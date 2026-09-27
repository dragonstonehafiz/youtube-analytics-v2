from __future__ import annotations

import dataclasses
from collections.abc import Iterable

from .dataclasses import (
    Comment,
    CommentAuthor,
    FxRate,
    Playlist,
    PlaylistItem,
    RelatedVideo,
    Row,
    SearchTerm,
    SyncCoverage,
    SyncRun,
    Video,
    VideoAnalytics,
    VideoTrafficSource,
)

# Row class -> table. Columns are the dataclass fields; tests check both against schema.sql.
TABLES: dict[type[Row], str] = {
    Video: "videos",
    Playlist: "playlists",
    PlaylistItem: "playlist_items",
    VideoAnalytics: "video_analytics",
    VideoTrafficSource: "video_traffic_sources",
    Comment: "comments",
    CommentAuthor: "comment_authors",
    SearchTerm: "search_terms",
    RelatedVideo: "related_videos",
    FxRate: "fx_rates",
    SyncCoverage: "sync_coverage",
    SyncRun: "sync_runs",
}

# Row class -> primary-key columns the writer matches on.
KEYS: dict[type[Row], tuple[str, ...]] = {
    Video: ("id",),
    Playlist: ("id",),
    PlaylistItem: ("id",),
    VideoAnalytics: ("video_id", "date"),
    VideoTrafficSource: ("video_id", "date", "traffic_source_type"),
    Comment: ("id",),
    CommentAuthor: ("id",),
    SearchTerm: ("video_id", "month", "search_term"),
    RelatedVideo: ("target_video_id", "month", "referrer_video_id"),
    FxRate: ("date",),
    SyncCoverage: ("collector", "video_id", "period_key"),
    SyncRun: ("id",),
}

# Row classes whose key SQLite generates when an insert omits it.
GENERATED_KEYS: frozenset[type[Row]] = frozenset({SyncRun})

# Columns an update may only raise, never lower: an owned video is never demoted to external.
NON_DECREASING: dict[type[Row], frozenset[str]] = {
    Video: frozenset({"own"}),
}


def table_name(model: type[Row]) -> str:
    """Return the registered table for a row class."""
    try:
        return TABLES[model]
    except KeyError:
        raise ValueError(f"{model.__name__} is not a registered row class") from None


def field_names(model: type[Row]) -> tuple[str, ...]:
    """Return a row class's column names in declaration order."""
    return tuple(field.name for field in dataclasses.fields(model))


def check_fields(model: type[Row], names: Iterable[str]) -> None:
    """Raise when any name is not a column of the row class."""
    unknown = [name for name in names if name not in field_names(model)]
    if unknown:
        raise ValueError(f"{model.__name__} has no fields {unknown}")
