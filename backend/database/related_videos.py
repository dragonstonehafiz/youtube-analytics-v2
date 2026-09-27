from __future__ import annotations

from collections.abc import Collection

from .connection import _month_bound_conditions, get_connection


def _coerce_referrer_own(row: dict) -> dict:
    """Convert a nullable SQLite ownership value to bool or None."""
    value = row.get("referrer_own")
    row["referrer_own"] = None if value is None else bool(value)
    return row


def get_related_video_referrers(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
    own: bool | None = None,
    limit: int | None = None,
) -> dict:
    """Return filtered Related Video referrers and total named views for owned targets."""
    scoped_ids = None if video_ids is None else list(video_ids)
    if scoped_ids is not None and not scoped_ids:
        return {"items": [], "total_named_views": 0}

    month_conditions, month_params = _month_bound_conditions("rv", start_date, end_date)
    conditions: list[str] = ["v.own = 1", *month_conditions]
    params: list = list(month_params)
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
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
        params.append(f"%{title}%")
    where = " AND ".join(conditions)

    own_condition = ""
    own_params: list = []
    if own is not None:
        own_condition = "AND COALESCE(ref.own, 0) = ?"
        own_params = [1 if own else 0]

    limit_clause = "LIMIT ?" if limit is not None else ""

    with get_connection() as conn:
        total_row = conn.execute(
            f"""
            SELECT COALESCE(SUM(rv.views), 0) AS total_named_views
            FROM related_videos rv
            JOIN videos v ON v.id = rv.target_video_id
            WHERE {where}
            """,
            params,
        ).fetchone()

        rows = conn.execute(
            f"""
            SELECT
                rv.referrer_video_id AS referrer_video_id,
                SUM(rv.views) AS views,
                ref.title AS title,
                ref.thumbnail_url AS thumbnail_url,
                ref.own AS referrer_own
            FROM related_videos rv
            JOIN videos v ON v.id = rv.target_video_id
            LEFT JOIN videos ref ON ref.id = rv.referrer_video_id
            WHERE {where} {own_condition}
            GROUP BY rv.referrer_video_id, ref.title, ref.thumbnail_url, ref.own
            ORDER BY views DESC, rv.referrer_video_id ASC
            {limit_clause}
            """,
            [*params, *own_params, *([limit] if limit is not None else [])],
        ).fetchall()

    return {
        "items": [_coerce_referrer_own(dict(row)) for row in rows],
        "total_named_views": total_row["total_named_views"],
    }
