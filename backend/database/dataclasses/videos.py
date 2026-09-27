from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class Video(Row):
    """One `videos` row; unselected columns stay None."""

    id: str | None = None
    channel_id: str | None = None
    title: str | None = None
    description: str | None = None
    published_at: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    content_type: str | None = None
    privacy_status: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    own: bool | None = None
    updated_at: str | None = None
