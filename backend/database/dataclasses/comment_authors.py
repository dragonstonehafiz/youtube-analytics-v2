from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class CommentAuthor(Row):
    """One `comment_authors` row; unselected columns stay None."""

    id: str | None = None
    youtube_channel_id: str | None = None
    display_name: str | None = None
    profile_image_url: str | None = None
    channel_url: str | None = None
    updated_at: str | None = None
