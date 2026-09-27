from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from database import Comment, CommentAuthor, Video, queries, reader
from .video_scope import require_owned_video, require_playlist

router = APIRouter()

CommentSort = Literal["newest", "oldest", "likes"]


def _comment_page(count_query: reader.Query, page_query: reader.Query, page: int, page_size: int) -> dict:
    """Run a comment feed's count and page queries and return the paged response envelope."""
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        rows = reader.fetch_joined(page_query, (Comment, CommentAuthor, Video), conn=conn)
    items = [
        {
            **row[Comment].to_dict(),
            **row[CommentAuthor].to_dict(queries.COMMENT_AUTHOR_FIELDS, prefix="author_"),
            **row[Video].to_dict(queries.COMMENT_VIDEO_FIELDS, prefix="video_"),
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


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
    count_query, page_query = queries.comment_feed(
        page=page, page_size=page_size, sort_by=sort_by, text=text, video_title=video_title,
        author=author, start_date=start_date, end_date=end_date, content_type=content_type,
    )
    return _comment_page(count_query, page_query, page, page_size)


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
    count_query, page_query = queries.comment_feed(
        page=page, page_size=page_size, sort_by=sort_by, text=text, video_title=None,
        author=author, start_date=start_date, end_date=end_date, content_type=None, video_id=video_id,
    )
    return _comment_page(count_query, page_query, page, page_size)


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
    count_query, page_query = queries.comment_feed(
        page=page, page_size=page_size, sort_by=sort_by, text=text, video_title=video_title,
        author=author, start_date=start_date, end_date=end_date, content_type=content_type,
        playlist_id=playlist_id,
    )
    return _comment_page(count_query, page_query, page, page_size)
