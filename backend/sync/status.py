from __future__ import annotations

import threading

_lock = threading.Lock()
_is_syncing: bool = False
_message: str = ""


def get_status() -> dict:
    """Return current sync status. Safe to call from any thread."""
    with _lock:
        return {"is_syncing": _is_syncing, "message": _message}


def is_syncing() -> bool:
    """Return True if a sync is currently running."""
    with _lock:
        return _is_syncing


def set_message(msg: str) -> None:
    """Update the current sync message."""
    global _message
    with _lock:
        _message = msg


def try_start() -> bool:
    """Mark a sync as in-progress if one isn't already running. Returns whether it was acquired."""
    global _is_syncing
    with _lock:
        if _is_syncing:
            return False
        _is_syncing = True
        return True


def finish() -> None:
    """Mark the current sync as no longer in-progress."""
    global _is_syncing
    with _lock:
        _is_syncing = False
