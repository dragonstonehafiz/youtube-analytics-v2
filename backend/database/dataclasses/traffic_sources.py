from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class VideoTrafficSource(Row):
    """One `video_traffic_sources` row; unselected columns stay None."""

    video_id: str | None = None
    date: str | None = None
    traffic_source_type: str | None = None
    views: int | None = None
    watch_time_minutes: float | None = None
    updated_at: str | None = None
