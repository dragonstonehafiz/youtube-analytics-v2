from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

import database
import sync

router = APIRouter()


# ---------------------------------------------------------------------------
# Videos
# ---------------------------------------------------------------------------

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
    """Return aggregated counts and totals for all videos with optional filters."""
    return database.get_video_stats(title, start_date, end_date, content_type, privacy_status)


@router.get("/videos/published")
def get_videos_published(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
    playlist_id: str | None = Query(default=None),
) -> dict:
    """Return id, title, published_at, thumbnail_url for all videos matching the filters."""
    items = database.get_videos_published(start_date, end_date, content_type, privacy_status, playlist_id)
    return {"items": items}


@router.get("/videos/{video_id}")
def get_video(video_id: str) -> dict:
    """Return a single video by ID."""
    video = database.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"item": video}


@router.get("/videos/{video_id}/analytics")
def get_video_analytics(
    video_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return daily analytics rows for a video with optional date filters."""
    video = database.get_video(video_id)
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
    video = database.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"items": database.get_video_traffic_sources(video_id, start_date, end_date)}


@router.get("/analytics/videos")
def get_aggregated_analytics(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return daily analytics aggregated across all videos."""
    return {"items": database.get_aggregated_analytics(start_date, end_date, content_type, privacy_status)}


@router.get("/analytics/videos/top")
def get_top_videos_by_views(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return top 10 videos by views within the given filters."""
    return {"items": database.get_top_videos_by_views(start_date, end_date, content_type, privacy_status)}


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
) -> dict:
    """Return top 10 videos in a playlist by views within the given filters."""
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"items": database.get_playlist_top_videos_by_views(playlist_id, start_date, end_date, content_type, privacy_status)}


@router.get("/analytics/playlists/{playlist_id}")
def get_playlist_aggregated_analytics(
    playlist_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return daily analytics aggregated across all videos in a playlist."""
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


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

@router.get("/playlists")
def list_playlists(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str = Query(default="last_item_added"),
    sort_dir: str = Query(default="desc"),
    title: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return a page of playlists with server-side sort and optional filters."""
    items, total = database.get_all_playlists(page, page_size, sort_by, sort_dir, title, start_date, end_date)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: str) -> dict:
    """Return a single playlist with aggregated stats."""
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"item": playlist}


@router.get("/playlists/{playlist_id}/videos/stats")
def get_playlist_video_stats(
    playlist_id: str,
    title: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    privacy_status: str | None = Query(default=None),
) -> dict:
    """Return aggregated counts and totals for videos in a playlist with optional filters."""
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return database.get_playlist_video_stats(playlist_id, title, start_date, end_date, content_type, privacy_status)


@router.get("/playlists/{playlist_id}/videos")
def get_playlist_videos(
    playlist_id: str,
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
    """Return a page of videos in a playlist with server-side sort and optional filters."""
    playlist = database.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    items, total = database.get_playlist_videos(playlist_id, page, page_size, sort_by, sort_dir, title, start_date, end_date, content_type, privacy_status)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@router.get("/meta/date-range")
def get_date_range() -> dict:
    """Return the earliest published year across videos and playlists."""
    return {"earliest_year": database.get_earliest_published_year()}


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

@router.get("/sync/status")
def sync_status() -> dict:
    """Return current sync status and last synced timestamp."""
    return sync.get_status()


@router.post("/sync/trigger")
def trigger_sync(
    background_tasks: BackgroundTasks,
    scope: str = Query(default="incremental"),
    year: int | None = Query(default=None),
) -> dict:
    """Manually trigger a sync if one is not already running.

    scope: "incremental" (default, resume from last synced date) | "year" (refetch
    the given year) | "all" (refetch each video's entire history). scope/year only
    affect video analytics and traffic source syncing.
    """
    if sync.is_syncing():
        raise HTTPException(status_code=409, detail="Sync already in progress")
    if scope not in ("incremental", "year", "all"):
        raise HTTPException(status_code=400, detail="scope must be one of: incremental, year, all")
    if scope == "year" and year is None:
        raise HTTPException(status_code=400, detail="year is required when scope=year")
    background_tasks.add_task(sync.run_sync, scope, year)
    return {"queued": True}


@router.get("/sync/runs")
def sync_runs(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    """Return recent sync-stage records, newest first."""
    return {"items": database.get_sync_runs(limit)}
