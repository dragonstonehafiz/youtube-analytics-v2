from __future__ import annotations

import re

from .connection import _now, get_connection

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def upsert_search_terms(video_id: str, month: str, terms: list[dict]) -> int:
    """Upsert monthly search terms for a video and return the number written."""
    if not _MONTH_RE.match(month):
        raise ValueError(f"invalid month {month!r}; expected YYYY-MM")

    aggregated: dict[str, int] = {}
    for term in terms:
        search_term = term["search_term"]
        views = term["views"]
        if not isinstance(search_term, str) or not search_term:
            raise ValueError(f"invalid search_term in response row: {term!r}")
        if not isinstance(views, int) or isinstance(views, bool):
            raise ValueError(f"invalid views in response row: {term!r}")
        aggregated[search_term] = aggregated.get(search_term, 0) + views

    positive_terms = {term: views for term, views in aggregated.items() if views > 0}
    if not positive_terms:
        return 0

    updated_at = _now()
    rows_written = 0
    with get_connection() as conn:
        for search_term, views in positive_terms.items():
            conn.execute(
                """
                INSERT INTO search_terms (video_id, month, search_term, views, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(video_id, month, search_term) DO UPDATE SET
                    views = excluded.views,
                    updated_at = excluded.updated_at
                """,
                (video_id, month, search_term, views, updated_at),
            )
            rows_written += 1
    return rows_written
