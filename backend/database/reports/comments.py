"""Paginated top-level comment feed on owned videos."""

from __future__ import annotations

from .. import reader
from ..dataclasses import Comment, CommentAuthor, Video
from ..reader import Query, joined_columns
from ._conditions import published_bounds, video_conditions

_AUTHOR_FIELDS = ("youtube_channel_id", "display_name", "profile_image_url", "channel_url")
_VIDEO_FIELDS = ("title", "content_type", "thumbnail_url")

# Every sort ends in a unique column so equal published times or like counts never page-shuffle a row.
_SORT_CLAUSES: dict[str, str] = {
    "newest": "c.published_at DESC, c.id DESC",
    "oldest": "c.published_at ASC, c.id ASC",
    "likes": "c.like_count DESC, c.published_at DESC, c.id DESC",
}


def comment_feed(
    *,
    page: int,
    page_size: int,
    sort_by: str,
    text: str | None = None,
    video_title: str | None = None,
    author: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
    video_id: str | None = None,
    playlist_id: str | None = None,
) -> dict:
    """One sorted page of comments on owned videos with author and video details, and the match count."""
    conditions, params = video_conditions(title=video_title, content_type=content_type)
    if video_id:
        conditions.append("c.video_id = ?")
        params.append(video_id)
    if playlist_id:
        conditions.append(
            "EXISTS (SELECT 1 FROM playlist_items pi WHERE pi.playlist_id = ? AND pi.video_id = c.video_id)"
        )
        params.append(playlist_id)
    if text:
        conditions.append("c.text LIKE ?")
        params.append(f"%{text}%")
    if author:
        conditions.append("ca.display_name LIKE ?")
        params.append(f"%{author}%")
    date_conditions, date_params = published_bounds("c.published_at", start_date, end_date)
    where = f"WHERE {' AND '.join([*conditions, *date_conditions])}"
    all_params = [*params, *date_params]
    joins = """
        FROM comments c
        JOIN comment_authors ca ON ca.id = c.author_id
        JOIN videos v ON v.id = c.video_id
    """
    order_by = _SORT_CLAUSES.get(sort_by, _SORT_CLAUSES["newest"])
    count_query = Query(f"SELECT COUNT(*) {joins} {where}", tuple(all_params))
    page_query = Query(
        f"""
        SELECT {joined_columns(Comment, 'c')},
            {joined_columns(CommentAuthor, 'ca', _AUTHOR_FIELDS)},
            {joined_columns(Video, 'v', _VIDEO_FIELDS)}
        {joins}
        {where}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        (*all_params, page_size, (page - 1) * page_size),
    )
    with reader.connect() as conn:
        total = reader.fetch_scalar(count_query, conn=conn)
        rows = reader.fetch_joined(page_query, (Comment, CommentAuthor, Video), conn=conn)
    items = [
        {
            **row[Comment].to_dict(),
            **row[CommentAuthor].to_dict(_AUTHOR_FIELDS, prefix="author_"),
            **row[Video].to_dict(_VIDEO_FIELDS, prefix="video_"),
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
