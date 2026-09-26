from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, ConfigDict

import database
import sync

router = APIRouter()

SyncStage = Literal[
    "videos",
    "playlists",
    "comments",
    "pruning",
    "video_analytics",
    "video_traffic_sources",
    "search_insights",
    "related_video_insights",
    "fx_rates",
]
SyncScope = Literal["incremental", "year", "all"]


class PlanStageRequest(BaseModel):
    """One requested stage. `scope`/`year` apply only to the period-aware stages."""

    model_config = ConfigDict(extra="forbid")

    stage: SyncStage
    scope: SyncScope | None = None
    year: int | None = None


class SyncPlanRequest(BaseModel):
    """An explicit manual sync plan. Submission order does not affect execution order."""

    model_config = ConfigDict(extra="forbid")

    stages: list[PlanStageRequest]


@router.get("/sync/status")
def sync_status() -> sync.SyncStatus:
    """Return reservation state and independent status for each selected stage."""
    return sync.get_sync_status()


@router.post("/sync/stop")
def stop_sync() -> dict:
    """Request cooperative cancellation of the active sync."""
    if not sync.request_stop():
        raise HTTPException(status_code=409, detail="No sync in progress")
    return {"stopping": True}


@router.post("/sync/trigger")
def trigger_sync(plan: SyncPlanRequest, background_tasks: BackgroundTasks) -> dict:
    """Queue a validated manual sync when no sync is active."""
    try:
        stages = sync.validate_plan(
            [sync.PlanStage(s.stage, s.scope, s.year) for s in plan.stages]
        )
    except sync.PlanValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not sync.try_begin_sync([stage.stage for stage in stages]):
        raise HTTPException(status_code=409, detail="Sync already in progress")

    try:
        background_tasks.add_task(sync.execute_plan, stages)
    except Exception:
        sync.reset_sync_status()
        raise

    return {"queued": True}


@router.get("/sync/runs")
def sync_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict:
    """Return a page of newest-first sync batches and the total batch count."""
    items, total = database.get_sync_runs(page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}
