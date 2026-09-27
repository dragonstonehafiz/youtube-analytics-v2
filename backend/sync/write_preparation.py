"""Pure validation of monthly insight payloads into row objects; nothing here touches the database."""

from __future__ import annotations

import re
from collections.abc import Sequence

from database import RelatedVideo, SearchTerm

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _positive_totals(rows: Sequence[dict], key: str, month: str) -> dict[str, int]:
    """Validate the month and every row, sum views per key, and keep keys with positive totals."""
    if not _MONTH_RE.match(month):
        raise ValueError(f"invalid month {month!r}; expected YYYY-MM")
    totals: dict[str, int] = {}
    for row in rows:
        value = row[key]
        views = row["views"]
        if not isinstance(value, str) or not value:
            raise ValueError(f"invalid {key} in response row: {row!r}")
        if not isinstance(views, int) or isinstance(views, bool):
            raise ValueError(f"invalid views in response row: {row!r}")
        totals[value] = totals.get(value, 0) + views
    return {value: views for value, views in totals.items() if views > 0}


def search_term_rows(video_id: str, month: str, terms: Sequence[dict], *, updated_at: str) -> list[SearchTerm]:
    """Return one SearchTerm per distinct term with positive summed views for a video's month."""
    return [
        SearchTerm(video_id=video_id, month=month, search_term=term, views=views, updated_at=updated_at)
        for term, views in _positive_totals(terms, "search_term", month).items()
    ]


def related_video_rows(
    target_video_id: str, month: str, referrers: Sequence[dict], *, updated_at: str
) -> list[RelatedVideo]:
    """Return one RelatedVideo per distinct referrer with positive summed views for a target's month."""
    return [
        RelatedVideo(
            target_video_id=target_video_id, month=month, referrer_video_id=referrer, views=views,
            updated_at=updated_at,
        )
        for referrer, views in _positive_totals(referrers, "referrer_video_id", month).items()
    ]
