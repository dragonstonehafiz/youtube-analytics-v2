from __future__ import annotations

from fastapi import APIRouter

import database

router = APIRouter()


@router.get("/meta/date-range")
def get_date_range() -> dict:
    """Return the earliest published year across videos."""
    return {"earliest_year": database.get_earliest_published_year()}
