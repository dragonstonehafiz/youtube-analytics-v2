from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

import database

router = APIRouter()


@router.get("/analytics/videos")
def get_aggregated_analytics(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return daily analytics aggregated across all videos, grouped by date and content_type."""
    return {"items": database.get_aggregated_analytics(start_date, end_date, content_type, privacy_status)}


@router.get("/analytics/videos/top")
def get_top_videos_by_views(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    sort_by: Literal["views", "watch_time"] = Query(default="views"),
) -> dict:
    """Return top 10 videos within the given filters, ranked by views or period watch time (default: views).

    Metrics are aggregated over the selected analytics period. Results include period views, watch time hours,
    and estimated SGD earnings.
    """
    return {"items": database.get_top_videos_by_views(start_date, end_date, content_type, privacy_status, sort_by=sort_by)}


@router.get("/analytics/traffic-sources")
def get_aggregated_traffic_sources(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return daily traffic sources aggregated across all videos."""
    return {"items": database.get_aggregated_traffic_sources(start_date, end_date, content_type, privacy_status)}


@router.get("/analytics/traffic-sources/top")
def get_top_videos_by_traffic_source(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return the top 10 videos by views for each traffic source type (channel-wide)."""
    return {"items": database.get_top_videos_by_traffic_source(start_date, end_date, content_type, privacy_status, limit=10)}


@router.get("/analytics/playlists/{playlist_id}/top")
def get_playlist_top_videos_by_views(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    sort_by: Literal["views", "watch_time"] = Query(default="views"),
) -> dict:
    """Return top 10 videos in a playlist within the given filters, ranked by views or period watch time
    (default: views).

    Metrics are aggregated over the selected analytics period. Results include period views, watch time hours,
    and estimated SGD earnings.
    """
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"items": database.get_playlist_top_videos_by_views(playlist_id, start_date, end_date, content_type, privacy_status, sort_by=sort_by)}


@router.get("/analytics/playlists/{playlist_id}")
def get_playlist_aggregated_analytics(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return daily analytics aggregated across all videos in a playlist, grouped by date and content_type."""
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"items": database.get_playlist_aggregated_analytics(playlist_id, start_date, end_date, content_type, privacy_status)}


@router.get("/analytics/playlists/{playlist_id}/traffic-sources")
def get_playlist_aggregated_traffic_sources(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return daily traffic sources aggregated across all videos in a playlist."""
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"items": database.get_playlist_aggregated_traffic_sources(playlist_id, start_date, end_date, content_type, privacy_status)}


@router.get("/analytics/playlists/{playlist_id}/traffic-sources/top")
def get_playlist_top_videos_by_traffic_source(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return the top 10 videos in a playlist by views for each traffic source type."""
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"items": database.get_playlist_top_videos_by_traffic_source(playlist_id, start_date, end_date, content_type, privacy_status, limit=10)}
