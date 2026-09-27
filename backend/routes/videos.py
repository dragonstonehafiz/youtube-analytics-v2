from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import database

router = APIRouter()


@router.get("/videos")
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
) -> dict:
    """Return a page of videos with server-side sort and optional filters."""
    items, total = database.get_all_videos(page, page_size, sort_by, sort_dir, title, start_date, end_date, content_type, privacy_status)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/videos/stats")
def get_video_stats(
    title: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return filtered channel statistics split into Legacy and New groups."""
    return database.get_video_stats(title, start_date, end_date, content_type, privacy_status)


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
    items = database.get_videos_published(start_date, end_date, content_type, privacy_status, playlist_id, title)
    return {"items": items}


@router.get("/videos/{video_id}")
def get_video(video_id: str) -> dict:
    """Return a single video by ID."""
    video = database.get_owned_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"item": video}


@router.get("/videos/{video_id}/analytics")
def get_video_analytics(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return daily analytics rows for a video, each tagged with content_type, with optional date filters."""
    video = database.get_owned_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"items": database.get_video_analytics(video_id, start_date, end_date)}


@router.get("/videos/{video_id}/traffic-sources")
def get_video_traffic_sources(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return daily traffic source rows for a video with optional date filters."""
    video = database.get_owned_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"items": database.get_video_traffic_sources(video_id, start_date, end_date)}
