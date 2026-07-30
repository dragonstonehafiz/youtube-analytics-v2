from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import database

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
    sync_video_analytics,
    sync_video_traffic_sources,
    sync_videos,
)

__all__ = ["FULL_SYNC_TYPES", "execute_plan", "run_plan"]


@dataclass(frozen=True)
class _StageSpec:
    """How one stage is announced and invoked.

    `message` is None for stages that report their own per-video progress from inside
    their loop; setting a message here would be immediately overwritten.
    """

    message: str | None
    run: Callable[[PlanStage, SyncCounts], None]


_STAGE_REGISTRY: dict[str, _StageSpec] = {
    "videos": _StageSpec(
        "Syncing videos...",
        lambda stage, counts: sync_videos(counts),
    ),
    "playlists": _StageSpec(
        "Syncing playlists...",
        lambda stage, counts: sync_playlists(counts),
    ),
    "video_analytics": _StageSpec(
        None,
        lambda stage, counts: sync_video_analytics(recorded_scope(stage), stage.year, counts),
    ),
    "video_traffic_sources": _StageSpec(
        None,
        lambda stage, counts: sync_video_traffic_sources(recorded_scope(stage), stage.year, counts),
    ),
    "fx_rates": _StageSpec(
        "Syncing FX rates...",
        lambda stage, counts: sync_fx_rates(counts),
    ),
}


def _run_stage(
    batch_id: str,
    sync_type: str,
    scope: str | None,
    year: int | None,
    fn: Callable[[SyncCounts], None],
) -> None:
    """Run one sync stage, recording a sync_runs row that reflects partial progress on failure."""
    counts = SyncCounts()
    sync_run_id = database.create_sync_run(batch_id, sync_type, scope, year)
    try:
        fn(counts)
    except Exception as exc:
        database.fail_sync_run(
            sync_run_id, str(exc), counts.rows_fetched, counts.rows_written, counts.rows_deleted
        )
        raise
    else:
        database.complete_sync_run(
            sync_run_id, counts.rows_fetched, counts.rows_written, counts.rows_deleted
        )


def execute_plan(stages: Sequence[PlanStage]) -> None:
    """Run a validated plan whose active-state reservation the caller already holds.

    Only the selected stages run, always in the canonical STAGE_ORDER regardless of the
    order they were submitted in, and every started stage gets one sync_runs row sharing
    a single batch_id. Execution is fail-fast: a failing stage is recorded with its
    partial counters and later stages neither run nor create rows — which also keeps the
    batch from qualifying as a complete pipeline run.

    Releases the reservation in all cases. Safe to call from a background thread.
    """
    try:
        # Revalidated here, not just at the API boundary, so no caller can drive the
        # stage loop with a plan that was never checked. validate_plan is idempotent.
        plan = {stage.stage: stage for stage in validate_plan(stages)}
        batch_id = str(uuid.uuid4())

        for name in STAGE_ORDER:
            stage = plan.get(name)
            if stage is None:
                continue
            spec = _STAGE_REGISTRY[name]
            if spec.message:
                status.set_message(spec.message)
            # Invoked synchronously inside _run_stage, so the loop variables cannot
            # advance before the lambda runs.
            _run_stage(
                batch_id,
                name,
                recorded_scope(stage),
                recorded_year(stage),
                lambda counts: spec.run(stage, counts),
            )
        status.set_message("Sync complete.")

    except Exception as exc:
        status.set_message(f"Sync failed: {exc}")
        raise

    finally:
        status.finish()


def run_plan(stages: Sequence[PlanStage]) -> bool:
    """Reserve active state and run a validated plan. Returns False if a sync is already active.

    Use this for callers that hold no reservation yet (the startup sync). Callers that
    already reserved — the manual trigger route — must use execute_plan instead, which
    would otherwise be blocked by their own reservation.
    """
    if not status.try_start("Starting sync..."):
        return False
    execute_plan(stages)
    return True
