from __future__ import annotations

from .connection import _now, get_connection


def upsert_comment_author(author: dict) -> None:
    """Insert or refresh one commenter row with the latest metadata snapshot observed in a
    comment payload.

    `id` is supplied by the caller and is already namespaced — either from the author's
    YouTube channel identity or from a comment-scoped fallback — so two commenters who
    merely share a display name can never collapse into one row.
    """
    row = {**author, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO comment_authors (id, youtube_channel_id, display_name, profile_image_url,
                channel_url, updated_at)
            VALUES (:id, :youtube_channel_id, :display_name, :profile_image_url, :channel_url,
                :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                youtube_channel_id = excluded.youtube_channel_id,
                display_name = excluded.display_name,
                profile_image_url = excluded.profile_image_url,
                channel_url = excluded.channel_url,
                updated_at = excluded.updated_at
            """,
            row,
        )


def upsert_comment(comment: dict) -> None:
    """Insert or replace one top-level comment row.

    The caller must have upserted the referenced author first, since `author_id` is a
    non-null foreign key and every connection enforces foreign keys.
    """
    row = {**comment, "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO comments (id, thread_id, video_id, author_id, text, like_count,
                total_reply_count, published_at, youtube_updated_at, updated_at)
            VALUES (:id, :thread_id, :video_id, :author_id, :text, :like_count,
                :total_reply_count, :published_at, :youtube_updated_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                thread_id = excluded.thread_id,
                video_id = excluded.video_id,
                author_id = excluded.author_id,
                text = excluded.text,
                like_count = excluded.like_count,
                total_reply_count = excluded.total_reply_count,
                published_at = excluded.published_at,
                youtube_updated_at = excluded.youtube_updated_at,
                updated_at = excluded.updated_at
            """,
            row,
        )


def get_comment_ids_for_video(video_id: str) -> set[str]:
    """Return the IDs of every stored top-level comment for one video.

    The incremental scan uses this both to detect that a video has no local comments at
    all (empty set) and to recognize the boundary item where its page walk can stop.
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM comments WHERE video_id = ?", (video_id,)).fetchall()
    return {row["id"] for row in rows}


def delete_orphan_comment_authors() -> int:
    """Delete commenter rows no comment references any more. Returns the number deleted.

    Kept independent of the comment cascade: a video pruned after the Comments stage
    cascade-deletes its comments and leaves their authors behind, and those are removed on
    the next successful Comments run rather than by the delete that orphaned them.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM comment_authors
            WHERE NOT EXISTS (
                SELECT 1 FROM comments WHERE comments.author_id = comment_authors.id
            )
            """
        )
        return cursor.rowcount


# Deterministic ORDER BY fragments, selected by key only. Every sort ends in a unique
# column so equal published times or like counts can never page-shuffle a row.
COMMENT_SORT_CLAUSES: dict[str, str] = {
    "newest": "c.published_at DESC, c.id DESC",
    "oldest": "c.published_at ASC, c.id ASC",
    "likes": "c.like_count DESC, c.published_at DESC, c.id DESC",
}

DEFAULT_COMMENT_SORT = "newest"


def _query_comments(
    page: int,
    page_size: int,
    sort_by: str,
    text: str | None,
    video_title: str | None,
    author: str | None,
    start_date: str | None,
    end_date: str | None,
    content_type: str | None,
    video_id: str | None = None,
    playlist_id: str | None = None,
) -> tuple[list[dict], int]:
    """Return one page of comments joined to their author and parent video, plus the total.

    The only SQL interpolated here is the allow-listed ORDER BY fragment; every value the
    caller supplies is bound. `playlist_id` scopes through an `EXISTS` so a video listed
    twice in a playlist still yields each of its comments exactly once.
    """
    order_by = COMMENT_SORT_CLAUSES.get(sort_by, COMMENT_SORT_CLAUSES[DEFAULT_COMMENT_SORT])
    offset = (page - 1) * page_size

    conditions: list[str] = []
    params: list[object] = []
    if video_id:
        conditions.append("c.video_id = ?")
        params.append(video_id)
    if playlist_id:
        conditions.append(
            "EXISTS (SELECT 1 FROM playlist_items pi"
            " WHERE pi.playlist_id = ? AND pi.video_id = c.video_id)"
        )
        params.append(playlist_id)
    if text:
        conditions.append("c.text LIKE ?")
        params.append(f"%{text}%")
    if video_title:
        conditions.append("v.title LIKE ?")
        params.append(f"%{video_title}%")
    if author:
        conditions.append("ca.display_name LIKE ?")
        params.append(f"%{author}%")
    if start_date:
        conditions.append("c.published_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("c.published_at <= ?")
        params.append(end_date + "T23:59:59")
    if content_type:
        conditions.append("v.content_type = ?")
        params.append(content_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    joins = """
        FROM comments c
        JOIN comment_authors ca ON ca.id = c.author_id
        JOIN videos v ON v.id = c.video_id
    """
    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) {joins} {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT c.*,
                ca.youtube_channel_id AS author_youtube_channel_id,
                ca.display_name AS author_display_name,
                ca.profile_image_url AS author_profile_image_url,
                ca.channel_url AS author_channel_url,
                v.title AS video_title,
                v.content_type AS video_content_type
            {joins}
            {where}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return [dict(row) for row in rows], total


def get_comments(
    page: int = 1,
    page_size: int = 50,
    sort_by: str = DEFAULT_COMMENT_SORT,
    text: str | None = None,
    video_title: str | None = None,
    author: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
) -> tuple[list[dict], int]:
    """Return a page of channel-wide comments with optional filters, plus the total count."""
    return _query_comments(
        page, page_size, sort_by, text, video_title, author, start_date, end_date, content_type
    )


def get_video_comments(
    video_id: str,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = DEFAULT_COMMENT_SORT,
    text: str | None = None,
    author: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict], int]:
    """Return a page of one video's comments with optional filters, plus the total count.

    Video title and content type are fixed by the scope itself, so neither is offered as a
    filter here.
    """
    return _query_comments(
        page, page_size, sort_by, text, None, author, start_date, end_date, None,
        video_id=video_id,
    )


def get_playlist_comments(
    playlist_id: str,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = DEFAULT_COMMENT_SORT,
    text: str | None = None,
    video_title: str | None = None,
    author: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    content_type: str | None = None,
) -> tuple[list[dict], int]:
    """Return a page of comments on one playlist's videos with optional filters, plus the
    total count."""
    return _query_comments(
        page, page_size, sort_by, text, video_title, author, start_date, end_date, content_type,
        playlist_id=playlist_id,
    )
