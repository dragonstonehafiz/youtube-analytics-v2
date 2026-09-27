from __future__ import annotations

from dataclasses import dataclass

from .base import Row


@dataclass
class SearchTerm(Row):
    """One monthly `search_terms` row, or grouped totals mapped onto its columns."""

    video_id: str | None = None
    month: str | None = None
    search_term: str | None = None
    views: int | None = None
    updated_at: str | None = None
