"""Shared test infrastructure: an isolated per-test SQLite database, deterministic row
factories, a complete-dataset seeder, and a lifespan-free FastAPI test app builder."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from database import connection

# Captured once at import time, before any test patches connection._DB_PATH, so later
# comparisons are always against the real application database path rather than
# whatever a previous test happened to patch it to.
APPLICATION_DB_PATH = connection._DB_PATH

FIXED_NOW = "2024-06-01T00:00:00+00:00"


@contextmanager
def freeze_now(iso_timestamp: str = FIXED_NOW) -> Generator[None]:
    """Freeze database.connection._now() to a fixed timestamp for the duration of the block.

    Every database write module did `from .connection import _now`, binding its own
    reference to the same function object, so patching that object's __globals__ entry
    for `datetime` (rather than patching `_now` on each importing module individually)
    is what makes every caller observe the frozen clock.
    """
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
    channel_id: str = "c1",
    description: str = "",
    published_at: str = "2024-01-01T00:00:00Z",
    duration_seconds: int = 100,
    thumbnail_url: str = "",
    content_type: str = "video",
    privacy_status: str = "public",
    view_count: int = 0,
    like_count: int = 0,
    comment_count: int = 0,
) -> dict:
    """Return a video row dict with caller-overridable defaults."""
    return {
        "id": video_id, "channel_id": channel_id, "title": title, "description": description,
        "published_at": published_at, "duration_seconds": duration_seconds,
        "thumbnail_url": thumbnail_url, "content_type": content_type,
        "privacy_status": privacy_status, "view_count": view_count,
        "like_count": like_count, "comment_count": comment_count,
    }


def make_playlist(
    playlist_id: str,
    title: str = "Playlist",
    *,
    description: str = "",
    published_at: str | None = "2024-01-01T00:00:00Z",
    thumbnail_url: str | None = "",
    item_count: int = 0,
) -> dict:
    """Return a playlist row dict with caller-overridable defaults."""
    return {
        "id": playlist_id, "title": title, "description": description,
        "published_at": published_at, "thumbnail_url": thumbnail_url, "item_count": item_count,
    }


def make_playlist_item(item_id: str, playlist_id: str, video_id: str | None, position: int = 0) -> dict:
    """Return a playlist item row dict."""
    return {"id": item_id, "playlist_id": playlist_id, "video_id": video_id, "position": position}


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
) -> dict:
    """Return a video_analytics row dict with caller-overridable defaults."""
    return {
        "video_id": video_id, "date": day, "views": views,
        "watch_time_minutes": watch_time_minutes, "estimated_revenue": estimated_revenue,
        "average_view_duration_seconds": average_view_duration_seconds,
        "average_view_percentage": average_view_percentage, "likes": likes,
        "subscribers_gained": subscribers_gained, "subscribers_lost": subscribers_lost,
    }


def make_traffic_source(
    video_id: str,
    day: str,
    traffic_source_type: str = "SEARCH",
    *,
    views: int = 0,
    watch_time_minutes: float = 0,
) -> dict:
    """Return a video_traffic_sources row dict with caller-overridable defaults."""
    return {
        "video_id": video_id, "date": day, "traffic_source_type": traffic_source_type,
        "views": views, "watch_time_minutes": watch_time_minutes,
    }


def make_fx_rate(day: str, usd_to_sgd: float) -> dict:
    """Return an fx_rates row dict."""
    return {"date": day, "usd_to_sgd": usd_to_sgd}


def make_comment_author(
    author_id: str,
    display_name: str,
    *,
    youtube_channel_id: str | None = None,
    profile_image_url: str | None = None,
    channel_url: str | None = None,
) -> dict:
    """Return a comment_authors row dict."""
    return {
        "id": author_id, "youtube_channel_id": youtube_channel_id, "display_name": display_name,
        "profile_image_url": profile_image_url, "channel_url": channel_url,
    }


def make_comment(
    comment_id: str,
    video_id: str,
    author_id: str,
    *,
    text: str = "a comment",
    published_at: str = "2024-01-01T00:00:00Z",
    like_count: int = 0,
    total_reply_count: int = 0,
) -> dict:
    """Return a comments row dict."""
    return {
        "id": comment_id, "thread_id": f"thread-{comment_id}", "video_id": video_id,
        "author_id": author_id, "text": text, "like_count": like_count,
        "total_reply_count": total_reply_count, "published_at": published_at,
        "youtube_updated_at": published_at,
    }


# ---------------------------------------------------------------------------
# Complete dataset seeder
# ---------------------------------------------------------------------------


def seed_dataset() -> None:
    """Seed a fixed, deterministic dataset covering every issue-required table.

    Videos and Shorts across publication/privacy/content-type boundaries; a populated
    playlist (with a duplicate and a dangling membership) and an empty playlist; daily
    analytics and traffic sources with a date that has no FX rate; FX rates for the
    other analytics dates; and one successful and one failed sync run.
    """
    with freeze_now():
        videos = [
            make_video("v-1", "Alpha Video", published_at="2024-01-01T00:00:00Z",
                       content_type="video", privacy_status="public", view_count=100, like_count=10, comment_count=2),
            make_video("v-2", "Beta Short", published_at="2024-01-02T00:00:00Z",
                       content_type="short", privacy_status="public", view_count=200, like_count=20, comment_count=3),
            make_video("v-3", "Gamma Video", published_at="2024-01-03T00:00:00Z",
                       content_type="video", privacy_status="private", view_count=50, like_count=5, comment_count=0),
            make_video("v-4", "Delta Short", published_at="2024-01-04T00:00:00Z",
                       content_type="short", privacy_status="unlisted", view_count=75, like_count=7, comment_count=1),
        ]
        for video in videos:
            database.upsert_video(video)

        database.upsert_playlist(make_playlist("p-full", "Full Playlist", item_count=2))
        database.upsert_playlist(make_playlist("p-empty", "Empty Playlist", item_count=0))
        items = [
            make_playlist_item("pi-1", "p-full", "v-1", 0),
            make_playlist_item("pi-2", "p-full", "v-1", 1),  # duplicate membership
            make_playlist_item("pi-3", "p-full", "v-2", 2),
            make_playlist_item("pi-4", "p-full", "missing-video", 3),  # dangling membership
        ]
        for item in items:
            database.upsert_playlist_item(item)

        # 2024-01-05 intentionally has no FX row so callers can assert zero-contribution behavior.
        analytics = [
            make_video_analytics("v-1", "2024-01-05", views=100, watch_time_minutes=50, estimated_revenue=1.0),
            make_video_analytics("v-1", "2024-01-06", views=150, watch_time_minutes=60, estimated_revenue=2.0),
            make_video_analytics("v-2", "2024-01-06", views=80, watch_time_minutes=30, estimated_revenue=0.5),
        ]
        for row in analytics:
            database.upsert_video_analytics(row)

        traffic = [
            make_traffic_source("v-1", "2024-01-05", "SEARCH", views=60, watch_time_minutes=30),
            make_traffic_source("v-1", "2024-01-05", "SUGGESTED", views=40, watch_time_minutes=20),
            make_traffic_source("v-1", "2024-01-06", "SEARCH", views=90, watch_time_minutes=40),
            make_traffic_source("v-2", "2024-01-06", "SEARCH", views=80, watch_time_minutes=30),
        ]
        for row in traffic:
            database.upsert_video_traffic_source(row)

        database.upsert_fx_rate(make_fx_rate("2024-01-06", 1.35))

        database.upsert_comment_author(make_comment_author("channel:UC1", "Ann Author", youtube_channel_id="UC1"))
        database.upsert_comment(make_comment("c-1", "v-1", "channel:UC1", text="great video", published_at="2024-01-10T00:00:00Z"))

        success_id = database.create_sync_run("batch-seed", "videos", "incremental", None)
        database.complete_sync_run(success_id, rows_fetched=4, rows_written=4, rows_deleted=0)
        failed_id = database.create_sync_run("batch-seed", "fx_rates", "incremental", None)
        database.fail_sync_run(failed_id, "quota exceeded", rows_fetched=0, rows_written=0, rows_deleted=0)


class SeededDatabaseTestCase(IsolatedDatabaseTestCase):
    """An IsolatedDatabaseTestCase pre-populated with the complete deterministic dataset."""

    def setUp(self) -> None:
        super().setUp()
        seed_dataset()
