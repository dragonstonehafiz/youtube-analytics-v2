from __future__ import annotations

from fastapi import HTTPException

from database import Playlist, Video, reader
from database.reports import catalog


def require_owned_video(video_id: str) -> None:
    """Raise 404 unless the video is stored and channel-owned."""
    if reader.select_one(Video, ("id",), where=[("id", "=", video_id), ("own", "=", True)]) is None:
        raise HTTPException(status_code=404, detail="Video not found")


def require_playlist(playlist_id: str) -> None:
    """Raise 404 unless the playlist is stored."""
    if reader.select_one(Playlist, ("id",), where=[("id", "=", playlist_id)]) is None:
        raise HTTPException(status_code=404, detail="Playlist not found")


def resolve_playlist_video_ids(playlist_id: str) -> list[str]:
    """Return valid playlist video IDs or raise 404 when the playlist is missing."""
    require_playlist(playlist_id)
    return catalog.playlist_video_ids(playlist_id)
