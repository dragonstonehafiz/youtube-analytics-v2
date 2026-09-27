from __future__ import annotations

import threading
from collections.abc import Iterable, Sequence
from typing import Literal, TypedDict

SyncStageState = Literal["pending", "running", "success", "failed", "cancelled"]


# Worst-first. A batch reports the most severe status among its stored stages.
_BATCH_STATUS_PRECEDENCE = ("failed", "incomplete", "running", "cancelled", "success")


def batch_status(statuses: Iterable[str]) -> str:
    """Return a stored batch's overall status: failed > incomplete > running > cancelled > success."""
    present = set(statuses)
    for status in _BATCH_STATUS_PRECEDENCE:
        if status in present:
            return status
    # An unrecognized stored status must never be reported as a success.
    return next(iter(present), "success")


class SyncStageStatus(TypedDict):
    """One selected stage's independent lifecycle and safe progress message."""

    key: str
    state: SyncStageState
    message: str


class SyncStatus(TypedDict):
    """The public per-stage sync status shape returned by `/sync/status`."""

    active: bool
    stop_requested: bool
    stages: list[SyncStageStatus]


class SyncCancelled(Exception):
    """Raised by `raise_if_stopping()` to unwind the active sync at a safe checkpoint."""


_lock = threading.Lock()
_active = False
_stop_requested = False
_stages: dict[str, SyncStageStatus] = {}


def get_sync_status() -> SyncStatus:
    """Return a thread-safe snapshot of reservation and per-stage status."""
    with _lock:
        stages: list[SyncStageStatus] = []
        for stage in _stages.values():
            stages.append({
                "key": stage["key"],
                "state": stage["state"],
                "message": stage["message"],
            })
        return {"active": _active, "stop_requested": _stop_requested, "stages": stages}


def try_begin_sync(stage_keys: Sequence[str] = ()) -> bool:
    """Reserve a sync and seed its selected stages as pending, if none is active."""
    global _active, _stop_requested, _stages
    with _lock:
        if _active:
            return False
        _active = True
        _stop_requested = False
        _stages = {
            key: {"key": key, "state": "pending", "message": ""}
            for key in stage_keys
        }
        return True


def update_sync_progress(stage_key: str, message: str) -> None:
    """Mark a selected stage running and update its safe progress message."""
    with _lock:
        if not _active or stage_key not in _stages:
            return
        _stages[stage_key]["state"] = "running"
        _stages[stage_key]["message"] = message


def complete_stage(stage_key: str) -> None:
    """Record a completed stage as successful or cancelled when stopping."""
    with _lock:
        if not _active or stage_key not in _stages:
            return
        _stages[stage_key]["state"] = "cancelled" if _stop_requested else "success"
        _stages[stage_key]["message"] = ""


def cancel_stage(stage_key: str) -> None:
    """Record cooperative cancellation for one selected stage."""
    with _lock:
        if not _active or stage_key not in _stages:
            return
        _stages[stage_key]["state"] = "cancelled"
        _stages[stage_key]["message"] = ""


def fail_stage(stage_key: str, label: str) -> None:
    """Record one stage's fixed, safe failure message."""
    with _lock:
        if not _active or stage_key not in _stages:
            return
        _stages[stage_key]["state"] = "failed"
        _stages[stage_key]["message"] = f"{label} failed"


def request_stop() -> bool:
    """Request idempotent cancellation of the active sync reservation."""
    global _stop_requested
    with _lock:
        if not _active:
            return False
        _stop_requested = True
        return True


def raise_if_stopping() -> None:
    """Raise `SyncCancelled` when cancellation was requested at a safe checkpoint."""
    with _lock:
        if _stop_requested:
            raise SyncCancelled()


def finish_sync() -> None:
    """Cancel any unstarted stages after an accepted stop and release the reservation."""
    global _active
    with _lock:
        if _stop_requested:
            for stage in _stages.values():
                if stage["state"] == "pending":
                    stage["state"] = "cancelled"
        _active = False


def reset_sync_status() -> None:
    """Reset reservation and stage data. Intended for test cleanup."""
    global _active, _stop_requested, _stages
    with _lock:
        _active = False
        _stop_requested = False
        _stages = {}
