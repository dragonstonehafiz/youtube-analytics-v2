from __future__ import annotations

import threading
from datetime import datetime, time

import database

from .orchestration import FULL_SYNC_TYPES, run_sync


def _scheduler_loop() -> None:
    """Run sync immediately, then repeat every 24 hours."""
    run_sync()
    timer = threading.Timer(86400, _scheduler_loop)
    timer.daemon = True
    timer.start()


def start_background_scheduler() -> None:
    """Start the background sync scheduler. Call once on app startup.

    If the latest successful full-pipeline batch (all five stages in FULL_SYNC_TYPES
    succeeded under one batch_id) completed within the last 24 hours (by local calendar
    date), skip the immediate sync and schedule the next one for the remaining time in
    the 24h window. This avoids re-syncing on every dev-server reload.
    """
    completed_at = database.get_last_successful_batch_completed_at(FULL_SYNC_TYPES)

    delay = 0.0
    if completed_at:
        try:
            last_date = datetime.fromisoformat(completed_at).astimezone().date()
            last_midnight = datetime.combine(last_date, time.min)
            elapsed = (datetime.now() - last_midnight).total_seconds()
            if elapsed < 86400:
                delay = 86400 - elapsed
        except ValueError:
            pass

    def _start(d: float) -> None:
        if d > 0:
            timer = threading.Timer(d, _scheduler_loop)
            timer.daemon = True
            timer.start()
        else:
            thread = threading.Thread(target=_scheduler_loop, daemon=True)
            thread.start()

    _start(delay)
