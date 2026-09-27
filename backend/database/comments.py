from __future__ import annotations

from .connection import _now, get_connection


def upsert_comment_author(author: dict) -> None:
    """Insert or refresh a comment author's latest metadata."""
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
    """Insert or replace a top-level comment row."""
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


def delete_orphan_comment_authors() -> int:
    """Delete unreferenced comment authors and return the number deleted."""
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
