from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_DB_PATH = Path(__file__).parent / "data" / "youtube.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _now() -> str:
    """Return the current time as a timezone-aware UTC ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory and foreign key enforcement set."""
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db() -> None:
    """Create tables from schema.sql if they don't exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema)


# ---------------------------------------------------------------------------
# Videos
# ---------------------------------------------------------------------------

def upsert_video(video: dict) -> None:
    """Insert or replace a video row."""
    row = {**video, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO videos (id, title, description, published_at, duration_seconds,
                thumbnail_url, content_type, privacy_status, view_count, like_count, comment_count,
                updated_at)
            VALUES (:id, :title, :description, :published_at, :duration_seconds,
                :thumbnail_url, :content_type, :privacy_status, :view_count, :like_count, :comment_count,
                :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                published_at = excluded.published_at,
                duration_seconds = excluded.duration_seconds,
                thumbnail_url = excluded.thumbnail_url,
                content_type = excluded.content_type,
                privacy_status = excluded.privacy_status,
                view_count = excluded.view_count,
                like_count = excluded.like_count,
                comment_count = excluded.comment_count,
                updated_at = excluded.updated_at
            """,
            row,
        )


_VIDEO_SORT_COLUMNS = {"published_at", "view_count", "comment_count", "total_revenue_sgd"}

def get_all_videos(
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "published_at",
    sort_dir: str = "desc",
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> tuple[list[dict], int]:
    """Return a page of videos with server-side sort and optional filters, plus total count."""
    col = sort_by if sort_by in _VIDEO_SORT_COLUMNS else "published_at"
    direction = "ASC" if sort_dir == "asc" else "DESC"
    offset = (page - 1) * page_size

    conditions: list[str] = []
    params: list[object] = []
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")
    if start_date:
        conditions.append("v.published_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("v.published_at <= ?")
        params.append(end_date + "T23:59:59")
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM videos v {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT v.*,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS total_revenue_sgd,
                COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS total_watch_time_hours
            FROM videos v
            LEFT JOIN video_analytics va ON va.video_id = v.id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            {where}
            GROUP BY v.id
            ORDER BY {col} {direction} LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return [dict(r) for r in rows], total


def get_video(video_id: str) -> dict | None:
    """Return a single video by ID, including total lifetime revenue in SGD."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT v.*,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS total_revenue_sgd,
                COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS total_watch_time_hours
            FROM videos v
            LEFT JOIN video_analytics va ON va.video_id = v.id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE v.id = ?
            GROUP BY v.id
            """,
            (video_id,),
        ).fetchone()
    return dict(row) if row else None


def get_videos_published(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    playlist_id: str | None = None,
) -> list[dict]:
    """Return id, title, published_at, thumbnail_url for videos matching filters, ordered by published_at."""
    conditions = ["1=1"]
    params: list = []
    if playlist_id:
        conditions.append("v.id IN (SELECT video_id FROM playlist_items WHERE playlist_id = ?)")
        params.append(playlist_id)
    if start_date:
        conditions.append("v.published_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("v.published_at <= ?")
        params.append(end_date + "T23:59:59")
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, title, published_at, thumbnail_url, content_type FROM videos v WHERE {where} ORDER BY v.published_at",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_earliest_published_year() -> int | None:
    """Return the year of the earliest video published_at, or None if empty."""
    with get_connection() as conn:
        video_min = conn.execute("SELECT MIN(published_at) FROM videos").fetchone()[0]
    return int(video_min[:4]) if video_min else None


def get_all_video_ids() -> list[str]:
    """Return all video IDs."""
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM videos").fetchall()
    return [r["id"] for r in rows]


def _empty_video_stats() -> dict:
    """Return a zeroed-out video stats dict matching the get_video_stats()/get_playlist_video_stats() contract."""
    return {
        "legacy_video_count": 0, "legacy_video_views": 0, "legacy_video_earnings_sgd": 0.0,
        "legacy_short_count": 0, "legacy_short_views": 0, "legacy_short_earnings_sgd": 0.0,
        "new_video_count": 0, "new_video_views": 0, "new_video_earnings_sgd": 0.0,
        "new_short_count": 0, "new_short_views": 0, "new_short_earnings_sgd": 0.0,
        "total_comments": 0, "video_comments": 0, "short_comments": 0,
        "total_public": 0, "total_private": 0, "total_unlisted": 0,
    }


def get_video_stats(
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> dict:
    """Return Legacy/New publication-classified counts with period views/earnings, plus lifetime comments and
    current privacy status, for all videos optionally filtered by title/content type/privacy status.

    Legacy content was published strictly before the effective start date; New content was published between the
    effective start and end dates inclusive. Period views/earnings are aggregated from video_analytics rows within
    the effective date range. When start_date/end_date are omitted, the effective range is derived from the
    available video_analytics date range, falling back to the matching videos' published_at range when no
    analytics rows exist at all. Comments and privacy status counts are always current lifetime totals and are
    not restricted by date.
    """
    conditions: list[str] = []
    params: list[object] = []
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection() as conn:
        analytics_min, analytics_max = conn.execute("SELECT MIN(date), MAX(date) FROM video_analytics").fetchone()
        publication_min, publication_max = conn.execute(
            f"SELECT MIN(v.published_at), MAX(v.published_at) FROM videos v {where}", params
        ).fetchone()

        eff_start = start_date or analytics_min or (publication_min[:10] if publication_min else None)
        eff_end = end_date or analytics_max or (publication_max[:10] if publication_max else None)
        eff_end_ts = f"{eff_end}T23:59:59" if eff_end else None

        catalog_row = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at < ? AND v.content_type = 'video' THEN 1 ELSE 0 END), 0) AS legacy_video_count,
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at < ? AND v.content_type = 'short' THEN 1 ELSE 0 END), 0) AS legacy_short_count,
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at >= ? AND v.published_at <= ? AND v.content_type = 'video' THEN 1 ELSE 0 END), 0) AS new_video_count,
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at >= ? AND v.published_at <= ? AND v.content_type = 'short' THEN 1 ELSE 0 END), 0) AS new_short_count,
                COALESCE(SUM(v.comment_count), 0) AS total_comments,
                COALESCE(SUM(CASE WHEN v.content_type = 'video' THEN v.comment_count ELSE 0 END), 0) AS video_comments,
                COALESCE(SUM(CASE WHEN v.content_type = 'short' THEN v.comment_count ELSE 0 END), 0) AS short_comments,
                COALESCE(SUM(CASE WHEN v.privacy_status = 'public' THEN 1 ELSE 0 END), 0) AS total_public,
                COALESCE(SUM(CASE WHEN v.privacy_status = 'private' THEN 1 ELSE 0 END), 0) AS total_private,
                COALESCE(SUM(CASE WHEN v.privacy_status = 'unlisted' THEN 1 ELSE 0 END), 0) AS total_unlisted
            FROM videos v
            {where}
            """,
            [eff_start, eff_start, eff_start, eff_end_ts, eff_start, eff_end_ts, *params],
        ).fetchone()

        period_rows = conn.execute(
            f"""
            SELECT
                CASE
                    WHEN v.published_at IS NULL THEN NULL
                    WHEN v.published_at < ? THEN 'legacy'
                    WHEN v.published_at >= ? AND v.published_at <= ? THEN 'new'
                    ELSE NULL
                END AS bucket,
                v.content_type AS content_type,
                COALESCE(SUM(pa.period_views), 0) AS period_views,
                COALESCE(SUM(pa.period_revenue_sgd), 0) AS period_revenue_sgd
            FROM videos v
            JOIN (
                SELECT va.video_id AS video_id,
                    SUM(va.views) AS period_views,
                    SUM(va.estimated_revenue * fx.usd_to_sgd) AS period_revenue_sgd
                FROM video_analytics va
                LEFT JOIN fx_rates fx ON fx.date = va.date
                WHERE va.date >= ? AND va.date <= ?
                GROUP BY va.video_id
            ) pa ON pa.video_id = v.id
            {where}
            GROUP BY bucket, v.content_type
            """,
            [eff_start, eff_start, eff_end_ts, eff_start, eff_end, *params],
        ).fetchall()

    result = {**_empty_video_stats(), **dict(catalog_row)}
    for period_row in period_rows:
        bucket = period_row["bucket"]
        if bucket is None or period_row["content_type"] not in ("video", "short"):
            continue
        prefix = f"{bucket}_{period_row['content_type']}"
        result[f"{prefix}_views"] = period_row["period_views"] or 0
        result[f"{prefix}_earnings_sgd"] = period_row["period_revenue_sgd"] or 0.0
    return result


def get_playlist_video_stats(
    playlist_id: str,
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> dict:
    """Return Legacy/New publication-classified counts with period views/earnings, plus lifetime comments and
    current privacy status, for videos in a playlist optionally filtered by title/content type/privacy status.

    Semantics match get_video_stats(), scoped to the playlist's member videos. Playlist membership is
    deduplicated by video ID before any counting or aggregation, so duplicate playlist_items rows for the same
    video cannot inflate results.
    """
    conditions: list[str] = ["v.id IN (SELECT DISTINCT pi.video_id FROM playlist_items pi WHERE pi.playlist_id = ?)"]
    params: list[object] = [playlist_id]
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    where = f"WHERE {' AND '.join(conditions)}"

    with get_connection() as conn:
        analytics_min, analytics_max = conn.execute(
            """
            SELECT MIN(va.date), MAX(va.date)
            FROM video_analytics va
            WHERE va.video_id IN (SELECT DISTINCT pi.video_id FROM playlist_items pi WHERE pi.playlist_id = ?)
            """,
            [playlist_id],
        ).fetchone()
        publication_min, publication_max = conn.execute(
            f"SELECT MIN(v.published_at), MAX(v.published_at) FROM videos v {where}", params
        ).fetchone()

        eff_start = start_date or analytics_min or (publication_min[:10] if publication_min else None)
        eff_end = end_date or analytics_max or (publication_max[:10] if publication_max else None)
        eff_end_ts = f"{eff_end}T23:59:59" if eff_end else None

        catalog_row = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at < ? AND v.content_type = 'video' THEN 1 ELSE 0 END), 0) AS legacy_video_count,
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at < ? AND v.content_type = 'short' THEN 1 ELSE 0 END), 0) AS legacy_short_count,
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at >= ? AND v.published_at <= ? AND v.content_type = 'video' THEN 1 ELSE 0 END), 0) AS new_video_count,
                COALESCE(SUM(CASE WHEN v.published_at IS NOT NULL AND v.published_at >= ? AND v.published_at <= ? AND v.content_type = 'short' THEN 1 ELSE 0 END), 0) AS new_short_count,
                COALESCE(SUM(v.comment_count), 0) AS total_comments,
                COALESCE(SUM(CASE WHEN v.content_type = 'video' THEN v.comment_count ELSE 0 END), 0) AS video_comments,
                COALESCE(SUM(CASE WHEN v.content_type = 'short' THEN v.comment_count ELSE 0 END), 0) AS short_comments,
                COALESCE(SUM(CASE WHEN v.privacy_status = 'public' THEN 1 ELSE 0 END), 0) AS total_public,
                COALESCE(SUM(CASE WHEN v.privacy_status = 'private' THEN 1 ELSE 0 END), 0) AS total_private,
                COALESCE(SUM(CASE WHEN v.privacy_status = 'unlisted' THEN 1 ELSE 0 END), 0) AS total_unlisted
            FROM videos v
            {where}
            """,
            [eff_start, eff_start, eff_start, eff_end_ts, eff_start, eff_end_ts, *params],
        ).fetchone()

        period_rows = conn.execute(
            f"""
            SELECT
                CASE
                    WHEN v.published_at IS NULL THEN NULL
                    WHEN v.published_at < ? THEN 'legacy'
                    WHEN v.published_at >= ? AND v.published_at <= ? THEN 'new'
                    ELSE NULL
                END AS bucket,
                v.content_type AS content_type,
                COALESCE(SUM(pa.period_views), 0) AS period_views,
                COALESCE(SUM(pa.period_revenue_sgd), 0) AS period_revenue_sgd
            FROM videos v
            JOIN (
                SELECT va.video_id AS video_id,
                    SUM(va.views) AS period_views,
                    SUM(va.estimated_revenue * fx.usd_to_sgd) AS period_revenue_sgd
                FROM video_analytics va
                LEFT JOIN fx_rates fx ON fx.date = va.date
                WHERE va.date >= ? AND va.date <= ?
                GROUP BY va.video_id
            ) pa ON pa.video_id = v.id
            {where}
            GROUP BY bucket, v.content_type
            """,
            [eff_start, eff_start, eff_end_ts, eff_start, eff_end, *params],
        ).fetchall()

    result = {**_empty_video_stats(), **dict(catalog_row)}
    for period_row in period_rows:
        bucket = period_row["bucket"]
        if bucket is None or period_row["content_type"] not in ("video", "short"):
            continue
        prefix = f"{bucket}_{period_row['content_type']}"
        result[f"{prefix}_views"] = period_row["period_views"] or 0
        result[f"{prefix}_earnings_sgd"] = period_row["period_revenue_sgd"] or 0.0
    return result


def delete_videos_not_in(ids: list[str]) -> int:
    """Delete videos (and their analytics via cascade) whose IDs are not in the given list. Returns the number of videos deleted."""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM videos WHERE id NOT IN ({placeholders})", ids)
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Video analytics
# ---------------------------------------------------------------------------

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


def upsert_video_traffic_source(row: dict) -> None:
    """Insert or replace a daily video traffic source row."""
    row = {**row, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO video_traffic_sources (video_id, date, traffic_source_type,
                views, watch_time_minutes, updated_at)
            VALUES (:video_id, :date, :traffic_source_type, :views, :watch_time_minutes, :updated_at)
            ON CONFLICT(video_id, date, traffic_source_type) DO UPDATE SET
                views = excluded.views,
                watch_time_minutes = excluded.watch_time_minutes,
                updated_at = excluded.updated_at
            """,
            row,
        )


def get_last_traffic_source_date(video_id: str) -> str | None:
    """Return the most recent date we have traffic sources for a video, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS last_date FROM video_traffic_sources WHERE video_id = ?",
            (video_id,),
        ).fetchone()
    return row["last_date"] if row else None


def _zero_fill_traffic_sources(rows: list[dict], start_date: str | None, end_date: str | None) -> list[dict]:
    """Insert a zero row on the 1st of each month, per traffic source type, for months with no data at all."""
    if not rows:
        return rows
    types = sorted({r["traffic_source_type"] for r in rows})
    seen = {(r["date"], r["traffic_source_type"]) for r in rows}
    first = date.fromisoformat(start_date or rows[0]["date"]).replace(day=1)
    last = date.fromisoformat(end_date or rows[-1]["date"])
    result = list(rows)
    d = first
    while d <= last:
        ds = d.isoformat()
        for t in types:
            if (ds, t) not in seen:
                result.append({"date": ds, "traffic_source_type": t, "views": 0, "watch_time_minutes": 0})
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1)
        else:
            d = d.replace(month=d.month + 1)
    result.sort(key=lambda r: (r["date"], r["traffic_source_type"]))
    real_dates = {r["date"] for r in rows}
    last_real_date = max(real_dates)
    result = [r for r in result if r["date"] <= last_real_date]
    return result


def get_video_traffic_sources(
    video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return daily traffic source rows for a video, ordered by date, with optional date filters."""
    conditions = ["vts.video_id = ?"]
    params: list = [video_id]
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)
    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT vts.date, vts.traffic_source_type, vts.views, vts.watch_time_minutes
            FROM video_traffic_sources vts
            WHERE {where}
            ORDER BY vts.date, vts.traffic_source_type
            """,
            params,
        ).fetchall()
    return _zero_fill_traffic_sources([dict(r) for r in rows], start_date, end_date)


def get_aggregated_traffic_sources(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> list[dict]:
    """Return daily traffic sources aggregated across all videos, filtered by date range, content_type, and privacy_status."""
    conditions = ["1=1"]
    params: list = []

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                vts.date,
                vts.traffic_source_type,
                SUM(vts.views) AS views,
                SUM(vts.watch_time_minutes) AS watch_time_minutes
            FROM video_traffic_sources vts
            JOIN videos v ON v.id = vts.video_id
            WHERE {where}
            GROUP BY vts.date, vts.traffic_source_type
            ORDER BY vts.date, vts.traffic_source_type
            """,
            params,
        ).fetchall()
    return _zero_fill_traffic_sources([dict(r) for r in rows], start_date, end_date)


def get_playlist_aggregated_traffic_sources(
    playlist_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> list[dict]:
    """Return daily traffic sources aggregated across all videos in a playlist, filtered by date range, content_type, and privacy_status."""
    conditions = ["pi.playlist_id = ?"]
    params: list = [playlist_id]

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                vts.date,
                vts.traffic_source_type,
                SUM(vts.views) AS views,
                SUM(vts.watch_time_minutes) AS watch_time_minutes
            FROM video_traffic_sources vts
            JOIN videos v ON v.id = vts.video_id
            JOIN playlist_items pi ON pi.video_id = vts.video_id
            WHERE {where}
            GROUP BY vts.date, vts.traffic_source_type
            ORDER BY vts.date, vts.traffic_source_type
            """,
            params,
        ).fetchall()
    return _zero_fill_traffic_sources([dict(r) for r in rows], start_date, end_date)


def get_top_videos_by_traffic_source(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    limit: int = 3,
) -> dict[str, list[dict]]:
    """Return the top N videos by views for each traffic source type, filtered by date range, content_type, and privacy_status."""
    conditions = ["1=1"]
    params: list = []

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                vts.traffic_source_type,
                v.id, v.title, v.thumbnail_url, v.content_type,
                SUM(vts.views) AS views,
                SUM(vts.watch_time_minutes) AS watch_time_minutes
            FROM video_traffic_sources vts
            JOIN videos v ON v.id = vts.video_id
            WHERE {where}
            GROUP BY vts.traffic_source_type, v.id
            ORDER BY vts.traffic_source_type, views DESC
            """,
            params,
        ).fetchall()
    return _top_n_per_source(rows, limit)


def get_playlist_top_videos_by_traffic_source(
    playlist_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    limit: int = 3,
) -> dict[str, list[dict]]:
    """Return the top N videos in a playlist by views for each traffic source type, filtered by date range, content_type, and privacy_status."""
    conditions = ["pi.playlist_id = ?"]
    params: list = [playlist_id]

    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                vts.traffic_source_type,
                v.id, v.title, v.thumbnail_url, v.content_type,
                SUM(vts.views) AS views,
                SUM(vts.watch_time_minutes) AS watch_time_minutes
            FROM video_traffic_sources vts
            JOIN videos v ON v.id = vts.video_id
            JOIN playlist_items pi ON pi.video_id = vts.video_id
            WHERE {where}
            GROUP BY vts.traffic_source_type, v.id
            ORDER BY vts.traffic_source_type, views DESC
            """,
            params,
        ).fetchall()
    return _top_n_per_source(rows, limit)


def _top_n_per_source(rows: list[sqlite3.Row], limit: int) -> dict[str, list[dict]]:
    """Group video rows by traffic_source_type, keeping only the first N per group (rows must already be sorted by views desc within each type)."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        d = dict(row)
        source_type = d.pop("traffic_source_type")
        bucket = grouped.setdefault(source_type, [])
        if len(bucket) < limit:
            bucket.append(d)
    return grouped


def get_aggregated_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> list[dict]:
    """Return daily analytics aggregated across all videos, grouped by date and content_type, filtered by date range, content_type, and privacy_status."""
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


def get_top_videos_by_views(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return top videos by views within the given filters, with earnings in SGD for the same period."""
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

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                v.id, v.title, v.published_at, v.thumbnail_url, v.content_type,
                SUM(va.views) AS period_views,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS period_earnings_sgd,
                SUM(va.watch_time_minutes) / 60.0 AS period_watch_time_hours
            FROM video_analytics va
            JOIN videos v ON v.id = va.video_id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE {where}
            GROUP BY v.id
            ORDER BY period_views DESC
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
) -> list[dict]:
    """Return top videos in a playlist by views within the given filters, with earnings in SGD for the same period."""
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

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                v.id, v.title, v.published_at, v.thumbnail_url, v.content_type,
                SUM(va.views) AS period_views,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS period_earnings_sgd
            FROM video_analytics va
            JOIN videos v ON v.id = va.video_id
            JOIN playlist_items pi ON pi.video_id = va.video_id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE {where}
            GROUP BY v.id
            ORDER BY period_views DESC
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
) -> list[dict]:
    """Return daily analytics aggregated across all videos in a playlist, grouped by date and content_type, filtered by date range, content_type, and privacy_status."""
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


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

def upsert_playlist(playlist: dict) -> None:
    """Insert or replace a playlist row."""
    row = {**playlist, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO playlists (id, title, description, published_at, thumbnail_url, item_count,
                updated_at)
            VALUES (:id, :title, :description, :published_at, :thumbnail_url, :item_count, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                published_at = excluded.published_at,
                thumbnail_url = excluded.thumbnail_url,
                item_count = excluded.item_count,
                updated_at = excluded.updated_at
            """,
            row,
        )


_PLAYLIST_SORT_COLUMNS = {"published_at", "item_count", "last_item_added", "total_views", "total_earnings_sgd"}

def get_all_playlists(
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "last_item_added",
    sort_dir: str = "desc",
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict], int]:
    """Return a page of playlists with server-side sort and optional filters, plus total count.

    Each row is augmented with:
    - last_item_added: MAX published_at of videos in the playlist
    - total_views: SUM of view_count of videos in the playlist
    - total_earnings_sgd: SUM of estimated_revenue * usd_to_sgd for videos in the playlist
    """
    col = sort_by if sort_by in _PLAYLIST_SORT_COLUMNS else "last_item_added"
    direction = "ASC" if sort_dir == "asc" else "DESC"
    offset = (page - 1) * page_size

    conditions: list[str] = []
    params: list[object] = []
    if title:
        conditions.append("p.title LIKE ?")
        params.append(f"%{title}%")
    if start_date:
        conditions.append("p.published_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("p.published_at <= ?")
        params.append(end_date + "T23:59:59")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    base_query = f"""
        SELECT
            p.*,
            MAX(v.published_at) AS last_item_added,
            COALESCE(SUM(v.view_count), 0) AS total_views,
            COALESCE((
                SELECT SUM(va.estimated_revenue * fx.usd_to_sgd)
                FROM playlist_items pi2
                JOIN video_analytics va ON va.video_id = pi2.video_id
                JOIN fx_rates fx ON fx.date = DATE(va.date)
                WHERE pi2.playlist_id = p.id
            ), 0) AS total_earnings_sgd
        FROM playlists p
        LEFT JOIN playlist_items pi ON pi.playlist_id = p.id
        LEFT JOIN videos v ON v.id = pi.video_id
        {where}
        GROUP BY p.id
    """
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM ({base_query})", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM ({base_query}) ORDER BY {col} {direction} LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
    return [dict(r) for r in rows], total


def get_playlist(playlist_id: str) -> dict | None:
    """Return a single playlist by ID with aggregated stats."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                p.*,
                MAX(v.published_at) AS last_item_added,
                COALESCE(SUM(v.view_count), 0) AS total_views,
                COALESCE((
                    SELECT SUM(va.estimated_revenue * fx.usd_to_sgd)
                    FROM playlist_items pi2
                    JOIN video_analytics va ON va.video_id = pi2.video_id
                    JOIN fx_rates fx ON fx.date = DATE(va.date)
                    WHERE pi2.playlist_id = p.id
                ), 0) AS total_earnings_sgd
            FROM playlists p
            LEFT JOIN playlist_items pi ON pi.playlist_id = p.id
            LEFT JOIN videos v ON v.id = pi.video_id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (playlist_id,),
        ).fetchone()
    return dict(row) if row else None


def upsert_playlist_item(item: dict) -> None:
    """Insert or replace a playlist item row."""
    row = {**item, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO playlist_items (id, playlist_id, video_id, position, updated_at)
            VALUES (:id, :playlist_id, :video_id, :position, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                playlist_id = excluded.playlist_id,
                video_id = excluded.video_id,
                position = excluded.position,
                updated_at = excluded.updated_at
            """,
            row,
        )


def get_playlist_videos(
    playlist_id: str,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "published_at",
    sort_dir: str = "desc",
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> tuple[list[dict], int]:
    """Return a page of videos in a playlist with server-side sort and optional filters, plus total count."""
    col = sort_by if sort_by in _VIDEO_SORT_COLUMNS else "published_at"
    direction = "ASC" if sort_dir == "asc" else "DESC"
    offset = (page - 1) * page_size

    conditions: list[str] = ["pi.playlist_id = ?"]
    params: list[object] = [playlist_id]
    if title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{title}%")
    if start_date:
        conditions.append("v.published_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("v.published_at <= ?")
        params.append(end_date + "T23:59:59")
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)

    where = f"WHERE {' AND '.join(conditions)}"
    with get_connection() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) FROM playlist_items pi
            JOIN videos v ON v.id = pi.video_id
            {where}
            """,
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT pi.position, v.*,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS total_revenue_sgd,
                COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS total_watch_time_hours
            FROM playlist_items pi
            JOIN videos v ON v.id = pi.video_id
            LEFT JOIN video_analytics va ON va.video_id = v.id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            {where}
            GROUP BY v.id
            ORDER BY {col} {direction}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return [dict(r) for r in rows], total


def delete_playlists_not_in(ids: list[str]) -> int:
    """Delete playlists (and their items via cascade) whose IDs are not in the given list. Returns the number of playlists deleted."""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        cursor = conn.execute(f"DELETE FROM playlists WHERE id NOT IN ({placeholders})", ids)
        return cursor.rowcount


def delete_playlist_items(playlist_id: str) -> int:
    """Remove all items for a playlist before re-inserting updated items. Returns the number of items deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist_id,))
        return cursor.rowcount


# ---------------------------------------------------------------------------
# FX rates
# ---------------------------------------------------------------------------

def upsert_fx_rate(row: dict) -> None:
    """Insert or replace a daily USD/SGD exchange rate row."""
    row = {**row, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fx_rates (date, usd_to_sgd, updated_at)
            VALUES (:date, :usd_to_sgd, :updated_at)
            ON CONFLICT(date) DO UPDATE SET
                usd_to_sgd = excluded.usd_to_sgd,
                updated_at = excluded.updated_at
            """,
            row,
        )


def get_last_fx_rate() -> dict | None:
    """Return the most recent FX rate row {date, usd_to_sgd}, or None if table is empty."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT date, usd_to_sgd FROM fx_rates ORDER BY date DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_fx_rates(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return daily USD/SGD rates, ordered by date, with optional date filters."""
    conditions: list[str] = []
    params: list[object] = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT date, usd_to_sgd FROM fx_rates {where} ORDER BY date",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

def get_sync_state(key: str) -> str | None:
    """Return a sync state value by key."""
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_sync_state(key: str, value: str) -> None:
    """Set a sync state value."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sync_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---------------------------------------------------------------------------
# Sync runs
# ---------------------------------------------------------------------------

def create_sync_run(batch_id: str, sync_type: str, scope: str | None, year: int | None) -> int:
    """Create a running sync-stage record and return its ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sync_runs (batch_id, sync_type, scope, year, status, started_at)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (batch_id, sync_type, scope, year, _now()),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def complete_sync_run(sync_run_id: int, rows_fetched: int, rows_written: int, rows_deleted: int) -> None:
    """Mark a sync stage successful and save its final counters."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sync_runs
            SET status = 'success', completed_at = ?, rows_fetched = ?, rows_written = ?, rows_deleted = ?
            WHERE id = ?
            """,
            (_now(), rows_fetched, rows_written, rows_deleted, sync_run_id),
        )


def fail_sync_run(
    sync_run_id: int,
    error_message: str,
    rows_fetched: int,
    rows_written: int,
    rows_deleted: int,
) -> None:
    """Mark a sync stage failed while preserving partial counters."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sync_runs
            SET status = 'failed', completed_at = ?, rows_fetched = ?, rows_written = ?, rows_deleted = ?,
                error_message = ?
            WHERE id = ?
            """,
            (_now(), rows_fetched, rows_written, rows_deleted, error_message, sync_run_id),
        )


def get_sync_runs(limit: int = 100) -> list[dict]:
    """Return recent sync-stage records, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
