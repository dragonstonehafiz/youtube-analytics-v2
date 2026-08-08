from __future__ import annotations

from datetime import date, timedelta

from .connection import _now, get_connection


def upsert_video_analytics(row: dict) -> None:
    """Insert or replace a video analytics row."""
    row = {**row, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO video_analytics (video_id, date, views, watch_time_minutes,
                estimated_revenue, average_view_duration_seconds, average_view_percentage,
                likes, subscribers_gained, subscribers_lost, updated_at)
            VALUES (:video_id, :date, :views, :watch_time_minutes,
                :estimated_revenue, :average_view_duration_seconds, :average_view_percentage,
                :likes, :subscribers_gained, :subscribers_lost, :updated_at)
            ON CONFLICT(video_id, date) DO UPDATE SET
                views = excluded.views,
                watch_time_minutes = excluded.watch_time_minutes,
                estimated_revenue = excluded.estimated_revenue,
                average_view_duration_seconds = excluded.average_view_duration_seconds,
                average_view_percentage = excluded.average_view_percentage,
                likes = excluded.likes,
                subscribers_gained = excluded.subscribers_gained,
                subscribers_lost = excluded.subscribers_lost,
                updated_at = excluded.updated_at
            """,
            row,
        )


def _zero_fill_analytics(rows: list[dict], start_date: str | None, end_date: str | None, content_types: list[str]) -> list[dict]:
    """Fill missing (date, content_type) combinations in the analytics rows with zero values."""
    if not rows:
        return rows
    by_key = {(r["date"], r["content_type"]): r for r in rows}
    real_dates = {r["date"] for r in rows}
    dates = [r["date"] for r in rows]
    first = date.fromisoformat(start_date or min(dates))
    last = date.fromisoformat(end_date or max(dates))
    zero = {k: 0 for k in rows[0] if k not in ("date", "content_type")}
    result = []
    d = first
    while d <= last:
        ds = d.isoformat()
        for ct in content_types:
            result.append(by_key.get((ds, ct), {"date": ds, "content_type": ct, **zero}))
        d += timedelta(days=1)
    while result and result[-1]["date"] not in real_dates:
        result.pop()
    return result


def get_video_analytics(
    video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return daily analytics rows for a video, ordered by date, with optional date filters."""
    conditions = ["va.video_id = ?"]
    params: list = [video_id]
    if start_date:
        conditions.append("va.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("va.date <= ?")
        params.append(end_date)
    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT va.*, v.content_type,
                COALESCE(va.estimated_revenue * fx.usd_to_sgd, 0) AS estimated_revenue_sgd
            FROM video_analytics va
            JOIN videos v ON v.id = va.video_id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE {where}
            ORDER BY va.date
            """,
            params,
        ).fetchall()
    dict_rows = [dict(r) for r in rows]
    content_types = [dict_rows[0]["content_type"]] if dict_rows else []
    return _zero_fill_analytics(dict_rows, start_date, end_date, content_types)


def get_last_analytics_date(video_id: str) -> str | None:
    """Return the most recent date we have analytics for a video, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS last_date FROM video_analytics WHERE video_id = ?",
            (video_id,),
        ).fetchone()
    return row["last_date"] if row else None


def get_aggregated_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
) -> list[dict]:
    """Return daily analytics aggregated across all videos, grouped by date and content_type, filtered by date range, content_type, privacy_status, and title."""
    conditions = ["1=1"]
    params: list = []

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("va.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("va.date <= ?")
        params.append(end_date)
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                va.date,
                v.content_type,
                SUM(va.views) AS views,
                SUM(va.watch_time_minutes) AS watch_time_minutes,
                SUM(va.estimated_revenue) AS estimated_revenue,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS estimated_revenue_sgd,
                AVG(va.average_view_duration_seconds) AS average_view_duration_seconds,
                AVG(va.average_view_percentage) AS average_view_percentage,
                SUM(va.likes) AS likes,
                SUM(va.subscribers_gained) AS subscribers_gained,
                SUM(va.subscribers_lost) AS subscribers_lost
            FROM video_analytics va
            JOIN videos v ON v.id = va.video_id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE {where}
            GROUP BY va.date, v.content_type
            ORDER BY va.date, v.content_type
            """,
            params,
        ).fetchall()
    content_types = [content_type] if content_type else ["video", "short"]
    return _zero_fill_analytics([dict(r) for r in rows], start_date, end_date, content_types)


_TOP_VIDEO_SORT_ORDER_BY = {
    "views": "period_views DESC, v.id ASC",
    "watch_time": "period_watch_time_hours DESC, period_views DESC, v.id ASC",
}


def get_top_videos_by_views(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    limit: int = 10,
    sort_by: str = "views",
    title: str | None = None,
) -> list[dict]:
    """Return top videos within the given filters, ranked by views or period watch time, with earnings in SGD
    for the same period. Unsupported sort_by values fall back to views."""
    order_by = _TOP_VIDEO_SORT_ORDER_BY.get(sort_by, _TOP_VIDEO_SORT_ORDER_BY["views"])
    conditions = ["1=1"]
    params: list = []

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("va.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("va.date <= ?")
        params.append(end_date)
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                v.id, v.title, v.published_at, v.thumbnail_url, v.content_type,
                SUM(va.views) AS period_views,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS period_earnings_sgd,
                COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS period_watch_time_hours
            FROM video_analytics va
            JOIN videos v ON v.id = va.video_id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE {where}
            GROUP BY v.id
            ORDER BY {order_by}
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return [dict(r) for r in rows]


def get_playlist_top_videos_by_views(
    playlist_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    limit: int = 10,
    sort_by: str = "views",
    title: str | None = None,
) -> list[dict]:
    """Return top videos in a playlist within the given filters, ranked by views or period watch time, with
    earnings in SGD for the same period. Playlist membership is deduplicated by video ID before aggregation so
    duplicate playlist_items rows for the same video cannot inflate totals. Unsupported sort_by values fall back
    to views."""
    order_by = _TOP_VIDEO_SORT_ORDER_BY.get(sort_by, _TOP_VIDEO_SORT_ORDER_BY["views"])
    conditions = ["v.id IN (SELECT DISTINCT pi.video_id FROM playlist_items pi WHERE pi.playlist_id = ?)"]
    params: list = [playlist_id]

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("va.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("va.date <= ?")
        params.append(end_date)
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                v.id, v.title, v.published_at, v.thumbnail_url, v.content_type,
                SUM(va.views) AS period_views,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS period_earnings_sgd,
                COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS period_watch_time_hours
            FROM video_analytics va
            JOIN videos v ON v.id = va.video_id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE {where}
            GROUP BY v.id
            ORDER BY {order_by}
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return [dict(r) for r in rows]


def get_playlist_aggregated_analytics(
    playlist_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
) -> list[dict]:
    """Return daily analytics aggregated across all videos in a playlist, grouped by date and content_type, filtered by date range, content_type, privacy_status, and title."""
    conditions = ["pi.playlist_id = ?"]
    params: list = [playlist_id]

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("va.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("va.date <= ?")
        params.append(end_date)
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                va.date,
                v.content_type,
                SUM(va.views) AS views,
                SUM(va.watch_time_minutes) AS watch_time_minutes,
                SUM(va.estimated_revenue) AS estimated_revenue,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS estimated_revenue_sgd,
                AVG(va.average_view_duration_seconds) AS average_view_duration_seconds,
                AVG(va.average_view_percentage) AS average_view_percentage,
                SUM(va.likes) AS likes,
                SUM(va.subscribers_gained) AS subscribers_gained,
                SUM(va.subscribers_lost) AS subscribers_lost
            FROM video_analytics va
            JOIN videos v ON v.id = va.video_id
            JOIN playlist_items pi ON pi.video_id = va.video_id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE {where}
            GROUP BY va.date, v.content_type
            ORDER BY va.date, v.content_type
            """,
            params,
        ).fetchall()
    content_types = [content_type] if content_type else ["video", "short"]
    return _zero_fill_analytics([dict(r) for r in rows], start_date, end_date, content_types)
