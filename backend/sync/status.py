from __future__ import annotations

import threading
from typing import Literal, TypedDict

SyncLifecycleState = Literal["idle", "running", "success", "failed"]


class SyncStatus(TypedDict):
    """The public sync status shape returned by `/sync/status`."""

    state: SyncLifecycleState
    message: str


_lock = threading.Lock()
_state: SyncLifecycleState = "idle"
_message: str = ""


def get_sync_status() -> SyncStatus:
    """Return the current sync lifecycle state and its safe message. Thread-safe."""
    with _lock:
        return {"state": _state, "message": _message}


def try_begin_sync(message: str = "") -> bool:
    """Reserve the running state if no sync is already running. Returns whether it was acquired.

    Sets `message` under the same lock acquisition, so a status poll can never observe
    the running state still carrying the previous run's terminal message. A successful
    reservation replaces any retained terminal result.
    """
    global _state, _message
    with _lock:
        if _state == "running":
            return False
        _state = "running"
        _message = message
        return True


def update_sync_progress(message: str) -> None:
    """Update the progress message of the currently running sync.

    No-op if no sync is running, so a stray call cannot fabricate a running state.
    """
    global _message
    with _lock:
        if _state != "running":
            return
        _message = message


def complete_sync(message: str) -> None:
    """Mark the running sync as successfully finished with a safe terminal message."""
    global _state, _message
    with _lock:
        _state = "success"
        _message = message


def fail_sync(message: str) -> None:
    """Mark the running sync as failed with a safe, operation-specific terminal message."""
    global _state, _message
    with _lock:
        _state = "failed"
        _message = message


def reset_sync_status() -> None:
    """Reset to the initial idle state with no message. Intended for test cleanup."""
    global _state, _message
    with _lock:
        _state = "idle"
        _message = ""
