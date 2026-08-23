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


def mark_incomplete_sync_runs() -> int:
    """Mark stages stranded by a previous process as incomplete; return how many changed.

    A row is created just before its stage starts and only leaves 'running' when the stage
    completes or fails, so a process killed mid-sync strands one indefinitely. Call this at
    startup, where the in-memory reservation guarding a real sync is necessarily gone and
    no stage can legitimately still be running — which is what makes the sweep safe. It
    would misclassify live work at any other time. completed_at stays NULL because the
    stage genuinely never completed.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE sync_runs SET status = 'incomplete' WHERE status = 'running'"
        )
        return cursor.rowcount


# Worst-first. A batch reports the most severe status among its stages.
_BATCH_STATUS_PRECEDENCE = ("failed", "incomplete", "running", "success")


def _batch_status(runs: list[dict]) -> str:
    """Return the batch's overall status: failed > incomplete > running > success."""
    present = {run["status"] for run in runs}
    for status in _BATCH_STATUS_PRECEDENCE:
        if status in present:
            return status
    # An unrecognized stored status must never be reported as a success.
    return next(iter(present), "success")


def get_sync_runs(page: int = 1, page_size: int = 25) -> tuple[list[dict], int]:
    """Return one page of sync batches newest first, plus the total distinct batch count.

    A batch is one batch_id — the ID execute_plan() generates once per submitted plan and
    shares across every stage that starts. Paging happens over distinct batch IDs rather
    than stage rows, so a batch is never split across two pages and a group's rolled-up
    counters always cover all of its stages. Each group is
    {batch_id, started_at, status, run_count, rows_fetched, rows_written, rows_deleted,
    runs}, where started_at is the batch's earliest stage start, status is the worst stage
    status in the batch, and the three counters are summed from exactly the child rows in
    `runs`.
    """
    offset = (page - 1) * page_size
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(DISTINCT sr.batch_id) FROM sync_runs sr").fetchone()[0]
        batch_rows = conn.execute(
            """
            SELECT sr.batch_id, MIN(sr.started_at) AS started_at
            FROM sync_runs sr
            GROUP BY sr.batch_id
            ORDER BY started_at DESC, sr.batch_id DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()

        # A page past the end selects no batches; an empty IN () list is invalid SQL.
        if not batch_rows:
            return [], total

        batch_ids = [row["batch_id"] for row in batch_rows]
        placeholders = ",".join("?" * len(batch_ids))
        child_rows = conn.execute(
            f"""
            SELECT sr.id, sr.batch_id, sr.sync_type, sr.scope, sr.year, sr.status,
                   sr.started_at, sr.completed_at, sr.rows_fetched, sr.rows_written,
                   sr.rows_deleted, sr.error_message
            FROM sync_runs sr
            WHERE sr.batch_id IN ({placeholders})
            ORDER BY sr.started_at DESC, sr.id DESC
            """,
            batch_ids,
        ).fetchall()

    # Seeded in batch-page order, so the returned groups keep the newest-first ordering.
    groups: dict[str, dict] = {
        row["batch_id"]: {
            "batch_id": row["batch_id"],
            "started_at": row["started_at"],
            "run_count": 0,
            "rows_fetched": 0,
            "rows_written": 0,
            "rows_deleted": 0,
            "runs": [],
        }
        for row in batch_rows
    }
    for child in child_rows:
        group = groups[child["batch_id"]]
        group["runs"].append(dict(child))
        group["run_count"] += 1
        group["rows_fetched"] += child["rows_fetched"]
        group["rows_written"] += child["rows_written"]
        group["rows_deleted"] += child["rows_deleted"]
    for group in groups.values():
        group["status"] = _batch_status(group["runs"])
    return list(groups.values()), total


def get_last_successful_run_completed_at() -> str | None:
    """Return the completion time of the most recent successful sync run of any type.

    A single succeeded stage qualifies — the run's sync_type, scope, and batch_id do not
    matter, and other stages in the same batch may have failed or never run. Only
    status = 'success' is considered, so failed, still-running, and incomplete rows are all
    ignored. Returns None when no run has ever succeeded.
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
