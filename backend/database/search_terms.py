from __future__ import annotations

import re
from collections.abc import Collection
from datetime import date

from .connection import _now, get_connection

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def upsert_search_terms(video_id: str, month: str, terms: list[dict]) -> int:
    """Upsert one video/month's search terms. `terms` are shaped {"search_term": str,
    "views": int}. A term omitted or zeroed here is left untouched, not deleted. Returns
    the number of terms upserted.
    """
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


def _inclusive_months(start_date: str | None, end_date: str | None) -> list[str]:
    """Return every YYYY-MM month from start_date's month through end_date's month.

    Empty when either bound is missing, unparsable, or start_date is after end_date.
    """
    if not start_date or not end_date:
        return []
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return []
    if start > end:
        return []

    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _search_terms_conditions(
    months: list[str],
    content_type: str | None,
    privacy_status: str | None,
    title: str | None,
    scoped_ids: list[str] | None,
) -> tuple[list[str], list]:
    """Build the shared WHERE conditions/params for the search-terms query helpers."""
    conditions = [f"st.month IN ({','.join('?' * len(months))})"]
    params: list = list(months)
    if scoped_ids:
        conditions.append(f"v.id IN ({','.join('?' * len(scoped_ids))})")
        params.extend(scoped_ids)
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")
    return conditions, params


def get_video_search_terms(
    video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return search terms for one video, summed across the months containing
    start_date/end_date, ordered by views descending. limit=None returns every term."""
    months = _inclusive_months(start_date, end_date)
    if not months:
        return []
    limit_clause = "LIMIT ?" if limit is not None else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT st.search_term, SUM(st.views) AS views
            FROM search_terms st
            WHERE st.video_id = ? AND st.month IN ({','.join('?' * len(months))})
            GROUP BY st.search_term
            ORDER BY views DESC, st.search_term ASC
            {limit_clause}
            """,
            [video_id, *months, *([limit] if limit is not None else [])],
        ).fetchall()
    return [dict(row) for row in rows]


def get_search_terms(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return search terms aggregated across videos, summed across the months containing
    start_date/end_date, ordered by views descending. limit=None returns every term.

    video_ids scopes the aggregation the same way as the other aggregation helpers: None
    covers every video in the channel, a populated collection covers only those videos,
    and an empty collection returns no rows.
    """
    scoped_ids = None if video_ids is None else list(video_ids)
    months = _inclusive_months(start_date, end_date)
    if (scoped_ids is not None and not scoped_ids) or not months:
        return []

    conditions, params = _search_terms_conditions(months, content_type, privacy_status, title, scoped_ids)
    where = " AND ".join(conditions)
    limit_clause = "LIMIT ?" if limit is not None else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT st.search_term, SUM(st.views) AS views
            FROM search_terms st
            JOIN videos v ON v.id = st.video_id
            WHERE {where}
            GROUP BY st.search_term
            ORDER BY views DESC, st.search_term ASC
            {limit_clause}
            """,
            [*params, *([limit] if limit is not None else [])],
        ).fetchall()
    return [dict(row) for row in rows]


def get_videos_by_search_term(
    search_term: str,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return the top N videos by views for one specific search term, filtered the same
    way as get_search_terms."""
    scoped_ids = None if video_ids is None else list(video_ids)
    months = _inclusive_months(start_date, end_date)
    if (scoped_ids is not None and not scoped_ids) or not months:
        return []

    conditions, params = _search_terms_conditions(months, content_type, privacy_status, title, scoped_ids)
    conditions.append("st.search_term = ?")
    params.append(search_term)
    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT v.id, v.title, v.thumbnail_url, v.content_type, SUM(st.views) AS views
            FROM search_terms st
            JOIN videos v ON v.id = st.video_id
            WHERE {where}
            GROUP BY v.id
            ORDER BY views DESC, v.id ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return [dict(row) for row in rows]
