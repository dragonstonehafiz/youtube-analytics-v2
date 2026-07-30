from __future__ import annotations

import threading
from datetime import date, datetime

import database

from .orchestration import run_plan
from .plans import FULL_SYNC_TYPES, full_incremental_plan


def synced_today() -> bool:
    """Return whether a complete pipeline run already succeeded today (local date).

    The checkpoint is derived from sync_runs alone: the latest batch in which every stage
    in FULL_SYNC_TYPES succeeded under one batch_id. A partial plan, or a batch with a
    failed or still-running stage, does not qualify — so the next launch still syncs.
    Missing or unparseable timestamps count as not-synced.
    """
    completed_at = database.get_last_successful_batch_completed_at(FULL_SYNC_TYPES)
    if not completed_at:
        return False
    try:
        last_date = datetime.fromisoformat(completed_at).astimezone().date()
    except ValueError:
        return False
    return last_date >= date.today()


def start_background_scheduler() -> None:
    """Run one complete incremental sync on startup unless today's already succeeded.

    Called once from the app lifespan. There is no recurring timer: the app is not
    expected to stay running long enough for one to fire, so freshness is decided per
    launch. Restarting after a complete sync on the same local date does nothing.
    """
    if synced_today():
        return

    def _run() -> None:
        run_plan(full_incremental_plan())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
