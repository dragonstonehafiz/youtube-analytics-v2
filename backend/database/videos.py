from __future__ import annotations

from .connection import _now, get_connection


def upsert_video(video: dict) -> None:
    """Insert or replace a video row.

    `content_type` may be None when the sync stage could not safely classify the
    video (e.g. Shorts pagination was truncated); on conflict this preserves the
    row's existing classification instead of overwriting it with NULL.
    """
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
                content_type = COALESCE(excluded.content_type, content_type),
                privacy_status = excluded.privacy_status,
                view_count = excluded.view_count,
                like_count = excluded.like_count,
                comment_count = excluded.comment_count,
                updated_at = excluded.updated_at
            """,
            row,
        )


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
