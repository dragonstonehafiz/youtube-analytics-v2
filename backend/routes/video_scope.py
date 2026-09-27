from __future__ import annotations

from fastapi import HTTPException

import database


def resolve_playlist_video_ids(playlist_id: str) -> list[str]:
    """Return valid playlist video IDs or raise 404 when the playlist is missing."""
    if not database.playlist_exists(playlist_id):
        raise HTTPException(status_code=404, detail="Playlist not found")
    return database.get_playlist_video_ids(playlist_id)
