from __future__ import annotations

import threading
from datetime import date, datetime

import database

from .orchestration import run_plan
from .plans import full_incremental_plan


def synced_today() -> bool:
    """Return whether any sync stage succeeded on the current local date."""
    completed_at = database.get_last_successful_run_completed_at()
    if not completed_at:
        return False
    try:
        last_date = datetime.fromisoformat(completed_at).astimezone().date()
    except ValueError:
        return False
    return last_date >= date.today()


def start_background_scheduler() -> None:
    """Run an incremental startup sync unless one already succeeded today."""
    if synced_today():
        return

    def _run() -> None:
        run_plan(full_incremental_plan())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
