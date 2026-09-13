from __future__ import annotations

from collections.abc import Collection

from .connection import _now, get_connection


def get_covered_periods(collector: str, video_id: str, start_key: str, end_key: str) -> set[str]:
    """Return the YYYY-MM period_keys already marked complete for one video/collector
    within an inclusive [start_key, end_key] range."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT sc.period_key
            FROM sync_coverage sc
            WHERE sc.collector = ? AND sc.video_id = ?
              AND sc.period_key >= ? AND sc.period_key <= ?
            """,
            (collector, video_id, start_key, end_key),
        ).fetchall()
    return {row["period_key"] for row in rows}


def upsert_coverage(collector: str, video_id: str, period_keys: Collection[str]) -> int:
    """Mark one or many YYYY-MM periods complete for one video/collector, refreshing
    completed_at on an already-complete period. Returns the number of periods upserted.
    Callers must only pass periods whose request/response fully succeeded.
    """
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
