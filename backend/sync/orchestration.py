from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from database import SyncRun, now, writer
from logging_config import exception_context, get_logger

from . import status
from .plans import (
    ANALYTICS_STAGES,
    FULL_SYNC_TYPES,
    PRE_ANALYTICS_STAGES,
    STAGE_ORDER,
    PlanStage,
    allocate_analytics_workers,
    recorded_scope,
    recorded_year,
    validate_plan,
)
from .stages import (
    SyncCounts,
    sync_comments,
    sync_fx_rates,
    sync_playlists,
    sync_pruning,
    sync_related_video_insights,
    sync_search_insights,
    sync_video_analytics,
    sync_video_traffic_sources,
    sync_videos,
)

__all__ = ["FULL_SYNC_TYPES", "execute_plan", "run_plan"]

_logger = get_logger("sync")


def _format_stage_counts(sync_type: str, counts: SyncCounts) -> str:
    """Render the canonical stage-count suffix shared by start/completion/failure records."""
    return (
        f"sync_type={sync_type} rows_fetched={counts.rows_fetched} "
        f"rows_written={counts.rows_written} rows_deleted={counts.rows_deleted}"
    )


# Starting message published the instant each stage is dispatched, before it has done
# any work of its own. Stages that report their own per-video progress from inside their
# loop (comments, the four Analytics API stages) overwrite this with real counts on their
# first iteration; every stage gets one immediately so a freshly-running stage is never
# shown with a blank message before that first update lands.
_STAGE_MESSAGES: dict[str, str] = {
    "playlists": "Syncing playlists...",
    "videos": "Syncing videos...",
    "comments": "Syncing comments...",
    "pruning": "Pruning videos...",
    "video_analytics": "Syncing video analytics...",
    "video_traffic_sources": "Syncing traffic sources...",
    "search_insights": "Syncing search insights...",
    "related_video_insights": "Syncing related video insights...",
    "fx_rates": "Syncing FX rates...",
}

# Fixed, safe operation labels for public failure text. Never combined with exception
# content: `str(exc)` may carry headers, credentials, tokens, or API response bodies.
_STAGE_FAILURE_LABELS: dict[str, str] = {
    "playlists": "syncing playlists",
    "videos": "syncing videos",
    "comments": "syncing comments",
    "pruning": "pruning videos",
    "video_analytics": "syncing video analytics",
    "video_traffic_sources": "syncing video traffic sources",
    "search_insights": "syncing search insights",
    "related_video_insights": "syncing related video insights",
    "fx_rates": "syncing FX rates",
}


def _finish_sync_run(
    sync_run_id: int | None, outcome: str, counts: SyncCounts, error_message: str | None = None,
) -> None:
    """Record a stage's final status, completion time, counters, and optional error."""
    writer.update(SyncRun(
        status=outcome, completed_at=now(), rows_fetched=counts.rows_fetched, rows_written=counts.rows_written,
        rows_deleted=counts.rows_deleted, error_message=error_message,
    ), where=(("id", "=", sync_run_id),))


def _run_stage(
    batch_id: str,
    sync_type: str,
    scope: str | None,
    year: int | None,
    fn: Callable[[SyncCounts], None],
) -> None:
    """Run a sync stage and record its final or partial progress."""
    counts = SyncCounts()
    _logger.info("Sync stage started %s", _format_stage_counts(sync_type, counts))

    try:
        started = SyncRun(
            batch_id=batch_id, sync_type=sync_type, scope=scope, year=year, status="running", started_at=now(),
        )
        sync_run_id = writer.write(started, returning=("id",)).id
    except Exception as exc:
        _logger.error(
            "Sync stage persistence failed %s operation=create_sync_run %s",
            _format_stage_counts(sync_type, counts),
            exception_context(exc),
        )
        raise

    try:
        fn(counts)
    except status.SyncCancelled:
        _logger.info(
            "Sync stage cancelled %s scope=%s year=%s", _format_stage_counts(sync_type, counts), scope, year
        )
        try:
            _finish_sync_run(sync_run_id, "cancelled", counts)
        except Exception as cancel_exc:
            _logger.error(
                "Sync stage persistence failed %s operation=cancel_sync_run %s",
                _format_stage_counts(sync_type, counts),
                exception_context(cancel_exc),
            )
            raise
        raise
    except Exception as exc:
        _logger.error(
            "Sync stage failed %s scope=%s year=%s %s",
            _format_stage_counts(sync_type, counts),
            scope,
            year,
            exception_context(exc),
        )
        try:
            _finish_sync_run(sync_run_id, "failed", counts, str(exc))
        except Exception as fail_exc:
            _logger.error(
                "Sync stage persistence failed %s operation=fail_sync_run %s",
                _format_stage_counts(sync_type, counts),
                exception_context(fail_exc),
            )
            raise
        raise
    else:
        try:
            _finish_sync_run(sync_run_id, "success", counts)
        except Exception as exc:
            _logger.error(
                "Sync stage persistence failed %s operation=complete_sync_run %s",
                _format_stage_counts(sync_type, counts),
                exception_context(exc),
            )
            raise
        _logger.info("Sync stage completed %s", _format_stage_counts(sync_type, counts))


def _run_tracked_stage(batch_id: str, name: str, stage: PlanStage, run: Callable[[SyncCounts], None]) -> None:
    """Run a stage while recording its live and final outcome."""
    status.update_sync_progress(name, _STAGE_MESSAGES[name])
    try:
        _run_stage(batch_id, name, recorded_scope(stage), recorded_year(stage), run)
    except status.SyncCancelled:
        status.cancel_stage(name)
        raise
    except Exception:
        status.fail_stage(name, _STAGE_FAILURE_LABELS[name])
        raise
    else:
        status.complete_stage(name)


def _pre_analytics_runner(
    name: str,
    stage: PlanStage,
    playlist_video_ids: Callable[[], set[str]],
    set_playlist_video_ids: Callable[[set[str]], None],
    set_channel_owned_ids: Callable[[set[str]], None],
    channel_owned_ids: Callable[[], set[str]],
) -> Callable[[SyncCounts], None]:
    """Build a pre-analytics stage callable with plan-local ID state."""
    run: Callable[[SyncCounts], None]
    if name == "playlists":
        def run(counts: SyncCounts) -> None:
            set_playlist_video_ids(sync_playlists(counts))
    elif name == "videos":
        def run(counts: SyncCounts) -> None:
            set_channel_owned_ids(sync_videos(counts, playlist_video_ids()))
    elif name == "pruning":
        def run(counts: SyncCounts) -> None:
            sync_pruning(counts, channel_owned_ids())
    elif name == "comments":
        def run(counts: SyncCounts) -> None:
            sync_comments(recorded_scope(stage), counts)
    else:
        def run(counts: SyncCounts) -> None:
            sync_fx_rates(counts)
    return run


_ANALYTICS_RUNNERS: dict[str, Callable[[PlanStage, SyncCounts], None]] = {
    "video_analytics": lambda stage, counts: sync_video_analytics(recorded_scope(stage), stage.year, counts),
    "video_traffic_sources": lambda stage, counts: sync_video_traffic_sources(recorded_scope(stage), stage.year, counts),
    "search_insights": lambda stage, counts: sync_search_insights(recorded_scope(stage), stage.year, counts),
    "related_video_insights": lambda stage, counts: sync_related_video_insights(recorded_scope(stage), stage.year, counts),
}


@dataclass
class _WorkerOutcome:
    """One Analytics API worker's result, written only by its own thread and read only
    after `Thread.join()` — no lock needed."""

    cancelled: bool = False
    failed_stages: list[str] = field(default_factory=list)


def _run_analytics_worker(
    batch_id: str, plan: dict[str, PlanStage], stage_names: Sequence[str], outcome: _WorkerOutcome,
) -> None:
    """Run one analytics worker queue until completion, cancellation, or failure."""
    for name in stage_names:
        try:
            status.raise_if_stopping()
        except status.SyncCancelled:
            outcome.cancelled = True
            return

        stage = plan[name]

        def run(counts: SyncCounts, stage: PlanStage = stage, name: str = name) -> None:
            _ANALYTICS_RUNNERS[name](stage, counts)

        try:
            _run_tracked_stage(batch_id, name, stage, run)
        except status.SyncCancelled:
            outcome.cancelled = True
            return
        except Exception:
            outcome.failed_stages.append(name)
            return


def execute_plan(stages: Sequence[PlanStage]) -> None:
    """Execute a reserved, validated sync plan and release its reservation."""
    playlist_video_ids: set[str] = set()
    channel_owned_ids: set[str] = set()

    def get_playlist_video_ids() -> set[str]:
        return playlist_video_ids

    def set_playlist_video_ids(ids: set[str]) -> None:
        nonlocal playlist_video_ids
        playlist_video_ids = ids

    def get_channel_owned_ids() -> set[str]:
        return channel_owned_ids

    def set_channel_owned_ids(ids: set[str]) -> None:
        nonlocal channel_owned_ids
        channel_owned_ids = ids

    try:
        # Revalidated here, not just at the API boundary, so no caller can drive the
        # stage loop with a plan that was never checked. validate_plan is idempotent.
        try:
            plan = {stage.stage: stage for stage in validate_plan(stages)}
        except Exception as exc:
            _logger.error("Sync plan rejected %s", exception_context(exc))
            raise
        batch_id = str(uuid.uuid4())
        selected = ",".join(name for name in STAGE_ORDER if name in plan)
        _logger.info("Sync plan started sync_types=%s", selected)

        for name in PRE_ANALYTICS_STAGES:
            stage = plan.get(name)
            if stage is None:
                continue
            status.raise_if_stopping()
            run = _pre_analytics_runner(
                name, stage, get_playlist_video_ids, set_playlist_video_ids,
                set_channel_owned_ids, get_channel_owned_ids,
            )
            _run_tracked_stage(batch_id, name, stage, run)

        status.raise_if_stopping()

        analytics_selected = [name for name in ANALYTICS_STAGES if name in plan]
        if analytics_selected:
            worker_queues = allocate_analytics_workers(analytics_selected)
            outcomes = [_WorkerOutcome() for _ in worker_queues]
            threads: list[threading.Thread] = []
            for queue, outcome in zip(worker_queues, outcomes):
                if not queue:
                    continue
                thread = threading.Thread(
                    target=_run_analytics_worker, args=(batch_id, plan, queue, outcome),
                )
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join()

            failed_stages = [name for outcome in outcomes for name in outcome.failed_stages]
            if failed_stages:
                raise RuntimeError(f"Analytics API workers failed: {', '.join(failed_stages)}")
            if any(outcome.cancelled for outcome in outcomes):
                raise status.SyncCancelled()

        status.raise_if_stopping()
    except status.SyncCancelled:
        return
    finally:
        status.finish_sync()


def run_plan(stages: Sequence[PlanStage]) -> bool:
    """Reserve and execute a validated plan, or return False when busy."""
    if not status.try_begin_sync([stage.stage for stage in stages]):
        _logger.warning("Sync plan skipped reason=already_active")
        return False
    execute_plan(stages)
    return True
