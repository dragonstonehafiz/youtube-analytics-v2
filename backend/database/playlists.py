from __future__ import annotations

from .connection import _now, get_connection


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


def delete_playlists_not_in(ids: list[str]) -> int:
    """Delete playlists absent from the given IDs and return the number deleted."""
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
