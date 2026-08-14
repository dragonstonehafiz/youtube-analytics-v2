from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

import database

router = APIRouter()

CommentSort = Literal["newest", "oldest", "likes"]


@router.get("/comments")
def list_comments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: CommentSort = Query(default="newest"),
    text: str | None = Query(default=None),
    video_title: str | None = Query(default=None),
    author: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
) -> dict:
    """Return a page of channel-wide top-level comments with optional filters and sort."""
    items, total = database.get_comments(
        page, page_size, sort_by, text, video_title, author, start_date, end_date, content_type
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/comments/videos/{video_id}")
def list_video_comments(
    video_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: CommentSort = Query(default="newest"),
    text: str | None = Query(default=None),
    author: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    """Return a page of one video's top-level comments with optional filters and sort.

    Video title and content type are fixed by the scope, so neither is accepted here.
    """
    if not database.get_video(video_id):
        raise HTTPException(status_code=404, detail="Video not found")
    items, total = database.get_video_comments(
        video_id, page, page_size, sort_by, text, author, start_date, end_date
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/comments/playlists/{playlist_id}")
def list_playlist_comments(
    playlist_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: CommentSort = Query(default="newest"),
    text: str | None = Query(default=None),
    video_title: str | None = Query(default=None),
    author: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
) -> dict:
    """Return a page of comments on one playlist's videos with optional filters and sort."""
    if not database.get_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")
    items, total = database.get_playlist_comments(
        playlist_id, page, page_size, sort_by, text, video_title, author, start_date, end_date,
        content_type,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
