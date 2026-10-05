from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class PlaylistItem(Row):
    """One `playlist_items` row; unselected columns stay None."""

    id: str | None = None
    playlist_id: str | None = None
    video_id: str | None = None
    position: int | None = None
    updated_at: str | None = None
