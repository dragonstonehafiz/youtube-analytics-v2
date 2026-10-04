#!/usr/bin/env python3
"""One-time migration: add and fill stored lifetime earnings on videos and playlists.

Adds `videos.total_revenue_sgd` and `playlists.total_earnings_sgd` when they are missing,
then fills every owned video's total and every playlist's total (summed over its distinct
owned member videos) with `catalog.lifetime_earnings()`. External videos have no analytics,
so they keep the column default of 0. It reads analytics and FX rates but never changes them.

Safe to run more than once: existing columns are kept and totals are recalculated in place.
Column additions and totals commit together or not at all. Run it with the backend stopped.

Usage:
    cd backend && .venv/Scripts/python.exe scripts/lifetime-earnings-migration.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Playlist, Video, writer  # noqa: E402
from database.connection import get_connection, init_db  # noqa: E402
from database.reports import catalog  # noqa: E402

COLUMNS = (("videos", "total_revenue_sgd"), ("playlists", "total_earnings_sgd"))


class MigrationResult(NamedTuple):
    """Columns the run added and how many owned video and playlist totals it recalculated."""

    columns_added: list[str]
    videos: int
    playlists: int


def _add_missing_columns(conn: sqlite3.Connection) -> list[str]:
    """Add each earnings column its table lacks and return the ones added."""
    added = []
    for table, column in COLUMNS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} REAL NOT NULL DEFAULT 0")
            added.append(f"{table}.{column}")
    return added


def migrate() -> MigrationResult:
    """Add missing earnings columns and recalculate every owned video and playlist total."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            added = _add_missing_columns(conn)
            video_ids = [row["id"] for row in conn.execute("SELECT id FROM videos WHERE own = 1")]
            for video_id in video_ids:
                earnings = catalog.lifetime_earnings([video_id])
                writer.update(Video(total_revenue_sgd=earnings), where=[("id", "=", video_id)], conn=conn)
            playlist_ids = [row["id"] for row in conn.execute("SELECT id FROM playlists")]
            for playlist_id in playlist_ids:
                earnings = catalog.lifetime_earnings(catalog.playlist_video_ids(playlist_id))
                writer.update(Playlist(total_earnings_sgd=earnings), where=[("id", "=", playlist_id)], conn=conn)
        except BaseException:
            conn.rollback()
            raise
        conn.commit()
    finally:
        conn.close()
    return MigrationResult(added, len(video_ids), len(playlist_ids))


def main() -> None:
    result = migrate()
    print(f"Columns added: {', '.join(result.columns_added) or 'none'}")
    print(f"Owned videos updated: {result.videos}")
    print(f"Playlists updated: {result.playlists}")


if __name__ == "__main__":
    main()
