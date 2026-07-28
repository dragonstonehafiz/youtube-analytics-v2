from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_ROOT = Path(__file__).parent.parent
_DB_PATH = _BACKEND_ROOT / "data" / "youtube.db"
_SCHEMA_PATH = _BACKEND_ROOT / "schema.sql"


def _now() -> str:
    """Return the current time as a timezone-aware UTC ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


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
