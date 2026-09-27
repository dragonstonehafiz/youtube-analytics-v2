from __future__ import annotations

from .connection import get_connection


# Worst-first. A batch reports the most severe status among its stages.
_BATCH_STATUS_PRECEDENCE = ("failed", "incomplete", "running", "cancelled", "success")


def _batch_status(runs: list[dict]) -> str:
    """Return the batch's overall status: failed > incomplete > running > cancelled > success."""
    present = {run["status"] for run in runs}
    for status in _BATCH_STATUS_PRECEDENCE:
        if status in present:
            return status
    # An unrecognized stored status must never be reported as a success.
    return next(iter(present), "success")


def get_sync_runs(page: int = 1, page_size: int = 25) -> tuple[list[dict], int]:
    """Return a page of newest-first sync batches and the total batch count."""
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
