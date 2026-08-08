from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence

import database
from logging_config import exception_context, get_logger

from . import status
from .plans import (
    FULL_SYNC_TYPES,
    STAGE_ORDER,
    PlanStage,
    recorded_scope,
    recorded_year,
    validate_plan,
)
from .stages import (
    SyncCounts,
    sync_fx_rates,
    sync_playlists,
    sync_pruning,
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
    "pruning": "Pruning videos...",
    "video_analytics": None,
    "video_traffic_sources": None,
    "fx_rates": "Syncing FX rates...",
}

# Fixed, safe operation labels for public failure text. Never combined with exception
# content: `str(exc)` may carry headers, credentials, tokens, or API response bodies.
_STAGE_FAILURE_LABELS: dict[str, str] = {
    "playlists": "syncing playlists",
    "videos": "syncing videos",
    "pruning": "pruning videos",
    "video_analytics": "syncing video analytics",
    "video_traffic_sources": "syncing video traffic sources",
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
    """Run one sync stage, recording a sync_runs row that reflects partial progress on failure."""
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


def execute_plan(stages: Sequence[PlanStage]) -> None:
    """Run a validated plan whose active-state reservation the caller already holds.

    Only the selected stages run, always in the canonical STAGE_ORDER regardless of the
    order they were submitted in, and every started stage gets one sync_runs row sharing
    a single batch_id. Execution is fail-fast: a failing stage is recorded with its
    partial counters and later stages neither run nor create rows — which also keeps the
    batch from qualifying as a complete pipeline run.

    Playlist- and video-discovered IDs are held in local variables for this call only
    (never persisted) and threaded from `sync_playlists()` into `sync_videos()` and from
    `sync_videos()` into `sync_pruning()`. Canonical ordering and fail-fast execution
    guarantee pruning cannot run without both of its inputs already populated.

    Releases the reservation in all cases. Safe to call from a background thread.
    """
    playlist_video_ids: set[str] = set()
    channel_owned_ids: set[str] = set()
    current_stage: str | None = None

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

        for name in STAGE_ORDER:
            stage = plan.get(name)
            if stage is None:
                continue
            current_stage = name
            message = _STAGE_MESSAGES[name]
            if message:
                status.update_sync_progress(message)

            run: Callable[[SyncCounts], None]
            if name == "playlists":
                def run(counts: SyncCounts) -> None:
                    nonlocal playlist_video_ids
                    playlist_video_ids = sync_playlists(counts)
            elif name == "videos":
                def run(counts: SyncCounts) -> None:
                    nonlocal channel_owned_ids
                    channel_owned_ids = sync_videos(counts, playlist_video_ids)
            elif name == "pruning":
                def run(counts: SyncCounts) -> None:
                    sync_pruning(counts, channel_owned_ids)
            elif name == "video_analytics":
                def run(counts: SyncCounts, stage: PlanStage = stage) -> None:
                    sync_video_analytics(recorded_scope(stage), stage.year, counts)
            elif name == "video_traffic_sources":
                def run(counts: SyncCounts, stage: PlanStage = stage) -> None:
                    sync_video_traffic_sources(recorded_scope(stage), stage.year, counts)
            else:
                def run(counts: SyncCounts) -> None:
                    sync_fx_rates(counts)

            _run_stage(batch_id, name, recorded_scope(stage), recorded_year(stage), run)
        status.complete_sync("Sync complete")

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
