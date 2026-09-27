"""Reusable, non-executing SELECT specifications for joins and aggregates; run them through `reader`."""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, timedelta

from .connection import _month_bound_conditions
from .dataclasses import Comment, CommentAuthor, Playlist, Video
from .reader import Query, joined_columns

VIDEO_TOTAL_VALUES = ("total_revenue_sgd", "total_watch_time_hours")
PLAYLIST_TOTAL_VALUES = ("last_item_added", "total_views", "total_earnings_sgd")
TOP_VIDEO_VALUES = ("period_views", "period_earnings_sgd", "period_watch_time_hours")

COMMENT_AUTHOR_FIELDS = ("youtube_channel_id", "display_name", "profile_image_url", "channel_url")
COMMENT_VIDEO_FIELDS = ("title", "content_type", "thumbnail_url")

_VIDEO_SORT_COLUMNS = {
    "published_at": "v.published_at",
    "view_count": "v.view_count",
    "comment_count": "v.comment_count",
    "total_revenue_sgd": "total_revenue_sgd",
}

_PLAYLIST_SORT_COLUMNS = {
    "published_at": "playlists__published_at",
    "item_count": "playlists__item_count",
    "last_item_added": "last_item_added",
    "total_views": "total_views",
    "total_earnings_sgd": "total_earnings_sgd",
}

# Every sort ends in a unique column so equal published times or like counts never page-shuffle a row.
COMMENT_SORT_CLAUSES: dict[str, str] = {
    "newest": "c.published_at DESC, c.id DESC",
    "oldest": "c.published_at ASC, c.id ASC",
    "likes": "c.like_count DESC, c.published_at DESC, c.id DESC",
}

_TOP_VIDEO_SORT_ORDER_BY = {
    "views": "period_views DESC, v.id ASC",
    "watch_time": "period_watch_time_hours DESC, period_views DESC, v.id ASC",
}

_VIDEO_TOTALS_SQL = """
    COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS total_revenue_sgd,
    COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS total_watch_time_hours
"""


def _video_conditions(
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


def _published_bounds(column: str, start_date: str | None, end_date: str | None) -> tuple[list[str], list[object]]:
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


def _date_bounds(column: str, start_date: str | None, end_date: str | None) -> tuple[list[str], list[object]]:
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


def _limit(limit: int | None) -> tuple[str, list[object]]:
    """Return an optional LIMIT clause and its parameter."""
    return ("LIMIT ?", [limit]) if limit is not None else ("", [])


def owned_video_worklist(published_through: str | None = None) -> Query:
    """Owned videos oldest first (unknown dates last), optionally published on or before a date."""
    conditions = ["own = 1"]
    params: list[object] = []
    if published_through is not None:
        exclusive_upper = date.fromisoformat(published_through) + timedelta(days=1)
        conditions.append("(published_at IS NULL OR published_at < ?)")
        params.append(f"{exclusive_upper.isoformat()}T00:00:00")
    return Query(
        f"""
        SELECT id, title, published_at FROM videos WHERE {' AND '.join(conditions)}
        ORDER BY (published_at IS NULL), published_at ASC, id ASC
        """,
        tuple(params),
    )


def playlist_owned_video_ids(playlist_id: str) -> Query:
    """Distinct IDs of stored owned videos in a playlist."""
    return Query(
        """
        SELECT DISTINCT v.id AS id
        FROM playlist_items pi
        JOIN videos v ON v.id = pi.video_id AND v.own = 1
        WHERE pi.playlist_id = ?
        """,
        (playlist_id,),
    )


def video_catalog(
    *,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "published_at",
    sort_dir: str = "desc",
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    video_ids: Collection[str] | None = None,
) -> tuple[Query, Query]:
    """Count and page queries for owned videos with lifetime totals; video_ids scopes the set."""
    conditions, params = _video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = _published_bounds("v.published_at", start_date, end_date)
    where = f"WHERE {' AND '.join([*conditions, *date_conditions])}"
    all_params = [*params, *date_params]
    order = f"{_VIDEO_SORT_COLUMNS.get(sort_by, 'v.published_at')} {'ASC' if sort_dir == 'asc' else 'DESC'}"
    count = Query(f"SELECT COUNT(*) FROM videos v {where}", tuple(all_params))
    rows = Query(
        f"""
        SELECT {joined_columns(Video, 'v')}, {_VIDEO_TOTALS_SQL}
        FROM videos v
        LEFT JOIN video_analytics va ON va.video_id = v.id
        LEFT JOIN fx_rates fx ON fx.date = va.date
        {where}
        GROUP BY v.id
        ORDER BY {order} LIMIT ? OFFSET ?
        """,
        (*all_params, page_size, (page - 1) * page_size),
    )
    return count, rows


PUBLISHED_VIDEO_FIELDS = ("id", "title", "published_at", "thumbnail_url", "content_type")


def videos_published(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> Query:
    """Owned videos matching the filters, ordered by publication time; video_ids scopes the set."""
    conditions, params = _video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = _published_bounds("v.published_at", start_date, end_date)
    columns = ", ".join(f"v.{name}" for name in PUBLISHED_VIDEO_FIELDS)
    return Query(
        f"SELECT {columns} FROM videos v WHERE {' AND '.join([*conditions, *date_conditions])} ORDER BY v.published_at",
        (*params, *date_params),
    )


_PLAYLIST_TOTALS_SQL = """
    MAX(v.published_at) AS last_item_added,
    COALESCE(SUM(v.view_count), 0) AS total_views,
    COALESCE((
        SELECT SUM(va.estimated_revenue * fx.usd_to_sgd)
        FROM playlist_items pi2
        JOIN videos v2 ON v2.id = pi2.video_id AND v2.own = 1
        JOIN video_analytics va ON va.video_id = pi2.video_id
        JOIN fx_rates fx ON fx.date = DATE(va.date)
        WHERE pi2.playlist_id = p.id
    ), 0) AS total_earnings_sgd
"""


def playlist_catalog(
    *,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "last_item_added",
    sort_dir: str = "desc",
    title: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    playlist_id: str | None = None,
) -> tuple[Query, Query]:
    """Count and page queries for playlists with membership totals; playlist_id selects one."""
    conditions: list[str] = []
    params: list[object] = []
    if playlist_id is not None:
        conditions.append("p.id = ?")
        params.append(playlist_id)
    if title:
        conditions.append("(p.title LIKE ? OR p.id LIKE ?)")
        params.extend([f"%{title}%", f"%{title}%"])
    date_conditions, date_params = _published_bounds("p.published_at", start_date, end_date)
    conditions.extend(date_conditions)
    params.extend(date_params)
    base = f"""
        SELECT {joined_columns(Playlist, 'p')}, {_PLAYLIST_TOTALS_SQL}
        FROM playlists p
        LEFT JOIN playlist_items pi ON pi.playlist_id = p.id
        LEFT JOIN videos v ON v.id = pi.video_id AND v.own = 1
        {f"WHERE {' AND '.join(conditions)}" if conditions else ""}
        GROUP BY p.id
    """
    order = f"{_PLAYLIST_SORT_COLUMNS.get(sort_by, 'last_item_added')} {'ASC' if sort_dir == 'asc' else 'DESC'}"
    count = Query(f"SELECT COUNT(*) FROM ({base})", tuple(params))
    rows = Query(
        f"SELECT * FROM ({base}) ORDER BY {order} LIMIT ? OFFSET ?",
        (*params, page_size, (page - 1) * page_size),
    )
    return count, rows


def comment_feed(
    *,
    page: int,
    page_size: int,
    sort_by: str,
    text: str | None,
    video_title: str | None,
    author: str | None,
    start_date: str | None,
    end_date: str | None,
    content_type: str | None,
    video_id: str | None = None,
    playlist_id: str | None = None,
) -> tuple[Query, Query]:
    """Count and page queries for comments on owned videos with author and video details."""
    conditions, params = _video_conditions(title=video_title, content_type=content_type)
    if video_id:
        conditions.append("c.video_id = ?")
        params.append(video_id)
    if playlist_id:
        conditions.append(
            "EXISTS (SELECT 1 FROM playlist_items pi WHERE pi.playlist_id = ? AND pi.video_id = c.video_id)"
        )
        params.append(playlist_id)
    if text:
        conditions.append("c.text LIKE ?")
        params.append(f"%{text}%")
    if author:
        conditions.append("ca.display_name LIKE ?")
        params.append(f"%{author}%")
    date_conditions, date_params = _published_bounds("c.published_at", start_date, end_date)
    where = f"WHERE {' AND '.join([*conditions, *date_conditions])}"
    all_params = [*params, *date_params]
    joins = """
        FROM comments c
        JOIN comment_authors ca ON ca.id = c.author_id
        JOIN videos v ON v.id = c.video_id
    """
    order_by = COMMENT_SORT_CLAUSES.get(sort_by, COMMENT_SORT_CLAUSES["newest"])
    count = Query(f"SELECT COUNT(*) {joins} {where}", tuple(all_params))
    rows = Query(
        f"""
        SELECT {joined_columns(Comment, 'c')},
            {joined_columns(CommentAuthor, 'ca', COMMENT_AUTHOR_FIELDS)},
            {joined_columns(Video, 'v', COMMENT_VIDEO_FIELDS)}
        {joins}
        {where}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        (*all_params, page_size, (page - 1) * page_size),
    )
    return count, rows


TOP_VIDEO_FIELDS = ("id", "title", "published_at", "thumbnail_url", "content_type")


def top_videos_by_views(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    sort_by: str = "views",
    limit: int = 10,
    video_ids: Collection[str] | None = None,
) -> Query:
    """Owned videos ranked by period views or watch time, with period earnings in SGD."""
    conditions, params = _video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = _date_bounds("va.date", start_date, end_date)
    order_by = _TOP_VIDEO_SORT_ORDER_BY.get(sort_by, _TOP_VIDEO_SORT_ORDER_BY["views"])
    return Query(
        f"""
        SELECT {joined_columns(Video, 'v', TOP_VIDEO_FIELDS)},
            SUM(va.views) AS period_views,
            COALESCE(SUM(va.estimated_revenue * fx.usd_to_sgd), 0) AS period_earnings_sgd,
            COALESCE(SUM(va.watch_time_minutes), 0) / 60.0 AS period_watch_time_hours
        FROM video_analytics va
        JOIN videos v ON v.id = va.video_id
        LEFT JOIN fx_rates fx ON fx.date = va.date
        WHERE {' AND '.join([*conditions, *date_conditions])}
        GROUP BY v.id
        ORDER BY {order_by}
        LIMIT ?
        """,
        (*params, *date_params, limit),
    )


def search_term_totals(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
    limit: int | None = None,
) -> Query:
    """Search terms summed across owned videos in a month range, ranked by views."""
    conditions, params = _video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    month_conditions, month_params = _month_bound_conditions("st", start_date, end_date)
    limit_sql, limit_params = _limit(limit)
    return Query(
        f"""
        SELECT st.search_term AS search_term, SUM(st.views) AS views
        FROM search_terms st
        JOIN videos v ON v.id = st.video_id
        WHERE {' AND '.join([*conditions, *month_conditions])}
        GROUP BY st.search_term
        ORDER BY views DESC, st.search_term ASC
        {limit_sql}
        """,
        (*params, *month_params, *limit_params),
    )


SEARCH_TERM_VIDEO_FIELDS = ("id", "title", "thumbnail_url", "content_type")


def videos_by_search_term(
    search_term: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    limit: int = 10,
    video_ids: Collection[str] | None = None,
) -> Query:
    """Owned videos ranked by views for one search term in a month range."""
    conditions, params = _video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    month_conditions, month_params = _month_bound_conditions("st", start_date, end_date)
    return Query(
        f"""
        SELECT {joined_columns(Video, 'v', SEARCH_TERM_VIDEO_FIELDS)}, SUM(st.views) AS views
        FROM search_terms st
        JOIN videos v ON v.id = st.video_id
        WHERE {' AND '.join([*conditions, *month_conditions, 'st.search_term = ?'])}
        GROUP BY v.id
        ORDER BY views DESC, v.id ASC
        LIMIT ?
        """,
        (*params, *month_params, search_term, limit),
    )


DESTINATION_VIDEO_FIELDS = ("title", "thumbnail_url", "content_type")


def related_video_destinations(
    referrer_video_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    video_ids: Collection[str] | None = None,
) -> Query:
    """Owned destination videos for one referrer in a month range, ranked by views."""
    conditions, params = _video_conditions(video_ids=video_ids)
    month_conditions, month_params = _month_bound_conditions("rv", start_date, end_date)
    limit_sql, limit_params = _limit(limit)
    return Query(
        f"""
        SELECT rv.target_video_id AS related_videos__target_video_id,
            {joined_columns(Video, 'v', DESTINATION_VIDEO_FIELDS)},
            SUM(rv.views) AS related_videos__views
        FROM related_videos rv
        JOIN videos v ON v.id = rv.target_video_id
        WHERE {' AND '.join(['rv.referrer_video_id = ?', *conditions, *month_conditions])}
        GROUP BY v.id
        ORDER BY related_videos__views DESC, v.id ASC
        {limit_sql}
        """,
        (referrer_video_id, *params, *month_params, *limit_params),
    )
