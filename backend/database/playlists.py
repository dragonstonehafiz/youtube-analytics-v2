from __future__ import annotations

from .connection import _now, get_connection
from .videos import VIDEO_SORT_COLUMNS


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
    col = sort_by if sort_by in VIDEO_SORT_COLUMNS else "published_at"
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
