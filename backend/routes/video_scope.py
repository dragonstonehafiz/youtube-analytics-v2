from __future__ import annotations

from fastapi import Request

from database import Playlist, Video, reader
from database.reports import catalog
from ._shared import require_found


def require_owned_video(video_id: str) -> None:
    """Raise 404 unless the video is stored and channel-owned."""
    require_found(reader.select_one(Video, ("id",), where=[("id", "=", video_id), ("own", "=", True)]), "Video")


def require_playlist(playlist_id: str) -> None:
    """Raise 404 unless the playlist is stored."""
    require_found(reader.select_one(Playlist, ("id",), where=[("id", "=", playlist_id)]), "Playlist")


def scope_video_ids(request: Request) -> list[str] | None:
    """Return None on a channel route, or the playlist's video IDs on a route with a playlist_id path parameter."""
    playlist_id = request.path_params.get("playlist_id")
    if playlist_id is None:
        return None
    return require_found(catalog.playlist_video_ids(playlist_id), "Playlist")
