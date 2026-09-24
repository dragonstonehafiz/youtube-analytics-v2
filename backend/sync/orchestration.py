from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import database
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


# Progress message shown while each stage runs. None for stages that report their own
# per-video progress from inside their loop; setting a message here would be
# immediately overwritten.
_STAGE_MESSAGES: dict[str, str | None] = {
    "playlists": "Syncing playlists...",
    "videos": "Syncing videos...",
    "comments": None,
    "pruning": "Pruning videos...",
    "video_analytics": None,
    "video_traffic_sources": None,
    "search_insights": None,
    "related_video_insights": None,
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


def _failure_message(stage_name: str | None) -> str:
    """Build safe, operation-specific failure text with no exception content."""
    if stage_name is None:
        return "Sync failed during plan validation"
    return f"Sync failed while {_STAGE_FAILURE_LABELS[stage_name]}"


def _run_stage(
    batch_id: str,
    sync_type: str,
    scope: str | None,
    year: int | None,
    fn: Callable[[SyncCounts], None],
) -> None:
    """Run one sync stage, recording a sync_runs row that reflects partial progress on
    failure or cooperative cancellation."""
    counts = SyncCounts()
    _logger.info("Sync stage started %s", _format_stage_counts(sync_type, counts))

    try:
        sync_run_id = database.create_sync_run(batch_id, sync_type, scope, year)
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
            database.cancel_sync_run(
                sync_run_id, counts.rows_fetched, counts.rows_written, counts.rows_deleted
            )
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
            database.fail_sync_run(
                sync_run_id, str(exc), counts.rows_fetched, counts.rows_written, counts.rows_deleted
            )
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
            database.complete_sync_run(
                sync_run_id, counts.rows_fetched, counts.rows_written, counts.rows_deleted
            )
        except Exception as exc:
            _logger.error(
                "Sync stage persistence failed %s operation=complete_sync_run %s",
                _format_stage_counts(sync_type, counts),
                exception_context(exc),
            )
            raise
        _logger.info("Sync stage completed %s", _format_stage_counts(sync_type, counts))


def _run_tracked_stage(batch_id: str, name: str, stage: PlanStage, run: Callable[[SyncCounts], None]) -> None:
    """Run one stage via `_run_stage()`, keeping its entry in the public status message
    (`sync.status`) in sync with its lifecycle: an initial fixed message is published for
    a stage whose loop doesn't report its own progress, the entry is removed on success
    or cancellation, and replaced with its fixed failure label — which stays visible
    alongside any other stage still active — on a genuine exception. Always re-raises
    `SyncCancelled` or the stage's own exception; the caller decides what that means at
    its own level (fail-fast for the serial pre-analytics stages, worker-isolated for the
    Analytics API stages).
    """
    initial_message = _STAGE_MESSAGES[name]
    if initial_message:
        status.update_sync_progress(name, initial_message)
    try:
        _run_stage(batch_id, name, recorded_scope(stage), recorded_year(stage), run)
    except status.SyncCancelled:
        status.end_stage(name)
        raise
    except Exception:
        status.fail_stage(name, _STAGE_FAILURE_LABELS[name])
        raise
    else:
        status.end_stage(name)


def _pre_analytics_runner(
    name: str,
    stage: PlanStage,
    playlist_video_ids: Callable[[], set[str]],
    set_playlist_video_ids: Callable[[set[str]], None],
    set_channel_owned_ids: Callable[[set[str]], None],
    channel_owned_ids: Callable[[], set[str]],
) -> Callable[[SyncCounts], None]:
    """Build the stage callable for one selected pre-analytics stage, threading the
    plan-local playlist/channel-owned ID sets between `playlists`, `videos`, and
    `pruning` via the given accessors."""
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
    """Run one worker's ordered Analytics API stage queue to completion, or stop it at
    its own first cancellation or genuine failure — isolated from the other worker,
    which keeps running its own queue regardless of what happens here."""
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


def _multi_failure_message(failed_stages: Sequence[str]) -> str:
    """Build safe failure text naming every failed Analytics API stage, in canonical
    stage order regardless of which worker or order they failed in."""
    ordered = [name for name in ANALYTICS_STAGES if name in failed_stages]
    labels = ", ".join(_STAGE_FAILURE_LABELS[name] for name in ordered)
    return f"Sync failed while {labels}"


def execute_plan(stages: Sequence[PlanStage]) -> None:
    """Run a validated plan whose active-state reservation the caller already holds.

    Only the selected stages run. The selected pre-analytics stages (`PRE_ANALYTICS_STAGES`
    — playlists, videos, pruning, FX rates, comments) run serially, fail-fast, in that
    canonical order; every started stage gets one sync_runs row sharing a single
    batch_id. Once they all succeed, the selected Analytics API stages
    (`ANALYTICS_STAGES`) are split across at most two independent workers by
    `allocate_analytics_workers()` and run concurrently — a failure on one worker stops
    only that worker's remaining queued stages, never the other's. An analytics-only
    plan (no pre-analytics stage selected) proceeds straight to the workers.

    Playlist- and video-discovered IDs are held in local variables for this call only
    (never persisted) and threaded from `sync_playlists()` into `sync_videos()` and from
    `sync_videos()` into `sync_pruning()`. Canonical ordering and fail-fast execution
    guarantee pruning cannot run without both of its inputs already populated.

    Releases the reservation in all cases. Safe to call from a background thread.
    """
    playlist_video_ids: set[str] = set()
    channel_owned_ids: set[str] = set()
    current_stage: str | None = None

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
            current_stage = name
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
                status.fail_sync(_multi_failure_message(failed_stages))
                raise RuntimeError(f"Analytics API workers failed: {', '.join(failed_stages)}")
            if any(outcome.cancelled for outcome in outcomes):
                raise status.SyncCancelled()

        status.raise_if_stopping()
        status.complete_sync("Sync complete")

    except status.SyncCancelled:
        status.cancel_sync("Sync stopped")
    except Exception:
        status.fail_sync(_failure_message(current_stage))
        raise


def run_plan(stages: Sequence[PlanStage]) -> bool:
    """Reserve active state and run a validated plan. Returns False if a sync is already active.

    Use this for callers that hold no reservation yet (the startup sync). Callers that
    already reserved — the manual trigger route — must use execute_plan instead, which
    would otherwise be blocked by their own reservation.
    """
    if not status.try_begin_sync("Starting sync..."):
        _logger.warning("Sync plan skipped reason=already_active")
        return False
    execute_plan(stages)
    return True
