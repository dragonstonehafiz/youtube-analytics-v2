from __future__ import annotations

from fastapi import APIRouter, Query

from database.reports import catalog
from ._shared import require_found

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
    return catalog.playlist_listing(
        page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, title=title,
        start_date=start_date, end_date=end_date,
    )


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: str) -> dict:
    """Return a single playlist with aggregated stats."""
    return {"item": require_found(catalog.playlist_detail(playlist_id), "Playlist")}
