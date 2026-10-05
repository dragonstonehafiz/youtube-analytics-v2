from __future__ import annotations

from fastapi import APIRouter

from database import Video, reader

router = APIRouter()


@router.get("/meta/date-range")
def get_date_range() -> dict:
    """Return the earliest published year across videos."""
    earliest = reader.scalar(Video, "MIN", "published_at", where=[("own", "=", True)])
    return {"earliest_year": int(earliest[:4]) if earliest else None}
