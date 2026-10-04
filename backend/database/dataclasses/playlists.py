from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class Playlist(Row):
    """One `playlists` row; unselected columns stay None."""

    id: str | None = None
    title: str | None = None
    description: str | None = None
    published_at: str | None = None
    thumbnail_url: str | None = None
    item_count: int | None = None
    updated_at: str | None = None
    total_earnings_sgd: float | None = None
