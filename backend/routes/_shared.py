from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def require_found(item: T | None, resource: str) -> T:
    """Return the item, or raise 404 "<resource> not found" when it is None."""
    if item is None:
        raise HTTPException(status_code=404, detail=f"{resource} not found")
    return item
