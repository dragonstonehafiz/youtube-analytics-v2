from __future__ import annotations

import threading
from typing import Literal, TypedDict

SyncLifecycleState = Literal["idle", "running", "stopping", "success", "failed", "cancelled"]


class SyncStatus(TypedDict):
    """The public sync status shape returned by `/sync/status`."""

    state: SyncLifecycleState
    message: str


class SyncCancelled(Exception):
    """Raised by `raise_if_stopping()` to unwind the active sync at a safe checkpoint."""


_lock = threading.Lock()
_state: SyncLifecycleState = "idle"
_message: str = ""


def get_sync_status() -> SyncStatus:
    """Return the current sync lifecycle state and its safe message. Thread-safe."""
    with _lock:
        return {"state": _state, "message": _message}


def try_begin_sync(message: str = "") -> bool:
    """Reserve the running state if no sync is already running or stopping. Returns
    whether it was acquired.

    Sets `message` under the same lock acquisition, so a status poll can never observe
    the running state still carrying the previous run's terminal message. A successful
    reservation replaces any retained terminal result.
    """
    global _state, _message
    with _lock:
        if _state in ("running", "stopping"):
            return False
        _state = "running"
        _message = message
        return True


def update_sync_progress(message: str) -> None:
    """Update the progress message of the currently running sync.

    No-op if no sync is running, so a stray call cannot fabricate a running state and
    cannot overwrite the stopping message once cancellation has been requested.
    """
    global _message
    with _lock:
        if _state != "running":
            return
        _message = message


def request_stop() -> bool:
    """Atomically request cancellation of the active sync. Returns whether a sync is
    active (running or already stopping); False when idle or in a terminal state.

    Idempotent: a second call while already `stopping` returns True without mutating
    the message. Never overwrites a terminal result recorded before this call acquires
    the lock.
    """
    global _state, _message
    with _lock:
        if _state == "running":
            _state = "stopping"
            _message = "Stopping sync..."
            return True
        return _state == "stopping"


def raise_if_stopping() -> None:
    """Raise `SyncCancelled` if cancellation has been requested for the active sync.

    A no-op otherwise. Callers invoke this only between safe work units — never inside
    an in-flight network request or database transaction.
    """
    with _lock:
        if _state == "stopping":
            raise SyncCancelled()


_TERMINAL_STATES = ("success", "failed", "cancelled")


def complete_sync(message: str) -> None:
    """Mark the running sync as successfully finished with a safe terminal message.

    No-op while already terminal, so a completing worker cannot overwrite another
    terminal result recorded first. A caller that never reserved (state still `idle`,
    as in stage-level unit tests) is still allowed through.

    While `stopping`, settles to `cancelled` instead of `success`: a stop request was
    already accepted and acknowledged to the caller, so a plan that finishes its last
    unit of work before its next checkpoint must still resolve to the outcome the user
    was told was happening, not silently report success. This is also what prevents the
    sync from wedging in `stopping` forever when no further checkpoint lies ahead.
    """
    global _state, _message
    with _lock:
        if _state == "stopping":
            _state = "cancelled"
            _message = "Sync stopped"
            return
        if _state in _TERMINAL_STATES:
            return
        _state = "success"
        _message = message


def fail_sync(message: str) -> None:
    """Mark the active sync as failed with a safe, operation-specific terminal message.

    No-op only once a terminal result has already been recorded, preserving whichever
    outcome was decided first. Still allowed while `stopping`, since a genuine error
    during the stopping window is a real failure, not a cancellation.
    """
    global _state, _message
    with _lock:
        if _state in _TERMINAL_STATES:
            return
        _state = "failed"
        _message = message


def cancel_sync(message: str) -> None:
    """Mark the active sync as cancelled with a safe terminal message.

    No-op only once a terminal result has already been recorded, preserving whichever
    outcome was decided first.
    """
    global _state, _message
    with _lock:
        if _state in _TERMINAL_STATES:
            return
        _state = "cancelled"
        _message = message


def reset_sync_status() -> None:
    """Reset to the initial idle state with no message. Intended for test cleanup."""
    global _state, _message
    with _lock:
        _state = "idle"
        _message = ""
