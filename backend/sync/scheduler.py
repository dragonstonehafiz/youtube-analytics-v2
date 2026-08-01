from __future__ import annotations

import threading
from datetime import date, datetime

import database

from .orchestration import run_plan
from .plans import full_incremental_plan


def synced_today() -> bool:
    """Return whether any sync stage already succeeded today (local date).

    The checkpoint is derived from sync_runs alone: the most recent successful run of any
    sync_type. A single-stage manual plan counts, so a manual sync of one type suppresses
    that day's startup sync. Failed and still-running rows are ignored, and missing or
    unparseable timestamps count as not-synced.
    """
    completed_at = database.get_last_successful_run_completed_at()
    if not completed_at:
        return False
    try:
        last_date = datetime.fromisoformat(completed_at).astimezone().date()
    except ValueError:
        return False
    return last_date >= date.today()


def start_background_scheduler() -> None:
    """Run one complete incremental sync on startup unless any sync already succeeded today.

    Called once from the app lifespan. There is no recurring timer: the app is not
    expected to stay running long enough for one to fire, so freshness is decided per
    launch. Restarting after any successful sync on the same local date does nothing.
    """
    if synced_today():
        return

    def _run() -> None:
        run_plan(full_incremental_plan())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
