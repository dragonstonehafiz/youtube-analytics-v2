"""Traffic-source, search-term and Related Video reports for owned videos."""

from __future__ import annotations

from collections.abc import Collection

from .. import reader
from ..dataclasses import RelatedVideo, SearchTerm, Video, VideoTrafficSource
from ..reader import Query, joined_columns
from ._conditions import date_bounds, limit_clause, month_bounds, video_conditions

_TRAFFIC_SOURCE_FIELDS = ("date", "traffic_source_type", "views", "watch_time_minutes")
_TRAFFIC_TOTAL_FIELDS = ("views", "watch_time_minutes")
_TRAFFIC_VIDEO_FIELDS = ("id", "title", "thumbnail_url", "content_type")
_TOP_VIDEOS_PER_SOURCE = 10

_SEARCH_TERM_FIELDS = ("search_term", "views")
_SEARCH_TERM_VIDEO_FIELDS = ("id", "title", "thumbnail_url", "content_type")

_REFERRER_VIDEO_FIELDS = ("title", "thumbnail_url", "own")
_DESTINATION_VIDEO_FIELDS = ("title", "thumbnail_url", "content_type")


def daily_traffic_sources(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> list[dict]:
    """Owned-video views and watch time summed per date and source type, zero-filling observed types daily."""
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = date_bounds("vts.date", start_date, end_date)
    query = Query(
        f"""
        SELECT vts.date AS date, vts.traffic_source_type AS traffic_source_type,
            SUM(vts.views) AS views, SUM(vts.watch_time_minutes) AS watch_time_minutes
        FROM video_traffic_sources vts
        JOIN videos v ON v.id = vts.video_id
        WHERE {' AND '.join([*conditions, *date_conditions])}
        GROUP BY vts.date, vts.traffic_source_type
        ORDER BY vts.date, vts.traffic_source_type
        """,
        (*params, *date_params),
    )
    fill = reader.DateFill(
        date="date",
        breakdown="traffic_source_type",
        metrics={"views": 0, "watch_time_minutes": 0},
        start_date=start_date,
    )
    rows = reader.fetch(VideoTrafficSource, query, fill_dates=fill)
    return [row.to_dict(_TRAFFIC_SOURCE_FIELDS) for row in rows]


def top_videos_by_traffic_source(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> dict[str, list[dict]]:
    """The top owned videos by views for each traffic-source type."""
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    date_conditions, date_params = date_bounds("vts.date", start_date, end_date)
    query = Query(
        f"""
        SELECT vts.traffic_source_type AS video_traffic_sources__traffic_source_type,
            {joined_columns(Video, 'v', _TRAFFIC_VIDEO_FIELDS)},
            SUM(vts.views) AS video_traffic_sources__views,
            SUM(vts.watch_time_minutes) AS video_traffic_sources__watch_time_minutes
        FROM video_traffic_sources vts
        JOIN videos v ON v.id = vts.video_id
        WHERE {' AND '.join([*conditions, *date_conditions])}
        GROUP BY vts.traffic_source_type, v.id
        ORDER BY vts.traffic_source_type, video_traffic_sources__views DESC
        """,
        (*params, *date_params),
    )
    rows = reader.fetch_joined(query, (VideoTrafficSource, Video))
    grouped = reader.group_by(rows, (VideoTrafficSource, "traffic_source_type"), limit=_TOP_VIDEOS_PER_SOURCE)
    return {
        source: [
            {
                **row[Video].to_dict(_TRAFFIC_VIDEO_FIELDS),
                **row[VideoTrafficSource].to_dict(_TRAFFIC_TOTAL_FIELDS),
            }
            for row in bucket
        ]
        for source, bucket in grouped.items()
    }


def search_terms(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Search terms summed across owned videos in a month range, ranked by views."""
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    month_conditions, month_params = month_bounds("st", start_date, end_date)
    limit_sql, limit_params = limit_clause(limit)
    query = Query(
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
    return [term.to_dict(_SEARCH_TERM_FIELDS) for term in reader.fetch(SearchTerm, query)]


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
) -> list[dict]:
    """Owned videos ranked by views for one search term in a month range."""
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    month_conditions, month_params = month_bounds("st", start_date, end_date)
    query = Query(
        f"""
        SELECT {joined_columns(Video, 'v', _SEARCH_TERM_VIDEO_FIELDS)}, SUM(st.views) AS views
        FROM search_terms st
        JOIN videos v ON v.id = st.video_id
        WHERE {' AND '.join([*conditions, *month_conditions, 'st.search_term = ?'])}
        GROUP BY v.id
        ORDER BY views DESC, v.id ASC
        LIMIT ?
        """,
        (*params, *month_params, search_term, limit),
    )
    rows = reader.fetch_joined(query, (Video,), ("views",))
    return [{**row[Video].to_dict(_SEARCH_TERM_VIDEO_FIELDS), **row.values} for row in rows]


def related_video_referrers(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
    own: bool | None = None,
    limit: int | None = None,
) -> dict:
    """Ranked referrers of owned targets and the scope's total named views; own and limit apply only to the list."""
    conditions, params = video_conditions(
        video_ids=video_ids, title=title, content_type=content_type, privacy_status=privacy_status
    )
    month_conditions, month_params = month_bounds("rv", start_date, end_date)
    where = " AND ".join([*conditions, *month_conditions])
    scope_params = (*params, *month_params)
    total_query = Query(
        f"""
        SELECT COALESCE(SUM(rv.views), 0)
        FROM related_videos rv
        JOIN videos v ON v.id = rv.target_video_id
        WHERE {where}
        """,
        scope_params,
    )
    own_sql, own_params = ("AND COALESCE(ref.own, 0) = ?", [1 if own else 0]) if own is not None else ("", [])
    limit_sql, limit_params = limit_clause(limit)
    rows_query = Query(
        f"""
        SELECT rv.referrer_video_id AS related_videos__referrer_video_id,
            SUM(rv.views) AS related_videos__views,
            {joined_columns(Video, 'ref', _REFERRER_VIDEO_FIELDS)}
        FROM related_videos rv
        JOIN videos v ON v.id = rv.target_video_id
        LEFT JOIN videos ref ON ref.id = rv.referrer_video_id
        WHERE {where} {own_sql}
        GROUP BY rv.referrer_video_id, ref.title, ref.thumbnail_url, ref.own
        ORDER BY related_videos__views DESC, rv.referrer_video_id ASC
        {limit_sql}
        """,
        (*scope_params, *own_params, *limit_params),
    )
    with reader.connect() as conn:
        total = reader.fetch_scalar(total_query, conn=conn)
        rows = reader.fetch_joined(rows_query, (RelatedVideo, Video), conn=conn)
    items = [
        {
            **row[RelatedVideo].to_dict(("referrer_video_id", "views")),
            **row[Video].to_dict(("title", "thumbnail_url")),
            "referrer_own": row[Video].own,
        }
        for row in rows
    ]
    return {"items": items, "total_named_views": total}


def related_video_destinations(
    referrer_video_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    video_ids: Collection[str] | None = None,
) -> list[dict]:
    """Owned destination videos for one referrer in a month range, ranked by views."""
    conditions, params = video_conditions(video_ids=video_ids)
    month_conditions, month_params = month_bounds("rv", start_date, end_date)
    limit_sql, limit_params = limit_clause(limit)
    query = Query(
        f"""
        SELECT rv.target_video_id AS related_videos__target_video_id,
            {joined_columns(Video, 'v', _DESTINATION_VIDEO_FIELDS)},
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
    rows = reader.fetch_joined(query, (RelatedVideo, Video))
    return [
        {
            **row[RelatedVideo].to_dict(("target_video_id",)),
            **row[Video].to_dict(_DESTINATION_VIDEO_FIELDS),
            **row[RelatedVideo].to_dict(("views",)),
        }
        for row in rows
    ]
