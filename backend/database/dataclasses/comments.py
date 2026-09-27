from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class Comment(Row):
    """One top-level `comments` row; unselected columns stay None."""

    id: str | None = None
    thread_id: str | None = None
    video_id: str | None = None
    author_id: str | None = None
    text: str | None = None
    like_count: int | None = None
    total_reply_count: int | None = None
    published_at: str | None = None
    youtube_updated_at: str | None = None
    updated_at: str | None = None
