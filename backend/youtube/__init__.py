from __future__ import annotations

from .analytics_api import iter_video_analytics, iter_video_traffic_sources
from .auth import get_credentials
from .data_api import (
    fetch_all_video_ids,
    fetch_playlist_items,
    fetch_playlists,
    fetch_shorts_video_ids,
    fetch_uploads_playlist_id,
    fetch_videos,
)

__all__ = [
    "fetch_all_video_ids",
    "fetch_playlist_items",
    "fetch_playlists",
    "fetch_shorts_video_ids",
    "fetch_uploads_playlist_id",
    "fetch_videos",
    "get_credentials",
    "iter_video_analytics",
    "iter_video_traffic_sources",
]
