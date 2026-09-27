from __future__ import annotations

from .connection import get_connection


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
