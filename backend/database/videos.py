from __future__ import annotations

from .connection import _now, get_connection


def _upsert_video_row(video: dict, *, own: bool) -> None:
    """Upsert a video while preserving known content type and owned status."""
    row = {**video, "own": int(own), "updated_at": _now()}
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO videos (id, channel_id, title, description, published_at, duration_seconds,
                thumbnail_url, content_type, privacy_status, view_count, like_count, comment_count,
                own, updated_at)
            VALUES (:id, :channel_id, :title, :description, :published_at, :duration_seconds,
                :thumbnail_url, :content_type, :privacy_status, :view_count, :like_count, :comment_count,
                :own, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                channel_id = excluded.channel_id,
                title = excluded.title,
                description = excluded.description,
                published_at = excluded.published_at,
                duration_seconds = excluded.duration_seconds,
                thumbnail_url = excluded.thumbnail_url,
                content_type = COALESCE(excluded.content_type, content_type),
                privacy_status = excluded.privacy_status,
                view_count = excluded.view_count,
                like_count = excluded.like_count,
                comment_count = excluded.comment_count,
                own = MAX(own, excluded.own),
                updated_at = excluded.updated_at
            """,
            row,
        )


def upsert_own_video(video: dict) -> None:
    """Upsert a confirmed channel-owned video."""
    _upsert_video_row(video, own=True)


def upsert_related_video(video: dict, *, own: bool) -> None:
    """Upsert a Related Video referrer's metadata without downgrading ownership."""
    _upsert_video_row(video, own=own)


def delete_videos_not_in(ids: list[str]) -> int:
    """Delete owned videos absent from the given IDs and return the number deleted."""
    with get_connection() as conn:
        if not ids:
            cursor = conn.execute("DELETE FROM videos WHERE own = 1")
        else:
            placeholders = ",".join("?" * len(ids))
            cursor = conn.execute(f"DELETE FROM videos WHERE own = 1 AND id NOT IN ({placeholders})", ids)
        return cursor.rowcount
