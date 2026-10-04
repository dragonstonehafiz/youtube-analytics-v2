"""Video and playlist listings, details, playlist membership, lifetime earnings and owned-video worklists."""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Sequence
from datetime import date, timedelta

from .. import reader
from ..dataclasses import Playlist, Video
from ..reader import Query, joined_columns
from ..tables import field_names
from ._conditions import published_bounds, video_conditions

_PLAYLIST_TOTAL_VALUES = ("last_item_added", "total_views")

# Lifetime totals a video listing can select, with the SQL that computes each over alias va.
_VIDEO_TOTALS = {
    "total_watch_time_hours": "COALESCE(SUM(va.watch_time_minutes), 0) / 60.0",
}
_DEFAULT_VIDEO_FIELDS = (*field_names(Video), *_VIDEO_TOTALS)

_VIDEO_SORT_COLUMNS = {
    "published_at": "v.published_at",
    "view_count": "v.view_count",
    "comment_count": "v.comment_count",
    "total_revenue_sgd": "v.total_revenue_sgd",
}

_PLAYLIST_SORT_COLUMNS = {
    "published_at": "playlists__published_at",
    "item_count": "playlists__item_count",
    "last_item_added": "last_item_added",
    "total_views": "total_views",
    "total_earnings_sgd": "playlists__total_earnings_sgd",
}

_PLAYLIST_TOTALS_SQL = """
    MAX(v.published_at) AS last_item_added,
    COALESCE(SUM(v.view_count), 0) AS total_views
"""


def _video_items(
    fields: Sequence[str], where: str, params: list[object], sort_by: str, sort_dir: str,
    page_size: int | None, offset: int, conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """Read owned videos as the requested fields, joining analytics only when a computed total is selected or sorted."""
    columns = [name for name in fields if name not in _VIDEO_TOTALS]
    totals = [name for name in fields if name in _VIDEO_TOTALS]
    computed = {*totals, *({sort_by} & _VIDEO_SORT_COLUMNS.keys())} & _VIDEO_TOTALS.keys()
    select = [joined_columns(Video, "v", columns)] if columns else []
    select += [f"{_VIDEO_TOTALS[name]} AS {name}" for name in totals]
    joins = "LEFT JOIN video_analytics va ON va.video_id = v.id" if computed else ""
    order = f"{_VIDEO_SORT_COLUMNS.get(sort_by, 'v.published_at')} {'ASC' if sort_dir == 'asc' else 'DESC'}"
    limit, limit_params = ("LIMIT ? OFFSET ?", [page_size, offset]) if page_size is not None else ("", [])
    query = Query(
        f"""
        SELECT {', '.join(select)}
        FROM videos v
        {joins}
        {where}
        {'GROUP BY v.id' if computed else ''}
        ORDER BY {order} {limit}
        """,
        (*params, *limit_params),
    )
    rows = reader.fetch_joined(query, (Video,), totals, conn=conn)
    items = []
    for row in rows:
        video = row[Video].to_dict(columns)
        items.append({name: video[name] if name in video else row.values[name] for name in fields})
    return items


def video_listing(
    *,
    fields: Sequence[str] | None = None,
    page: int = 1,
    page_size: int | None = 50,
    sort_by: str = "published_at",
    sort_dir: str = "desc",
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    video_ids: Collection[str] | None = None,
) -> dict:
    """Owned videos as the chosen fields (default: all columns and totals); page_size=None returns all, uncounted."""
    selected = _DEFAULT_VIDEO_FIELDS if fields is None else tuple(fields)
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = published_bounds("v.published_at", start_date, end_date)
    where = f"WHERE {' AND '.join([*conditions, *date_conditions])}"
    all_params = [*params, *date_params]
    if page_size is None:
        return {"items": _video_items(selected, where, all_params, sort_by, sort_dir, None, 0)}
    count_query = Query(f"SELECT COUNT(*) FROM videos v {where}", tuple(all_params))
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        items = _video_items(selected, where, all_params, sort_by, sort_dir, page_size, (page - 1) * page_size, conn)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def video_detail(video_id: str) -> dict | None:
    """One owned video with every column and lifetime totals, or None."""
    conditions, params = video_conditions(video_ids=[video_id])
    where = f"WHERE {' AND '.join(conditions)}"
    items = _video_items(_DEFAULT_VIDEO_FIELDS, where, params, "published_at", "desc", 1, 0)
    return items[0] if items else None


def _playlist_base_sql(conditions: list[str]) -> str:
    """Playlists with membership totals under optional conditions on alias `p`."""
    return f"""
        SELECT {joined_columns(Playlist, 'p')}, {_PLAYLIST_TOTALS_SQL}
        FROM playlists p
        LEFT JOIN playlist_items pi ON pi.playlist_id = p.id
        LEFT JOIN videos v ON v.id = pi.video_id AND v.own = 1
        {f"WHERE {' AND '.join(conditions)}" if conditions else ""}
        GROUP BY p.id
    """


def _playlist_items(rows: list[reader.Joined]) -> list[dict]:
    """Serialize playlist rows with their membership totals."""
    return [{**row[Playlist].to_dict(), **row.values} for row in rows]


def playlist_listing(
    *,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "last_item_added",
    sort_dir: str = "desc",
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """One sorted page of playlists with membership totals and the match count."""
    conditions: list[str] = []
    params: list[object] = []
    if title:
        conditions.append("(p.title LIKE ? OR p.id LIKE ?)")
        params.extend([f"%{title}%", f"%{title}%"])
    date_conditions, date_params = published_bounds("p.published_at", start_date, end_date)
    conditions.extend(date_conditions)
    params.extend(date_params)
    base = _playlist_base_sql(conditions)
    order = f"{_PLAYLIST_SORT_COLUMNS.get(sort_by, 'last_item_added')} {'ASC' if sort_dir == 'asc' else 'DESC'}"
    count_query = Query(f"SELECT COUNT(*) FROM ({base})", tuple(params))
    page_query = Query(
        f"SELECT * FROM ({base}) ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, page_size, (page - 1) * page_size),
    )
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        rows = reader.fetch_joined(page_query, (Playlist,), _PLAYLIST_TOTAL_VALUES, conn=conn)
    return {"items": _playlist_items(rows), "total": total, "page": page, "page_size": page_size}


def playlist_detail(playlist_id: str) -> dict | None:
    """One playlist with membership totals, or None."""
    query = Query(_playlist_base_sql(["p.id = ?"]), (playlist_id,))
    items = _playlist_items(reader.fetch_joined(query, (Playlist,), _PLAYLIST_TOTAL_VALUES))
    return items[0] if items else None


def playlist_video_ids(playlist_id: str) -> list[str]:
    """Distinct IDs of stored owned videos in a playlist."""
    query = Query(
        """
        SELECT DISTINCT v.id AS id
        FROM playlist_items pi
        JOIN videos v ON v.id = pi.video_id AND v.own = 1
        WHERE pi.playlist_id = ?
        """,
        (playlist_id,),
    )
    return [video.id for video in reader.fetch(Video, query) if video.id is not None]


def lifetime_earnings(video_ids: Collection[str]) -> float:
    """Summed daily revenue times that day's USD/SGD rate across distinct videos; 0 when none have any."""
    ids = sorted(set(video_ids))
    if not ids:
        return 0.0
    query = Query(
        f"""
        SELECT COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0)
        FROM video_analytics va
        JOIN fx_rates fx ON fx.date = va.date
        WHERE va.video_id IN ({', '.join('?' for _ in ids)})
        """,
        tuple(ids),
    )
    return float(reader.fetch_scalar(query))


def owned_video_worklist(published_through: str | None = None) -> list[Video]:
    """Owned videos' id/title/published_at oldest first (unknown dates last), optionally published by a date."""
    conditions = ["own = 1"]
    params: list[object] = []
    if published_through is not None:
        exclusive_upper = date.fromisoformat(published_through) + timedelta(days=1)
        conditions.append("(published_at IS NULL OR published_at < ?)")
        params.append(f"{exclusive_upper.isoformat()}T00:00:00")
    query = Query(
        f"""
        SELECT id, title, published_at FROM videos WHERE {' AND '.join(conditions)}
        ORDER BY (published_at IS NULL), published_at ASC, id ASC
        """,
        tuple(params),
    )
    return reader.fetch(Video, query)
