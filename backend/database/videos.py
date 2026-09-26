from __future__ import annotations

from datetime import date, timedelta

from .connection import _now, get_connection


def _coerce_own(row: dict) -> dict:
    """Convert a selected SQLite ownership value to a Python bool."""
    if "own" in row:
        row["own"] = bool(row["own"])
    return row


def _upsert_video_row(video: dict, *, own: bool) -> None:
    """Upsert a video while preserving known content type and owned status."""
    row = {**video, "own": int(own), "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO videos (id, channel_id, title, description, published_at, duration_seconds,
                thumbnail_url, content_type, privacy_status, view_count, like_count, comment_count,
                own, updated_at)
            VALUES (:id, :channel_id, :title, :description, :published_at, :duration_seconds,
                :thumbnail_url, :content_type, :privacy_status, :view_count, :like_count, :comment_count,
                :own, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                channel_id = excluded.channel_id,
                title = excluded.title,
                description = excluded.description,
                published_at = excluded.published_at,
                duration_seconds = excluded.duration_seconds,
                thumbnail_url = excluded.thumbnail_url,
                content_type = COALESCE(excluded.content_type, content_type),
                privacy_status = excluded.privacy_status,
                view_count = excluded.view_count,
                like_count = excluded.like_count,
                comment_count = excluded.comment_count,
                own = MAX(own, excluded.own),
                updated_at = excluded.updated_at
            """,
            row,
        )


def upsert_own_video(video: dict) -> None:
    """Upsert a confirmed channel-owned video."""
    _upsert_video_row(video, own=True)


def upsert_related_video(video: dict, *, own: bool) -> None:
    """Upsert a Related Video referrer's metadata without downgrading ownership."""
    _upsert_video_row(video, own=own)


VIDEO_SORT_COLUMNS = {"published_at", "view_count", "comment_count", "total_revenue_sgd"}

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
    col = sort_by if sort_by in VIDEO_SORT_COLUMNS else "published_at"
    direction = "ASC" if sort_dir == "asc" else "DESC"
    offset = (page - 1) * page_size

    conditions: list[str] = ["v.own = 1"]
    params: list[object] = []
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
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
    return [_coerce_own(dict(r)) for r in rows], total


def get_owned_video(video_id: str) -> dict | None:
    """Return an owned video with lifetime SGD revenue, or None."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT v.*,
                COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS total_revenue_sgd,
                COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS total_watch_time_hours
            FROM videos v
            LEFT JOIN video_analytics va ON va.video_id = v.id
            LEFT JOIN fx_rates fx ON fx.date = va.date
            WHERE v.id = ? AND v.own = 1
            GROUP BY v.id
            """,
            (video_id,),
        ).fetchone()
    return _coerce_own(dict(row)) if row else None


def get_videos_published(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    playlist_id: str | None = None,
    title: str | None = None,
) -> list[dict]:
    """Return id, title, published_at, thumbnail_url for owned videos matching filters, ordered by published_at."""
    conditions = ["v.own = 1"]
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
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
        params.append(f"%{title}%")
    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, title, published_at, thumbnail_url, content_type FROM videos v WHERE {where} ORDER BY v.published_at",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_earliest_published_year() -> int | None:
    """Return the year of the earliest owned video's published_at, or None if empty."""
    with get_connection() as conn:
        video_min = conn.execute("SELECT MIN(published_at) FROM videos WHERE own = 1").fetchone()[0]
    return int(video_min[:4]) if video_min else None


def get_owned_video_ids(published_through: str | None = None) -> list[str]:
    """Return owned video IDs oldest first, optionally published through a date."""
    conditions = ["own = 1"]
    params: list[str] = []
    if published_through is not None:
        exclusive_upper = date.fromisoformat(published_through) + timedelta(days=1)
        conditions.append("(published_at IS NULL OR published_at < ?)")
        params.append(f"{exclusive_upper.isoformat()}T00:00:00")
    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id FROM videos WHERE {where}
            ORDER BY (published_at IS NULL), published_at ASC, id ASC
            """,
            params,
        ).fetchall()
    return [r["id"] for r in rows]


def get_all_video_ids() -> list[str]:
    """Return every known video ID regardless of ownership."""
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
    """Return filtered channel video statistics split into Legacy and New groups."""
    conditions: list[str] = ["v.own = 1"]
    params: list[object] = []
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
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
            SELECT MIN(va.date), MAX(va.date) FROM video_analytics va
            JOIN videos v ON v.id = va.video_id AND v.own = 1
            """
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


def get_playlist_video_stats(
    playlist_id: str,
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> dict:
    """Return filtered playlist video statistics split into Legacy and New groups."""
    conditions: list[str] = [
        "v.own = 1",
        "v.id IN (SELECT DISTINCT pi.video_id FROM playlist_items pi WHERE pi.playlist_id = ?)",
    ]
    params: list[object] = [playlist_id]
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
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
            JOIN videos v ON v.id = va.video_id AND v.own = 1
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
    """Delete owned videos absent from the given IDs and return the number deleted."""
    with get_connection() as conn:
        if not ids:
            cursor = conn.execute("DELETE FROM videos WHERE own = 1")
        else:
            placeholders = ",".join("?" * len(ids))
            cursor = conn.execute(f"DELETE FROM videos WHERE own = 1 AND id NOT IN ({placeholders})", ids)
        return cursor.rowcount
