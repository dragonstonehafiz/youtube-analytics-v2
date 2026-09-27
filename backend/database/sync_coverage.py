from __future__ import annotations

from collections.abc import Collection

from .connection import _now, get_connection


def upsert_coverage(collector: str, video_id: str, period_keys: Collection[str]) -> int:
    """Mark monthly periods complete and return the number upserted."""
    keys = list(period_keys)
    if not keys:
        return 0
    completed_at = _now()
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO sync_coverage (collector, video_id, period_key, completed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(collector, video_id, period_key) DO UPDATE SET
                completed_at = excluded.completed_at
            """,
            [(collector, video_id, key, completed_at) for key in keys],
        )
    return len(keys)
