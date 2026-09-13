from __future__ import annotations

import sqlite3
from collections.abc import Collection
from datetime import date, timedelta

from .connection import _now, get_connection


def upsert_video_traffic_source(row: dict) -> None:
    """Insert or replace a daily video traffic source row."""
    row = {**row, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO video_traffic_sources (video_id, date, traffic_source_type,
                views, watch_time_minutes, updated_at)
            VALUES (:video_id, :date, :traffic_source_type, :views, :watch_time_minutes, :updated_at)
            ON CONFLICT(video_id, date, traffic_source_type) DO UPDATE SET
                views = excluded.views,
                watch_time_minutes = excluded.watch_time_minutes,
                updated_at = excluded.updated_at
            """,
            row,
        )


def get_last_traffic_source_date(video_id: str) -> str | None:
    """Return the most recent date we have traffic sources for a video, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS last_date FROM video_traffic_sources WHERE video_id = ?",
            (video_id,),
        ).fetchone()
    return row["last_date"] if row else None


def _zero_fill_traffic_sources(rows: list[dict], start_date: str | None, end_date: str | None) -> list[dict]:
    """Fill missing (date, traffic_source_type) combinations in the traffic source rows with zero values."""
    if not rows:
        return rows
    types = sorted({r["traffic_source_type"] for r in rows})
    by_key = {(r["date"], r["traffic_source_type"]): r for r in rows}
    real_dates = {r["date"] for r in rows}
    dates = [r["date"] for r in rows]
    first = date.fromisoformat(start_date or min(dates))
    last = date.fromisoformat(end_date or max(dates))
    result = []
    d = first
    while d <= last:
        ds = d.isoformat()
        for t in types:
            result.append(by_key.get((ds, t), {"date": ds, "traffic_source_type": t, "views": 0, "watch_time_minutes": 0}))
        d += timedelta(days=1)
    while result and result[-1]["date"] not in real_dates:
        result.pop()
    return result


def get_video_traffic_sources(
    video_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return daily traffic source rows for an owned video, ordered by date, with
    optional date filters. Returns no rows for an external video."""
    conditions = ["vts.video_id = ?", "v.own = 1"]
    params: list = [video_id]
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)
    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT vts.date, vts.traffic_source_type, vts.views, vts.watch_time_minutes
            FROM video_traffic_sources vts
            JOIN videos v ON v.id = vts.video_id
            WHERE {where}
            ORDER BY vts.date, vts.traffic_source_type
            """,
            params,
        ).fetchall()
    return _zero_fill_traffic_sources([dict(r) for r in rows], start_date, end_date)


def get_aggregated_traffic_sources(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> list[dict]:
    """Return daily traffic sources aggregated across videos, filtered by date range, content_type, privacy_status, and title.

    video_ids scopes the aggregation: None covers every video in the channel, a populated collection
    covers only those videos, and an empty collection returns no rows.
    """
    scoped_ids = None if video_ids is None else list(video_ids)
    if scoped_ids is not None and not scoped_ids:
        return []

    conditions = ["v.own = 1"]
    params: list = []

    if scoped_ids:
        conditions.append(f"v.id IN ({','.join('?' * len(scoped_ids))})")
        params.extend(scoped_ids)
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
        params.append(f"%{title}%")

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                vts.date,
                vts.traffic_source_type,
                SUM(vts.views) AS views,
                SUM(vts.watch_time_minutes) AS watch_time_minutes
            FROM video_traffic_sources vts
            JOIN videos v ON v.id = vts.video_id
            WHERE {where}
            GROUP BY vts.date, vts.traffic_source_type
            ORDER BY vts.date, vts.traffic_source_type
            """,
            params,
        ).fetchall()
    return _zero_fill_traffic_sources([dict(r) for r in rows], start_date, end_date)


def get_top_videos_by_traffic_source(
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    limit: int = 3,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> dict[str, list[dict]]:
    """Return the top N videos by views for each traffic source type, filtered by date range, content_type, privacy_status, and title.

    video_ids scopes the ranking: None covers every video in the channel, a populated collection covers
    only those videos, and an empty collection returns no source groups.
    """
    scoped_ids = None if video_ids is None else list(video_ids)
    if scoped_ids is not None and not scoped_ids:
        return {}

    conditions = ["v.own = 1"]
    params: list = []

    if scoped_ids:
        conditions.append(f"v.id IN ({','.join('?' * len(scoped_ids))})")
        params.extend(scoped_ids)
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)
    if privacy_status:
        conditions.append("v.privacy_status = ?")
        params.append(privacy_status)
    if start_date:
        conditions.append("vts.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("vts.date <= ?")
        params.append(end_date)
    if title:
        conditions.append("(v.title LIKE ? OR v.id LIKE ?)")
        params.append(f"%{title}%")
        params.append(f"%{title}%")

    where = " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                vts.traffic_source_type,
                v.id, v.title, v.thumbnail_url, v.content_type,
                SUM(vts.views) AS views,
                SUM(vts.watch_time_minutes) AS watch_time_minutes
            FROM video_traffic_sources vts
            JOIN videos v ON v.id = vts.video_id
            WHERE {where}
            GROUP BY vts.traffic_source_type, v.id
            ORDER BY vts.traffic_source_type, views DESC
            """,
            params,
        ).fetchall()
    return _top_n_per_source(rows, limit)


def _top_n_per_source(rows: list[sqlite3.Row], limit: int) -> dict[str, list[dict]]:
    """Group video rows by traffic_source_type, keeping only the first N per group (rows must already be sorted by views desc within each type)."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        d = dict(row)
        source_type = d.pop("traffic_source_type")
        bucket = grouped.setdefault(source_type, [])
        if len(bucket) < limit:
            bucket.append(d)
    return grouped
