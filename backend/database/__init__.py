from __future__ import annotations

from . import queries, reader
from .analytics import (
    get_aggregated_analytics,
    get_video_analytics,
    upsert_video_analytics,
)
from .comments import (
    delete_orphan_comment_authors,
    upsert_comment,
    upsert_comment_author,
)
from .connection import get_connection, init_db
from .dataclasses import (
    Comment,
    CommentAuthor,
    FxRate,
    Playlist,
    PlaylistItem,
    RelatedVideo,
    SearchTerm,
    SyncCoverage,
    SyncRun,
    Video,
    VideoAnalytics,
    VideoTrafficSource,
)
from .fx_rates import upsert_fx_rate
from .playlists import (
    delete_playlist_items,
    delete_playlists_not_in,
    upsert_playlist,
    upsert_playlist_item,
)
from .related_videos import (
    get_related_video_referrers,
    upsert_related_videos,
)
from .search_terms import upsert_search_terms
from .sync_coverage import upsert_coverage
from .sync_runs import (
    cancel_sync_run,
    complete_sync_run,
    create_sync_run,
    fail_sync_run,
    get_sync_runs,
    mark_incomplete_sync_runs,
)
from .traffic_sources import (
    get_aggregated_traffic_sources,
    get_top_videos_by_traffic_source,
    get_video_traffic_sources,
    upsert_video_traffic_source,
)
from .video_statistics import get_video_stats
from .videos import (
    delete_videos_not_in,
    upsert_own_video,
    upsert_related_video,
)

__all__ = [
    "Comment",
    "CommentAuthor",
    "FxRate",
    "Playlist",
    "PlaylistItem",
    "RelatedVideo",
    "SearchTerm",
    "SyncCoverage",
    "SyncRun",
    "Video",
    "VideoAnalytics",
    "VideoTrafficSource",
    "cancel_sync_run",
    "complete_sync_run",
    "create_sync_run",
    "delete_orphan_comment_authors",
    "delete_playlist_items",
    "delete_playlists_not_in",
    "delete_videos_not_in",
    "fail_sync_run",
    "get_aggregated_analytics",
    "get_aggregated_traffic_sources",
    "get_connection",
    "get_related_video_referrers",
    "get_sync_runs",
    "get_top_videos_by_traffic_source",
    "get_video_analytics",
    "get_video_stats",
    "get_video_traffic_sources",
    "init_db",
    "mark_incomplete_sync_runs",
    "queries",
    "reader",
    "upsert_comment",
    "upsert_comment_author",
    "upsert_coverage",
    "upsert_fx_rate",
    "upsert_own_video",
    "upsert_playlist",
    "upsert_playlist_item",
    "upsert_related_video",
    "upsert_related_videos",
    "upsert_search_terms",
    "upsert_video_analytics",
    "upsert_video_traffic_source",
]
