from __future__ import annotations

from .connection import get_connection


def delete_videos_not_in(ids: list[str]) -> int:
    """Delete owned videos absent from the given IDs and return the number deleted."""
    with get_connection() as conn:
        if not ids:
            cursor = conn.execute("DELETE FROM videos WHERE own = 1")
        else:
            placeholders = ",".join("?" * len(ids))
            cursor = conn.execute(f"DELETE FROM videos WHERE own = 1 AND id NOT IN ({placeholders})", ids)
        return cursor.rowcount
