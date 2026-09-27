from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import database
from database import Playlist, Video, queries, reader
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
    count_query, page_query = queries.playlist_catalog(
        page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, title=title,
        start_date=start_date, end_date=end_date,
    )
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        rows = reader.fetch_joined(page_query, (Playlist,), queries.PLAYLIST_TOTAL_VALUES, conn=conn)
    items = [{**row[Playlist].to_dict(), **row.values} for row in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: str) -> dict:
    """Return a single playlist with aggregated stats."""
    _, page_query = queries.playlist_catalog(playlist_id=playlist_id, page_size=1)
    rows = reader.fetch_joined(page_query, (Playlist,), queries.PLAYLIST_TOTAL_VALUES)
    if not rows:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"item": {**rows[0][Playlist].to_dict(), **rows[0].values}}


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
    video_ids = resolve_playlist_video_ids(playlist_id)
    count_query, page_query = queries.video_catalog(
        page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, title=title,
        start_date=start_date, end_date=end_date, content_type=content_type, privacy_status=privacy_status,
        video_ids=video_ids,
    )
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        rows = reader.fetch_joined(page_query, (Video,), queries.VIDEO_TOTAL_VALUES, conn=conn)
    items = [{**row[Video].to_dict(), **row.values} for row in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
