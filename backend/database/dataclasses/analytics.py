from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class VideoAnalytics(Row):
    """One `video_analytics` row, or grouped totals mapped onto its columns."""

    video_id: str | None = None
    date: str | None = None
    views: int | None = None
    watch_time_minutes: float | None = None
    estimated_revenue: float | None = None
    average_view_duration_seconds: float | None = None
    average_view_percentage: float | None = None
    likes: int | None = None
    subscribers_gained: int | None = None
    subscribers_lost: int | None = None
    updated_at: str | None = None
