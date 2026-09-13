#!/usr/bin/env python3
"""One-time migration: assert every owned video's Analytics coverage complete (Issue 62).

Marks video_analytics, video_traffic_sources, search_insights, and
related_video_insights complete for every calendar month from each owned video's
upload month through the current month, inclusive — an explicit operator baseline
assertion, not an evidence backfill. It reads only `videos.id`, `videos.own`, and
`videos.published_at`, plus the local current date captured once at script start; it
never reads, inserts, updates, or deletes any Analytics reporting table
(video_analytics, video_traffic_sources, search_terms, related_videos).

Coverage created here suppresses only historical backfill. Every Incremental sync
still fetches its mandatory previous/current-month refresh regardless, since that
refresh always overrides coverage state.

Safe to run more than once: reruns produce the identical completion rows via the same
conflict-upsert path normal sync uses. Aborts with no writes if any owned video lacks
a valid published_at.

Usage:
    cd backend && .venv/Scripts/python.exe scripts/issue-62-migration.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import get_connection, init_db  # noqa: E402
from sync.monthly_insights import monthly_windows_for_range  # noqa: E402

COLLECTORS = ("video_analytics", "video_traffic_sources", "search_insights", "related_video_insights")


def _owned_videos(conn: sqlite3.Connection) -> list[dict]:
    """Return every owned video's id and published_at, including any with a missing one."""
    return [dict(row) for row in conn.execute("SELECT id, published_at FROM videos WHERE own = 1")]


def migrate(today: date | None = None) -> dict[str, int]:
    """Mark every owned video complete for all four collectors, from its publish month
    through today's month inclusive. Returns {"owned_videos": N, collector: count, ...}
    with each collector's count being months-marked summed across all owned videos.

    Raises ValueError without writing anything if any owned video lacks a valid
    published_at; `today` defaults to the real current date and is otherwise only for
    deterministic testing.
    """
    today = today or date.today()
    init_db()
    with get_connection() as conn:
        videos = _owned_videos(conn)
        invalid_ids = sorted(video["id"] for video in videos if not video["published_at"])
        if invalid_ids:
            raise ValueError(f"owned videos missing published_at: {invalid_ids}")

        counts = {collector: 0 for collector in COLLECTORS}
        completed_at = datetime.now(timezone.utc).isoformat()
        for video in videos:
            publish_date = date.fromisoformat(video["published_at"][:10])
            months = [window.month for window in monthly_windows_for_range(publish_date, today)]
            for collector in COLLECTORS:
                conn.executemany(
                    """
                    INSERT INTO sync_coverage (collector, video_id, period_key, completed_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(collector, video_id, period_key) DO UPDATE SET
                        completed_at = excluded.completed_at
                    """,
                    [(collector, video["id"], month, completed_at) for month in months],
                )
                counts[collector] += len(months)
    return {"owned_videos": len(videos), **counts}


def main() -> None:
    try:
        result = migrate()
    except ValueError as exc:
        print(f"Aborted: {exc}")
        raise SystemExit(1) from exc

    print(f"Owned videos processed: {result['owned_videos']}")
    for collector in COLLECTORS:
        print(f"  {collector}: {result[collector]} month(s) marked complete")


if __name__ == "__main__":
    main()
