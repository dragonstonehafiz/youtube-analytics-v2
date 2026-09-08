#!/usr/bin/env python3
"""One-time migration: add videos.own to a database created before Issue 48.

Fresh databases already get this column from schema.sql via init_db(). This
script is only for an existing database whose videos table predates the
column; it adds `own INTEGER NOT NULL DEFAULT 1 CHECK (own IN (0, 1))` and
leaves every existing row owned (own=1). Safe to run more than once — it is a
no-op once the column exists.

Usage:
    cd backend && .venv/Scripts/python.exe scripts/issue-48-migration.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import get_connection  # noqa: E402


def migrate(conn: sqlite3.Connection) -> bool:
    """Add videos.own if missing. Returns True if the column was added."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(videos)")}
    if "own" in columns:
        return False
    conn.execute("ALTER TABLE videos ADD COLUMN own INTEGER NOT NULL DEFAULT 1 CHECK (own IN (0, 1))")
    return True


def main() -> None:
    with get_connection() as conn:
        added = migrate(conn)
    print("Added videos.own (existing rows set to own=1)." if added else "videos.own already present; no change made.")


if __name__ == "__main__":
    main()
