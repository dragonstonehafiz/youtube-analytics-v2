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


def get_sync_runs(page: int = 1, page_size: int = 25) -> tuple[list[dict], int]:
    """Return one page of sync-stage records newest first, plus the unfiltered total.

    Rows are ordered by started_at descending with a descending ID tie-breaker so stages
    started within the same timestamp keep a stable order across page requests.
    """
    offset = (page - 1) * page_size
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0]
        rows = conn.execute(
            """
            SELECT * FROM sync_runs
            ORDER BY started_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
    return [dict(r) for r in rows], total


def get_last_successful_run_completed_at() -> str | None:
    """Return the completion time of the most recent successful sync run of any type.

    A single succeeded stage qualifies — the run's sync_type, scope, and batch_id do not
    matter, and other stages in the same batch may have failed or never run. Failed and
    still-running rows are ignored. Returns None when no run has ever succeeded.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(sr.completed_at) AS completed_at
            FROM sync_runs sr
            WHERE sr.status = 'success'
            """
        ).fetchone()
    return row["completed_at"] if row else None
