"""Shared test infrastructure: an isolated per-test SQLite database, deterministic row
factories, a complete-dataset seeder, and a lifespan-free FastAPI test app builder."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from database import (
    Comment,
    CommentAuthor,
    FxRate,
    Playlist,
    PlaylistItem,
    SyncCoverage,
    SyncRun,
    Video,
    VideoAnalytics,
    VideoTrafficSource,
    connection,
    reader,
    writer,
)
from database.dataclasses import Row
from sync.write_preparation import related_video_rows, search_term_rows

# Captured once at import time, before any test patches connection._DB_PATH, so later
# comparisons are always against the real application database path rather than
# whatever a previous test happened to patch it to.
APPLICATION_DB_PATH = connection._DB_PATH

FIXED_NOW = "2024-06-01T00:00:00+00:00"


@contextmanager
def freeze_now(iso_timestamp: str = FIXED_NOW) -> Generator[None]:
    """Freeze database timestamps for the duration of the context."""
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> "datetime":  # type: ignore[override]
            return datetime.fromisoformat(iso_timestamp).astimezone(tz)

    with mock.patch.object(connection, "datetime", _FrozenDatetime):
        yield


class IsolatedDatabaseTestCase(unittest.TestCase):
    """Base case that gives each test a fresh, schema-initialized, throwaway SQLite database.

    Refuses to patch connection._DB_PATH to a path that resolves to the real application
    database, so a bug in the isolation setup fails loudly instead of touching real data.
    """

    def setUp(self) -> None:
        # get_connection() commits but never closes, so Windows still holds the WAL file
        # open at teardown; leaving the temp file behind is harmless.
        tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmpdir.cleanup)

        test_db_path = Path(tmpdir.name) / "test.db"
        if test_db_path.resolve() == APPLICATION_DB_PATH.resolve():
            raise AssertionError("Refusing to initialize the application database as a test database")

        patcher = mock.patch.object(connection, "_DB_PATH", test_db_path)
        self.addCleanup(patcher.stop)
        patcher.start()

        database.init_db()


def covered_periods(collector: str, video_id: str, start_key: str, end_key: str) -> set[str]:
    """Return stored completed period keys for a video and collector within an inclusive range."""
    rows = reader.select(SyncCoverage, ("period_key",), where=[
        ("collector", "=", collector),
        ("video_id", "=", video_id),
        ("period_key", ">=", start_key),
        ("period_key", "<=", end_key),
    ])
    return {row.period_key for row in rows if row.period_key is not None}


class StageReads:
    """In-memory stand-in for the reader calls sync stages make; install with patch_stage_reads()."""

    def __init__(self) -> None:
        self.videos: list[Video] = []
        self.covered: set[str] = set()
        self.stored_video_ids: list[str] = []
        self.comment_ids: set[str] = set()
        self.last_fx_rate: FxRate | None = None

    def fetch(self, model: type, query: reader.Query, **kwargs: object) -> list[Video]:
        """Return the owned-video worklist."""
        assert model is Video, model
        return list(self.videos)

    def select(self, model: type, fields: object = None, **kwargs: object) -> list:
        """Return covered periods, stored video IDs, or stored comment IDs by row class."""
        if model is SyncCoverage:
            return [SyncCoverage(period_key=key) for key in sorted(self.covered)]
        if model is Video:
            return [Video(id=video_id) for video_id in self.stored_video_ids]
        if model is Comment:
            return [Comment(id=comment_id) for comment_id in sorted(self.comment_ids)]
        raise AssertionError(f"unexpected select of {model.__name__}")

    def select_one(self, model: type, fields: object = None, *, where: object = (), **kwargs: object) -> Row | None:
        """Return the latest stored FX rate, or the worklist video matching an ID lookup."""
        if model is FxRate:
            return self.last_fx_rate
        assert model is Video, model
        video_id = dict((column, value) for column, _, value in where)["id"]  # type: ignore[attr-defined]
        return next((video for video in self.videos if video.id == video_id), None)


def patch_stage_reads() -> StageReads:
    """Route sync.stages reader calls to a fresh StageReads until mock.patch.stopall()."""
    reads = StageReads()
    for name in ("fetch", "select", "select_one"):
        mock.patch(f"sync.stages.reader.{name}", side_effect=getattr(reads, name)).start()
    return reads


class StageWrites:
    """Records the rows and deletes sync stages send to the writer; install with patch_stage_writes()."""

    def __init__(self) -> None:
        self.rows: list[Row] = []
        self.fail: Callable[[Row], None] | None = None
        self.deletes: list[tuple[type, list[object]]] = []
        self.deleted: dict[type, int] = {}

    def write(self, row: Row, **kwargs: object) -> int:
        """Record one row, first letting `fail` raise for it."""
        return self.write_many([row])

    def write_many(self, rows: Iterable[Row], **kwargs: object) -> int:
        """Record a batch of rows and return its size, first letting `fail` raise for any of them."""
        batch = list(rows)
        if self.fail is not None:
            for row in batch:
                self.fail(row)
        self.rows.extend(batch)
        return len(batch)

    def delete(self, model: type, *, where: Sequence[object], **kwargs: object) -> int:
        """Record one filtered delete and return the count configured in `deleted` for its class."""
        self.deletes.append((model, list(where)))
        return self.deleted.get(model, 0)

    def of(self, model: type) -> list:
        """Return the recorded rows of one class, in write order."""
        return [row for row in self.rows if type(row) is model]

    def deletes_of(self, model: type) -> list[list[object]]:
        """Return the recorded delete predicates for one class, in call order."""
        return [where for deleted, where in self.deletes if deleted is model]


def patch_stage_writes() -> StageWrites:
    """Route sync.stages writer calls to a fresh StageWrites until mock.patch.stopall()."""
    writes = StageWrites()
    for name in ("write", "write_many", "delete"):
        mock.patch(f"sync.stages.writer.{name}", side_effect=getattr(writes, name)).start()
    return writes


def owned_videos(*video_ids: str, title: str | None = "T", published_at: str | None = None) -> list[Video]:
    """Return worklist rows for owned videos sharing a title and publish time."""
    return [Video(id=video_id, title=title, published_at=published_at) for video_id in video_ids]


def create_test_app(*routers) -> FastAPI:
    """Return a plain FastAPI app with the given routers and no application lifespan."""
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return app


def create_test_client(*routers) -> TestClient:
    """Return a TestClient for a lifespan-free app built from the given routers."""
    return TestClient(create_test_app(*routers))


# ---------------------------------------------------------------------------
# Deterministic row factories
# ---------------------------------------------------------------------------


def make_video(
    video_id: str,
    title: str = "Video Title",
    *,
    own: bool = True,
    channel_id: str = "c1",
    description: str = "",
    published_at: str | None = "2024-01-01T00:00:00Z",
    duration_seconds: int = 100,
    thumbnail_url: str = "",
    content_type: str | None = "video",
    privacy_status: str = "public",
    view_count: int = 0,
    like_count: int = 0,
    comment_count: int = 0,
    updated_at: str = FIXED_NOW,
) -> Video:
    """Return a Video row, owned unless told otherwise, with caller-overridable defaults."""
    return Video(
        id=video_id, channel_id=channel_id, title=title, description=description,
        published_at=published_at, duration_seconds=duration_seconds, thumbnail_url=thumbnail_url,
        content_type=content_type, privacy_status=privacy_status, view_count=view_count,
        like_count=like_count, comment_count=comment_count, own=own, updated_at=updated_at,
    )


def make_playlist(
    playlist_id: str,
    title: str = "Playlist",
    *,
    description: str = "",
    published_at: str | None = "2024-01-01T00:00:00Z",
    thumbnail_url: str | None = "",
    item_count: int = 0,
    updated_at: str = FIXED_NOW,
) -> Playlist:
    """Return a Playlist row with caller-overridable defaults."""
    return Playlist(
        id=playlist_id, title=title, description=description, published_at=published_at,
        thumbnail_url=thumbnail_url, item_count=item_count, updated_at=updated_at,
    )


def make_playlist_item(
    item_id: str, playlist_id: str, video_id: str | None, position: int = 0, *, updated_at: str = FIXED_NOW
) -> PlaylistItem:
    """Return a PlaylistItem row."""
    return PlaylistItem(
        id=item_id, playlist_id=playlist_id, video_id=video_id, position=position, updated_at=updated_at
    )


def make_video_analytics(
    video_id: str,
    day: str,
    *,
    views: int = 0,
    watch_time_minutes: float = 0,
    estimated_revenue: float = 0.0,
    average_view_duration_seconds: float = 0,
    average_view_percentage: float = 0.0,
    likes: int = 0,
    subscribers_gained: int = 0,
    subscribers_lost: int = 0,
    updated_at: str = FIXED_NOW,
) -> VideoAnalytics:
    """Return a VideoAnalytics row with caller-overridable defaults."""
    return VideoAnalytics(
        video_id=video_id, date=day, views=views, watch_time_minutes=watch_time_minutes,
        estimated_revenue=estimated_revenue, average_view_duration_seconds=average_view_duration_seconds,
        average_view_percentage=average_view_percentage, likes=likes,
        subscribers_gained=subscribers_gained, subscribers_lost=subscribers_lost, updated_at=updated_at,
    )


def make_traffic_source(
    video_id: str,
    day: str,
    traffic_source_type: str = "SEARCH",
    *,
    views: int = 0,
    watch_time_minutes: float = 0,
    updated_at: str = FIXED_NOW,
) -> VideoTrafficSource:
    """Return a VideoTrafficSource row with caller-overridable defaults."""
    return VideoTrafficSource(
        video_id=video_id, date=day, traffic_source_type=traffic_source_type, views=views,
        watch_time_minutes=watch_time_minutes, updated_at=updated_at,
    )


def make_fx_rate(day: str, usd_to_sgd: float, *, updated_at: str = FIXED_NOW) -> FxRate:
    """Return an FxRate row."""
    return FxRate(date=day, usd_to_sgd=usd_to_sgd, updated_at=updated_at)


def make_search_term(search_term: str = "term", *, views: int = 1) -> dict:
    """Return a search-term API response row, shaped for write_preparation.search_term_rows()."""
    return {"search_term": search_term, "views": views}


def make_related_referrer(referrer_video_id: str = "ref-1", *, views: int = 1) -> dict:
    """Return a Related Video API response row, shaped for write_preparation.related_video_rows()."""
    return {"referrer_video_id": referrer_video_id, "views": views}


def make_coverage(
    collector: str, video_id: str, period_keys: Iterable[str], *, completed_at: str = FIXED_NOW
) -> list[SyncCoverage]:
    """Return one completed SyncCoverage row per period key."""
    return [
        SyncCoverage(collector=collector, video_id=video_id, period_key=key, completed_at=completed_at)
        for key in period_keys
    ]


def make_comment_author(
    author_id: str,
    display_name: str,
    *,
    youtube_channel_id: str | None = None,
    profile_image_url: str | None = None,
    channel_url: str | None = None,
    updated_at: str = FIXED_NOW,
) -> CommentAuthor:
    """Return a CommentAuthor row."""
    return CommentAuthor(
        id=author_id, youtube_channel_id=youtube_channel_id, display_name=display_name,
        profile_image_url=profile_image_url, channel_url=channel_url, updated_at=updated_at,
    )


def make_comment(
    comment_id: str,
    video_id: str,
    author_id: str,
    *,
    text: str = "a comment",
    published_at: str = "2024-01-01T00:00:00Z",
    like_count: int = 0,
    total_reply_count: int = 0,
    updated_at: str = FIXED_NOW,
) -> Comment:
    """Return a Comment row."""
    return Comment(
        id=comment_id, thread_id=f"thread-{comment_id}", video_id=video_id, author_id=author_id,
        text=text, like_count=like_count, total_reply_count=total_reply_count,
        published_at=published_at, youtube_updated_at=published_at, updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# Complete dataset seeder
# ---------------------------------------------------------------------------


def seed_dataset() -> None:
    """Seed a deterministic dataset spanning all required tables."""
    with freeze_now():
        writer.write_many([
            make_video("v-1", "Alpha Video", published_at="2024-01-01T00:00:00Z",
                       content_type="video", privacy_status="public", view_count=100, like_count=10, comment_count=2),
            make_video("v-2", "Beta Short", published_at="2024-01-02T00:00:00Z",
                       content_type="short", privacy_status="public", view_count=200, like_count=20, comment_count=3),
            make_video("v-3", "Gamma Video", published_at="2024-01-03T00:00:00Z",
                       content_type="video", privacy_status="private", view_count=50, like_count=5, comment_count=0),
            make_video("v-4", "Delta Short", published_at="2024-01-04T00:00:00Z",
                       content_type="short", privacy_status="unlisted", view_count=75, like_count=7, comment_count=1),
        ])

        writer.write_many([
            make_playlist("p-full", "Full Playlist", item_count=2),
            make_playlist("p-empty", "Empty Playlist", item_count=0),
        ])
        writer.write_many([
            make_playlist_item("pi-1", "p-full", "v-1", 0),
            make_playlist_item("pi-2", "p-full", "v-1", 1),  # duplicate membership
            make_playlist_item("pi-3", "p-full", "v-2", 2),
            make_playlist_item("pi-4", "p-full", "missing-video", 3),  # dangling membership
        ])

        # 2024-01-05 intentionally has no FX row so callers can assert zero-contribution behavior.
        writer.write_many([
            make_video_analytics("v-1", "2024-01-05", views=100, watch_time_minutes=50, estimated_revenue=1.0),
            make_video_analytics("v-1", "2024-01-06", views=150, watch_time_minutes=60, estimated_revenue=2.0),
            make_video_analytics("v-2", "2024-01-06", views=80, watch_time_minutes=30, estimated_revenue=0.5),
        ])

        writer.write_many([
            make_traffic_source("v-1", "2024-01-05", "SEARCH", views=60, watch_time_minutes=30),
            make_traffic_source("v-1", "2024-01-05", "SUGGESTED", views=40, watch_time_minutes=20),
            make_traffic_source("v-1", "2024-01-06", "SEARCH", views=90, watch_time_minutes=40),
            make_traffic_source("v-2", "2024-01-06", "SEARCH", views=80, watch_time_minutes=30),
        ])

        writer.write(make_fx_rate("2024-01-06", 1.35))

        writer.write_many(search_term_rows(
            "v-1", "2024-01", [make_search_term("alpha tutorial", views=6)], updated_at=FIXED_NOW
        ))
        writer.write_many(related_video_rows(
            "v-1", "2024-01", [make_related_referrer("v-2", views=4)], updated_at=FIXED_NOW
        ))

        for collector in ("video_analytics", "video_traffic_sources", "search_insights", "related_video_insights"):
            writer.write_many(make_coverage(collector, "v-1", ["2024-01"]))

        writer.write(make_comment_author("channel:UC1", "Ann Author", youtube_channel_id="UC1"))
        writer.write(make_comment("c-1", "v-1", "channel:UC1", text="great video", published_at="2024-01-10T00:00:00Z"))

        writer.write(SyncRun(
            batch_id="batch-seed", sync_type="videos", scope="incremental", status="success",
            started_at=database.now(), completed_at=database.now(), rows_fetched=4, rows_written=4, rows_deleted=0,
        ))
        writer.write(SyncRun(
            batch_id="batch-seed", sync_type="fx_rates", scope="incremental", status="failed",
            started_at=database.now(), completed_at=database.now(), error_message="quota exceeded",
        ))


class SeededDatabaseTestCase(IsolatedDatabaseTestCase):
    """An IsolatedDatabaseTestCase pre-populated with the complete deterministic dataset."""

    def setUp(self) -> None:
        super().setUp()
        seed_dataset()
