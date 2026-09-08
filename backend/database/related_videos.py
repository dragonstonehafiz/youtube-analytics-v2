from __future__ import annotations

import re
from collections.abc import Collection

from .connection import _month_bound_conditions, _now, get_connection

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def upsert_related_videos(target_video_id: str, month: str, referrers: list[dict]) -> int:
    """Upsert one target video/month's Related Video referrers. `referrers` are shaped
    {"referrer_video_id": str, "views": int}. A referrer omitted or zeroed here is left
    untouched, not deleted. Returns the number of referrers upserted.

    Raises ValueError if `target_video_id` is not currently an owned video — Related
    rows only ever describe traffic *into* an owned target; a video can appear here as
    a referrer regardless of ownership, but never as an unowned target.
    """
    if not _MONTH_RE.match(month):
        raise ValueError(f"invalid month {month!r}; expected YYYY-MM")

    aggregated: dict[str, int] = {}
    for referrer in referrers:
        referrer_video_id = referrer["referrer_video_id"]
        views = referrer["views"]
        if not isinstance(referrer_video_id, str) or not referrer_video_id:
            raise ValueError(f"invalid referrer_video_id in response row: {referrer!r}")
        if not isinstance(views, int) or isinstance(views, bool):
            raise ValueError(f"invalid views in response row: {referrer!r}")
        aggregated[referrer_video_id] = aggregated.get(referrer_video_id, 0) + views

    positive_referrers = {rid: views for rid, views in aggregated.items() if views > 0}
    if not positive_referrers:
        return 0

    updated_at = _now()
    rows_written = 0
    with get_connection() as conn:
        owned_row = conn.execute("SELECT own FROM videos WHERE id = ?", (target_video_id,)).fetchone()
        if owned_row is None or not owned_row["own"]:
            raise ValueError(f"target_video_id {target_video_id!r} is not an owned video")
        for referrer_video_id, views in positive_referrers.items():
            conn.execute(
                """
                INSERT INTO related_videos (target_video_id, month, referrer_video_id, views, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(target_video_id, month, referrer_video_id) DO UPDATE SET
                    views = excluded.views,
                    updated_at = excluded.updated_at
                """,
                (target_video_id, month, referrer_video_id, views, updated_at),
            )
            rows_written += 1
    return rows_written


def get_last_related_videos_month(target_video_id: str) -> str | None:
    """Return the most recent YYYY-MM month we have Related Video referrers for a
    target video, or None. This is the Related collector's own checkpoint — never
    inferred from Search rows, aggregate Traffic Sources, a sync run, or the mere
    existence of a video.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(month) AS last_month FROM related_videos WHERE target_video_id = ?",
            (target_video_id,),
        ).fetchone()
    return row["last_month"] if row else None


def _coerce_referrer_own(row: dict) -> dict:
    """Convert the SQLite-integer-or-NULL referrer_own column into a real Python
    True/False/None, so an unresolved referrer serializes as JSON null rather than the
    `bool(None) == False` a naive conversion would produce."""
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
    """Return Related Video referrers aggregated across owned target videos, summed
    across the months overlapping start_date/end_date (a missing bound is unbounded on
    that side), ordered by views descending then referrer ID ascending.

    `video_ids` scopes the destination (target) side exactly like every other
    aggregation helper: None covers every owned video, a populated collection covers
    only those videos, and an empty collection returns no rows. `content_type`,
    `privacy_status`, and `title` filter the target side the same way.

    `own` filters the *referrer* side: True matches only a referrer confirmed as this
    channel's own video; False matches everything else, including a referrer with no
    resolved metadata at all (`COALESCE(referrer_own, 0) = 0`) — an unresolved referrer
    is not confirmed ours, so it belongs in the "Other Channels" bucket, never in
    neither bucket. None (the default) returns every referrer regardless of ownership.
    `limit=None` returns every referrer.

    Returns {"items": [...], "total_named_views": int}. `total_named_views` is the same
    scope's SUM(views) across every real referrer regardless of the own/limit filters —
    an independent unfiltered total, computed alongside `items` in this same call, so
    the frontend never has to fetch an unranked/uncapped row set just to total it.
    """
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
        conditions.append("v.title LIKE ?")
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


def get_related_video_destinations(
    referrer_video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    video_ids: Collection[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return the top destination (target) videos for one given referrer, summed
    across the months overlapping start_date/end_date, ordered by views descending
    then target ID ascending. limit=None returns every destination.

    The referrer's own ownership is irrelevant to this query — any video, owned or
    external, can be a referrer. `video_ids` scopes the destination set exactly like
    get_related_video_referrers and every other aggregation helper (None = every owned
    video, populated = playlist members, empty = nothing).
    """
    scoped_ids = None if video_ids is None else list(video_ids)
    if scoped_ids is not None and not scoped_ids:
        return []

    month_conditions, month_params = _month_bound_conditions("rv", start_date, end_date)
    conditions = ["rv.referrer_video_id = ?", "v.own = 1", *month_conditions]
    params: list = [referrer_video_id, *month_params]
    if scoped_ids:
        conditions.append(f"v.id IN ({','.join('?' * len(scoped_ids))})")
        params.extend(scoped_ids)
    where = " AND ".join(conditions)
    limit_clause = "LIMIT ?" if limit is not None else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT v.id AS target_video_id, v.title AS title, v.thumbnail_url AS thumbnail_url,
                v.content_type AS content_type, SUM(rv.views) AS views
            FROM related_videos rv
            JOIN videos v ON v.id = rv.target_video_id
            WHERE {where}
            GROUP BY v.id
            ORDER BY views DESC, v.id ASC
            {limit_clause}
            """,
            [*params, *([limit] if limit is not None else [])],
        ).fetchall()
    return [dict(row) for row in rows]
