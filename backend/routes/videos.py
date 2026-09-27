from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import database
from database import Video, queries, reader
from .video_scope import require_owned_video, resolve_playlist_video_ids

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
    count_query, page_query = queries.video_catalog(
        page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, title=title,
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
    )
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        rows = reader.fetch_joined(page_query, (Video,), queries.VIDEO_TOTAL_VALUES, conn=conn)
    items = [{**row[Video].to_dict(), **row.values} for row in rows]
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
    video_ids = resolve_playlist_video_ids(playlist_id) if playlist_id else None
    videos = reader.fetch(Video, queries.videos_published(
        start_date=start_date, end_date=end_date, content_type=content_type,
        privacy_status=privacy_status, title=title, video_ids=video_ids,
    ))
    return {"items": [video.to_dict(queries.PUBLISHED_VIDEO_FIELDS) for video in videos]}


@router.get("/videos/{video_id}")
def get_video(video_id: str) -> dict:
    """Return a single video by ID."""
    _, page_query = queries.video_catalog(video_ids=[video_id], page_size=1)
    rows = reader.fetch_joined(page_query, (Video,), queries.VIDEO_TOTAL_VALUES)
    if not rows:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"item": {**rows[0][Video].to_dict(), **rows[0].values}}


@router.get("/videos/{video_id}/analytics")
def get_video_analytics(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return daily analytics rows for a video, each tagged with content_type, with optional date filters."""
    require_owned_video(video_id)
    return {"items": database.get_video_analytics(video_id, start_date, end_date)}


@router.get("/videos/{video_id}/traffic-sources")
def get_video_traffic_sources(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return daily traffic source rows for a video with optional date filters."""
    require_owned_video(video_id)
    return {"items": database.get_video_traffic_sources(video_id, start_date, end_date)}
