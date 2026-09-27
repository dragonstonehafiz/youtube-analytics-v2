from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class SyncRun(Row):
    """One `sync_runs` stage record; unselected columns stay None."""

    id: int | None = None
    batch_id: str | None = None
    sync_type: str | None = None
    scope: str | None = None
    year: int | None = None
    status: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    rows_fetched: int | None = None
    rows_written: int | None = None
    rows_deleted: int | None = None
    error_message: str | None = None
