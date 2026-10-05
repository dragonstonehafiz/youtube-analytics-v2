from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class SyncCoverage(Row):
    """One `sync_coverage` row; unselected columns stay None."""

    collector: str | None = None
    video_id: str | None = None
    period_key: str | None = None
    completed_at: str | None = None
