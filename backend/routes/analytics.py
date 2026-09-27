from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from fastapi import APIRouter, Query

from database import RelatedVideo, SearchTerm, Video, VideoAnalytics, VideoTrafficSource, queries, reader
from .daily_series import ANALYTICS_METRIC_DEFAULTS, traffic_source_fill, traffic_source_items
from .video_scope import require_owned_video, resolve_playlist_video_ids

router = APIRouter()

_SEARCH_TERM_FIELDS = ("search_term", "views")
_TRAFFIC_SOURCE_TOTAL_FIELDS = ("views", "watch_time_minutes")
_TRAFFIC_SOURCE_TOP_LIMIT = 10


def _analytics_totals(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> list[dict]:
    """Read and serialize daily analytics totals, zero-filling each content type."""
    fill = reader.DateFill(
        date=(VideoAnalytics, "date"),
        breakdown=(Video, "content_type"),
        breakdown_values=[content_type] if content_type else ["video", "short"],
        metrics=ANALYTICS_METRIC_DEFAULTS,
        start_date=start_date,
    )
    rows = reader.fetch_joined(queries.daily_analytics_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids,
    ), (VideoAnalytics, Video), queries.ANALYTICS_VALUES, fill_dates=fill)
    return [
        {
            **row[VideoAnalytics].to_dict(("date",)),
            **row[Video].to_dict(("content_type",)),
            **row[VideoAnalytics].to_dict(queries.ANALYTICS_METRIC_FIELDS),
            **row.values,
        }
        for row in rows
    ]


def _traffic_source_totals(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> list[dict]:
    """Read and serialize daily traffic-source totals, zero-filling each observed source type."""
    rows = reader.fetch(VideoTrafficSource, queries.daily_traffic_source_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids,
    ), fill_dates=traffic_source_fill(start_date))
    return traffic_source_items(rows)


def _traffic_source_top_videos(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
    video_ids: Collection[str] | None = None,
) -> dict[str, list[dict]]:
    """Read and serialize the top videos by views for each traffic-source type."""
    rows = reader.fetch_joined(queries.traffic_source_video_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids,
    ), (VideoTrafficSource, Video))
    grouped = reader.group_by(rows, (VideoTrafficSource, "traffic_source_type"), limit=_TRAFFIC_SOURCE_TOP_LIMIT)
    return {
        source: [
            {
                **row[Video].to_dict(queries.TRAFFIC_SOURCE_VIDEO_FIELDS),
                **row[VideoTrafficSource].to_dict(_TRAFFIC_SOURCE_TOTAL_FIELDS),
            }
            for row in bucket
        ]
        for source, bucket in grouped.items()
    }


def _top_video_items(rows: list[reader.Joined]) -> list[dict]:
    """Serialize ranked top-video rows with their period totals."""
    return [{**row[Video].to_dict(queries.TOP_VIDEO_FIELDS), **row.values} for row in rows]


def _search_term_video_items(rows: list[reader.Joined]) -> list[dict]:
    """Serialize ranked videos for one search term with their summed views."""
    return [{**row[Video].to_dict(queries.SEARCH_TERM_VIDEO_FIELDS), **row.values} for row in rows]


def _destination_items(rows: list[reader.Joined]) -> list[dict]:
    """Serialize ranked Related Video destinations with their summed views."""
    return [
        {
            **row[RelatedVideo].to_dict(("target_video_id",)),
            **row[Video].to_dict(queries.DESTINATION_VIDEO_FIELDS),
            **row[RelatedVideo].to_dict(("views",)),
        }
        for row in rows
    ]


def _related_video_referrers_response(
    video_ids: Collection[str] | None = None,
    *,
    start_date: str | None,
    end_date: str | None,
    own: bool,
    limit: int | None,
    content_type: str | None = None,
    privacy_status: str | None = None,
    title: str | None = None,
) -> dict:
    """Return ranked Related Video referrers and the total named views for the scope."""
    total_query, rows_query = queries.related_video_referrers(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids, own=own, limit=limit,
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


@router.get("/analytics/videos")
def get_aggregated_analytics(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return daily analytics aggregated across all videos, grouped by date and content_type."""
    return {"items": _analytics_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title,
    )}


@router.get("/analytics/videos/top")
def get_top_videos_by_views(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    sort_by: Literal["views", "watch_time"] = Query(default="views"),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 filtered videos by views or watch time."""
    rows = reader.fetch_joined(queries.top_videos_by_views(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, sort_by=sort_by, limit=10,
    ), (Video,), queries.TOP_VIDEO_VALUES)
    return {"items": _top_video_items(rows)}


@router.get("/analytics/traffic-sources")
def get_aggregated_traffic_sources(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return daily traffic sources aggregated across all videos."""
    return {"items": _traffic_source_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title,
    )}


@router.get("/analytics/traffic-sources/top")
def get_top_videos_by_traffic_source(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 videos by views for each traffic source type (channel-wide)."""
    return {"items": _traffic_source_top_videos(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title,
    )}


@router.get("/analytics/search-insights")
def get_search_terms(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return channel-wide search terms by views for the selected months."""
    terms = reader.fetch(SearchTerm, queries.search_term_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title,
    ))
    return {"items": [term.to_dict(_SEARCH_TERM_FIELDS) for term in terms]}


@router.get("/analytics/search-insights/top")
def get_top_search_terms(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 search terms by views across all videos (channel-wide)."""
    terms = reader.fetch(SearchTerm, queries.search_term_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, limit=10,
    ))
    return {"items": [term.to_dict(_SEARCH_TERM_FIELDS) for term in terms]}


@router.get("/analytics/search-insights/videos")
def get_videos_by_search_term(
    search_term: str = Query(),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
    limit: int = Query(default=10),
) -> dict:
    """Return the top channel-wide videos for a search term."""
    rows = reader.fetch_joined(queries.videos_by_search_term(
        search_term, start_date=start_date, end_date=end_date, content_type=content_type,
        privacy_status=privacy_status, title=title, limit=limit,
    ), (Video,), ("views",))
    return {"items": _search_term_video_items(rows)}


@router.get("/analytics/playlists/{playlist_id}/top")
def get_playlist_top_videos_by_views(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    sort_by: Literal["views", "watch_time"] = Query(default="views"),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 filtered playlist videos by views or watch time."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    rows = reader.fetch_joined(queries.top_videos_by_views(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, sort_by=sort_by, limit=10, video_ids=video_ids,
    ), (Video,), queries.TOP_VIDEO_VALUES)
    return {"items": _top_video_items(rows)}


@router.get("/analytics/playlists/{playlist_id}")
def get_playlist_aggregated_analytics(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return daily analytics aggregated across all videos in a playlist, grouped by date and content_type."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    return {"items": _analytics_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids,
    )}


@router.get("/analytics/playlists/{playlist_id}/traffic-sources")
def get_playlist_aggregated_traffic_sources(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return daily traffic sources aggregated across all videos in a playlist."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    return {"items": _traffic_source_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids,
    )}


@router.get("/analytics/playlists/{playlist_id}/traffic-sources/top")
def get_playlist_top_videos_by_traffic_source(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 videos in a playlist by views for each traffic source type."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    return {"items": _traffic_source_top_videos(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids,
    )}


@router.get("/analytics/playlists/{playlist_id}/search-insights")
def get_playlist_search_terms(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return playlist search terms by views for the selected months."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    terms = reader.fetch(SearchTerm, queries.search_term_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids,
    ))
    return {"items": [term.to_dict(_SEARCH_TERM_FIELDS) for term in terms]}


@router.get("/analytics/playlists/{playlist_id}/search-insights/top")
def get_playlist_top_search_terms(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 search terms by views across all videos in a playlist."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    terms = reader.fetch(SearchTerm, queries.search_term_totals(
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        title=title, video_ids=video_ids, limit=10,
    ))
    return {"items": [term.to_dict(_SEARCH_TERM_FIELDS) for term in terms]}


@router.get("/analytics/playlists/{playlist_id}/search-insights/videos")
def get_playlist_videos_by_search_term(
    playlist_id: str,
    search_term: str = Query(),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
    limit: int = Query(default=10),
) -> dict:
    """Return the top playlist videos for a search term."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    rows = reader.fetch_joined(queries.videos_by_search_term(
        search_term, start_date=start_date, end_date=end_date, content_type=content_type,
        privacy_status=privacy_status, title=title, limit=limit, video_ids=video_ids,
    ), (Video,), ("views",))
    return {"items": _search_term_video_items(rows)}


@router.get("/analytics/videos/{video_id}/search-insights")
def get_video_search_terms(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return one video's search terms by views for the selected months."""
    require_owned_video(video_id)
    terms = reader.fetch(SearchTerm, queries.search_term_totals(
        start_date=start_date, end_date=end_date, video_ids=[video_id],
    ))
    return {"items": [term.to_dict(_SEARCH_TERM_FIELDS) for term in terms]}


@router.get("/analytics/related-videos/referrers")
def get_related_video_referrers(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
    own: bool = Query(),
    limit: int = Query(default=10),
) -> dict:
    """Return channel-wide Related Video referrers and total named views."""
    return _related_video_referrers_response(
        start_date=start_date, end_date=end_date, content_type=content_type,
        privacy_status=privacy_status, title=title, own=own, limit=limit,
    )


@router.get("/analytics/related-videos/destinations")
def get_related_video_destinations(
    referrer_video_id: str = Query(),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=10),
) -> dict:
    """Return top owned destinations for a Related Video referrer."""
    rows = reader.fetch_joined(queries.related_video_destinations(
        referrer_video_id, start_date=start_date, end_date=end_date, limit=limit,
    ), (RelatedVideo, Video))
    return {"items": _destination_items(rows)}


@router.get("/analytics/playlists/{playlist_id}/related-videos/referrers")
def get_playlist_related_video_referrers(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
    own: bool = Query(),
    limit: int = Query(default=10),
) -> dict:
    """Return Related Video referrers for a playlist and total named views."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    return _related_video_referrers_response(
        video_ids, start_date=start_date, end_date=end_date, content_type=content_type,
        privacy_status=privacy_status, title=title, own=own, limit=limit,
    )


@router.get("/analytics/playlists/{playlist_id}/related-videos/destinations")
def get_playlist_related_video_destinations(
    playlist_id: str,
    referrer_video_id: str = Query(),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=10),
) -> dict:
    """Return top playlist destinations for a Related Video referrer."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    rows = reader.fetch_joined(queries.related_video_destinations(
        referrer_video_id, start_date=start_date, end_date=end_date, limit=limit, video_ids=video_ids,
    ), (RelatedVideo, Video))
    return {"items": _destination_items(rows)}


@router.get("/analytics/videos/{video_id}/related-videos/referrers")
def get_video_related_video_referrers(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    own: bool = Query(),
    limit: int | None = Query(default=None),
) -> dict:
    """Return Related Video referrers for one owned video."""
    require_owned_video(video_id)
    return _related_video_referrers_response(
        [video_id], start_date=start_date, end_date=end_date, own=own, limit=limit
    )
