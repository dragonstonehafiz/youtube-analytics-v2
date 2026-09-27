from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class RelatedVideo(Row):
    """One monthly `related_videos` row, or grouped totals mapped onto its columns."""

    target_video_id: str | None = None
    month: str | None = None
    referrer_video_id: str | None = None
    views: int | None = None
    updated_at: str | None = None
