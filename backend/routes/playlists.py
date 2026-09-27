from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import database
from .video_scope import resolve_playlist_video_ids

router = APIRouter()


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
    """Return filtered playlist statistics split into Legacy and New groups."""
    video_ids = resolve_playlist_video_ids(playlist_id)
    return database.get_video_stats(title, start_date, end_date, content_type, privacy_status, video_ids=video_ids)


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
