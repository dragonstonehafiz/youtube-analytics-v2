"""Shared scope, date and limit SQL fragments for report queries."""

from __future__ import annotations

import re
from collections.abc import Collection

_MONTH_PREFIX_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])")


def video_conditions(
    *,
    video_ids: Collection[str] | None = None,
    title: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
) -> tuple[list[str], list[object]]:
    """Return owned-video conditions for alias `v`; an empty ID scope matches nothing."""
    conditions: list[str] = ["v.own = 1"]
    params: list[object] = []
    if video_ids is not None:
        ids = list(dict.fromkeys(video_ids))
        conditions.append(f"v.id IN ({','.join('?' * len(ids))})" if ids else "0")
        params.extend(ids)
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.extend([f"%{title}%", f"%{title}%"])
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    return conditions, params


def published_bounds(column: str, start_date: str | None, end_date: str | None) -> tuple[list[str], list[object]]:
    """Return inclusive calendar-date bounds on an ISO timestamp column."""
    conditions: list[str] = []
    params: list[object] = []
    if start_date:
        conditions.append(f"{column} >= ?")
        params.append(start_date)
    if end_date:
        conditions.append(f"{column} <= ?")
        params.append(end_date + "T23:59:59")
    return conditions, params


def date_bounds(column: str, start_date: str | None, end_date: str | None) -> tuple[list[str], list[object]]:
    """Return inclusive bounds on a YYYY-MM-DD date column."""
    conditions: list[str] = []
    params: list[object] = []
    if start_date:
        conditions.append(f"{column} >= ?")
        params.append(start_date)
    if end_date:
        conditions.append(f"{column} <= ?")
        params.append(end_date)
    return conditions, params


def month_bounds(alias: str, start_date: str | None, end_date: str | None) -> tuple[list[str], list[object]]:
    """Return inclusive month bounds on `<alias>.month`; a malformed bound matches nothing."""
    conditions: list[str] = []
    params: list[object] = []
    if start_date:
        if _MONTH_PREFIX_RE.match(start_date):
            conditions.append(f"{alias}.month >= ?")
            params.append(start_date[:7])
        else:
            conditions.append("0")
    if end_date:
        if _MONTH_PREFIX_RE.match(end_date):
            conditions.append(f"{alias}.month <= ?")
            params.append(end_date[:7])
        else:
            conditions.append("0")
    return conditions, params


def limit_clause(limit: int | None) -> tuple[str, list[object]]:
    """Return an optional LIMIT clause and its parameter."""
    return ("LIMIT ?", [limit]) if limit is not None else ("", [])
