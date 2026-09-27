from __future__ import annotations

from .connection import get_connection


def delete_orphan_comment_authors() -> int:
    """Delete unreferenced comment authors and return the number deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM comment_authors
            WHERE NOT EXISTS (
                SELECT 1 FROM comments WHERE comments.author_id = comment_authors.id
            )
            """
        )
        return cursor.rowcount
