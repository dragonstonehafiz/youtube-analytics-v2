from __future__ import annotations

from .connection import _now, get_connection


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


def get_last_successful_batch_completed_at(sync_types: tuple[str, ...]) -> str | None:
    """Return the latest completion time for a batch where all expected sync types succeeded.

    A batch qualifies only if every sync_type in `sync_types` appears in that batch_id and
    none of those rows has a non-success status (failed or still running disqualifies the
    whole batch, even if another row for the same sync_type in the batch did succeed).
    Returns None if no batch qualifies.
    """
    if not sync_types:
        return None
    placeholders = ",".join("?" * len(sync_types))
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT MAX(batches.completed_at) AS completed_at
            FROM (
                SELECT sr.batch_id AS batch_id, MAX(sr.completed_at) AS completed_at
                FROM sync_runs sr
                WHERE sr.sync_type IN ({placeholders})
                GROUP BY sr.batch_id
                HAVING COUNT(DISTINCT sr.sync_type) = ?
                   AND SUM(CASE WHEN sr.status <> 'success' THEN 1 ELSE 0 END) = 0
            ) batches
            """,
            [*sync_types, len(sync_types)],
        ).fetchone()
    return row["completed_at"] if row else None
