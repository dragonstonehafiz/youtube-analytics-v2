from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from database.reports import comments
from .video_scope import require_owned_video, require_playlist

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
    return comments.comment_feed(
        page=page, page_size=page_size, sort_by=sort_by, text=text, video_title=video_title,
        author=author, start_date=start_date, end_date=end_date, content_type=content_type,
    )


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
    """Return a filtered and sorted page of one video's top-level comments."""
    require_owned_video(video_id)
    return comments.comment_feed(
        page=page, page_size=page_size, sort_by=sort_by, text=text,
        author=author, start_date=start_date, end_date=end_date, video_id=video_id,
    )


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
    require_playlist(playlist_id)
    return comments.comment_feed(
        page=page, page_size=page_size, sort_by=sort_by, text=text, video_title=video_title,
        author=author, start_date=start_date, end_date=end_date, content_type=content_type,
        playlist_id=playlist_id,
    )
