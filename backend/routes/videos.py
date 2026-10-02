from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from database.reports import analytics, catalog, traffic, video_statistics
from ._shared import require_found
from .video_scope import require_owned_video, require_playlist, scope_video_ids

router = APIRouter()


@router.get("/videos", name="list_videos")
@router.get("/playlists/{playlist_id}/videos", name="get_playlist_videos")
def list_videos(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = Query(default="published_at"),
    sort_dir: str = Query(default="desc"),
    title: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    video_ids: list[str] | None = Depends(scope_video_ids),
) -> dict:
    """Return a page of channel or playlist videos with server-side sort and optional filters."""
    return catalog.video_listing(
        page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, title=title,
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        video_ids=video_ids,
    )


@router.get("/videos/stats", name="get_video_stats")
@router.get("/playlists/{playlist_id}/videos/stats", name="get_playlist_video_stats")
def get_video_stats(
    title: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    video_ids: list[str] | None = Depends(scope_video_ids),
) -> dict:
    """Return filtered channel or playlist statistics split into Legacy and New groups."""
    return video_statistics.get_video_stats(
        title, start_date, end_date, content_type, privacy_status, video_ids=video_ids
    )


@router.get("/videos/published")
def get_videos_published(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    playlist_id: str | None = Query(default=None),
    title: str | None = Query(default=None),
) -> dict:
    """Return id, title, published_at, thumbnail_url for all videos matching the filters."""
    video_ids = None
    if playlist_id:
        require_playlist(playlist_id)
        video_ids = catalog.playlist_video_ids(playlist_id)
    return catalog.video_listing(
        fields=("id", "title", "published_at", "thumbnail_url", "content_type"), page_size=None,
        sort_by="published_at", sort_dir="asc", start_date=start_date, end_date=end_date,
        content_type=content_type, privacy_status=privacy_status, title=title, video_ids=video_ids,
    )


@router.get("/videos/{video_id}")
def get_video(video_id: str) -> dict:
    """Return a single video by ID."""
    return {"item": require_found(catalog.video_detail(video_id), "Video")}


@router.get("/videos/{video_id}/analytics")
def get_video_analytics(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return daily analytics rows for a video, each tagged with content_type, with optional date filters."""
    require_owned_video(video_id)
    return {"items": analytics.daily_analytics(
        start_date=start_date, end_date=end_date, video_ids=[video_id], fill_content_types=None,
    )}


@router.get("/videos/{video_id}/traffic-sources")
def get_video_traffic_sources(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return daily traffic source rows for a video with optional date filters."""
    require_owned_video(video_id)
    return {"items": traffic.daily_traffic_sources(start_date=start_date, end_date=end_date, video_ids=[video_id])}
