from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

import database
import sync

router = APIRouter()


@router.get("/sync/status")
def sync_status() -> dict:
    """Return active sync status and progress."""
    return sync.get_status()


@router.post("/sync/trigger")
def trigger_sync(
    background_tasks: BackgroundTasks,
    scope: str = Query(default="incremental"),
    year: int | None = Query(default=None),
) -> dict:
    """Manually trigger a sync if one is not already running.

    scope: "incremental" (default, resume from last synced date) | "year" (refetch
    the given year) | "all" (refetch each video's entire history). scope/year only
    affect video analytics and traffic source syncing.
    """
    if sync.is_syncing():
        raise HTTPException(status_code=409, detail="Sync already in progress")
    if scope not in ("incremental", "year", "all"):
        raise HTTPException(status_code=400, detail="scope must be one of: incremental, year, all")
    if scope == "year" and year is None:
        raise HTTPException(status_code=400, detail="year is required when scope=year")
    background_tasks.add_task(sync.run_sync, scope, year)
    return {"queued": True}


@router.get("/sync/runs")
def sync_runs(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    """Return recent sync-stage records, newest first."""
    return {"items": database.get_sync_runs(limit)}
