from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

import database

router = APIRouter()


def _resolve_playlist_video_ids(playlist_id: str) -> list[str]:
    """Return valid playlist video IDs or raise 404 when the playlist is missing."""
    if not database.get_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")
    return database.get_playlist_video_ids(playlist_id)


@router.get("/analytics/videos")
def get_aggregated_analytics(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return daily analytics aggregated across all videos, grouped by date and content_type."""
    return {"items": database.get_aggregated_analytics(start_date, end_date, content_type, privacy_status, title)}


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
    return {"items": database.get_top_videos_by_views(start_date, end_date, content_type, privacy_status, sort_by=sort_by, title=title)}


@router.get("/analytics/traffic-sources")
def get_aggregated_traffic_sources(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return daily traffic sources aggregated across all videos."""
    return {"items": database.get_aggregated_traffic_sources(start_date, end_date, content_type, privacy_status, title)}


@router.get("/analytics/traffic-sources/top")
def get_top_videos_by_traffic_source(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 videos by views for each traffic source type (channel-wide)."""
    return {"items": database.get_top_videos_by_traffic_source(start_date, end_date, content_type, privacy_status, limit=10, title=title)}


@router.get("/analytics/search-insights")
def get_search_terms(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return channel-wide search terms by views for the selected months."""
    return {"items": database.get_search_terms(start_date, end_date, content_type, privacy_status, title)}


@router.get("/analytics/search-insights/top")
def get_top_search_terms(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return the top 10 search terms by views across all videos (channel-wide)."""
    return {"items": database.get_search_terms(start_date, end_date, content_type, privacy_status, title, limit=10)}


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
    return {"items": database.get_videos_by_search_term(
        search_term, start_date, end_date, content_type, privacy_status, title, limit=limit
    )}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_top_videos_by_views(start_date, end_date, content_type, privacy_status, sort_by=sort_by, title=title, video_ids=video_ids)}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_aggregated_analytics(start_date, end_date, content_type, privacy_status, title, video_ids=video_ids)}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_aggregated_traffic_sources(start_date, end_date, content_type, privacy_status, title, video_ids=video_ids)}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_top_videos_by_traffic_source(start_date, end_date, content_type, privacy_status, limit=10, title=title, video_ids=video_ids)}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_search_terms(
        start_date, end_date, content_type, privacy_status, title, video_ids=video_ids
    )}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_search_terms(
        start_date, end_date, content_type, privacy_status, title, video_ids=video_ids, limit=10
    )}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_videos_by_search_term(
        search_term, start_date, end_date, content_type, privacy_status, title, video_ids=video_ids, limit=limit
    )}


@router.get("/analytics/videos/{video_id}/search-insights")
def get_video_search_terms(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return one video's search terms by views for the selected months."""
    if not database.get_owned_video(video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    return {"items": database.get_video_search_terms(video_id, start_date, end_date)}


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
    return database.get_related_video_referrers(
        start_date, end_date, content_type, privacy_status, title, own=own, limit=limit
    )


@router.get("/analytics/related-videos/destinations")
def get_related_video_destinations(
    referrer_video_id: str = Query(),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=10),
) -> dict:
    """Return top owned destinations for a Related Video referrer."""
    return {"items": database.get_related_video_destinations(referrer_video_id, start_date, end_date, limit=limit)}


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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return database.get_related_video_referrers(
        start_date, end_date, content_type, privacy_status, title, video_ids=video_ids, own=own, limit=limit
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
    video_ids = _resolve_playlist_video_ids(playlist_id)
    return {"items": database.get_related_video_destinations(
        referrer_video_id, start_date, end_date, video_ids=video_ids, limit=limit
    )}


@router.get("/analytics/videos/{video_id}/related-videos/referrers")
def get_video_related_video_referrers(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    own: bool = Query(),
    limit: int | None = Query(default=None),
) -> dict:
    """Return Related Video referrers for one owned video."""
    if not database.get_owned_video(video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    return database.get_related_video_referrers(
        start_date, end_date, video_ids=[video_id], own=own, limit=limit
    )
