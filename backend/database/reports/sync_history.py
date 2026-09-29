"""Paginated sync batch history with per-batch stage runs and overall status."""

from __future__ import annotations

from collections.abc import Iterable

from .. import reader
from ..dataclasses import SyncRun
from ..reader import Query

# Worst-first. A batch reports the most severe status among its stored stages.
_BATCH_STATUS_PRECEDENCE = ("failed", "incomplete", "running", "cancelled", "success")


def _batch_status(statuses: Iterable[str]) -> str:
    """Return a stored batch's overall status: failed > incomplete > running > cancelled > success."""
    present = set(statuses)
    for status in _BATCH_STATUS_PRECEDENCE:
        if status in present:
            return status
    # An unrecognized stored status must never be reported as a success.
    return next(iter(present), "success")


def sync_batches(*, page: int, page_size: int) -> dict:
    """One page of batches newest first by earliest stage start, each with its runs, and the batch count."""
    count_query = Query("SELECT COUNT(DISTINCT batch_id) FROM sync_runs")
    page_query = Query(
        """
        SELECT batch_id, MIN(started_at) AS started_at
        FROM sync_runs
        GROUP BY batch_id
        ORDER BY started_at DESC, batch_id DESC
        LIMIT ? OFFSET ?
        """,
        (page_size, (page - 1) * page_size),
    )
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        batches = reader.fetch(SyncRun, page_query, conn=conn)
        batch_ids = [batch.batch_id for batch in batches]
        # An empty page skips the stage read.
        runs = reader.select(
            SyncRun, where=[("batch_id", "IN", batch_ids)], order_by=("-started_at", "-id"), conn=conn
        ) if batch_ids else []
    stages = reader.group_by(runs, "batch_id")
    items = []
    for batch in batches:
        batch_runs = stages.get(batch.batch_id, [])
        items.append({
            "batch_id": batch.batch_id,
            "started_at": batch.started_at,
            "run_count": len(batch_runs),
            "rows_fetched": sum(run.rows_fetched or 0 for run in batch_runs),
            "rows_written": sum(run.rows_written or 0 for run in batch_runs),
            "rows_deleted": sum(run.rows_deleted or 0 for run in batch_runs),
            "runs": [run.to_dict() for run in batch_runs],
            "status": _batch_status(run.status or "" for run in batch_runs),
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}
