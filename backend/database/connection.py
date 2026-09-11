from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).parent.parent
_DB_PATH = _BACKEND_ROOT / "data" / "youtube.db"
_SCHEMA_PATH = _BACKEND_ROOT / "schema.sql"

_MONTH_PREFIX_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])")


def _now() -> str:
    """Return the current time as a timezone-aware UTC ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _month_bound_conditions(alias: str, start_date: str | None, end_date: str | None) -> tuple[list[str], list]:
    """Build `{alias}.month >=/<=` conditions from date-string bounds. A missing bound
    is unbounded on that side, matching how every other date-filtered query in this
    codebase (e.g. traffic_sources, analytics) treats a missing start/end date.

    A *supplied* bound that doesn't start with a valid `YYYY-MM` prefix is malformed —
    e.g. `"2026"` would otherwise slice to the literal string `"2026"`, which sorts
    lexically **before** every real `"2026-MM"` month and so would match everything
    from 2026 onward instead of matching nothing. A malformed bound therefore forces an
    always-false condition (`0`) so the query returns no rows rather than an
    unintended broad match, without rejecting the request outright.

    Shared by every monthly-storage table (search_terms, related_videos) since each
    query's own table alias differs; callers own their alias.
    """
    conditions = []
    params: list = []
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


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory and foreign key enforcement set."""
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db() -> None:
    """Create tables from schema.sql if they don't exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema)
