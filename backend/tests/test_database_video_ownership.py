from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import database
from database import writer
from sync import stages
from sync.stages import SyncCounts
from sync.write_preparation import search_term_rows
from database import Video, reader
from database.reports import analytics, catalog, traffic, video_statistics
from routes import router
from routes.video_scope import resolve_playlist_video_ids
from tests.support import (
    FIXED_NOW,
    IsolatedDatabaseTestCase,
    create_test_client,
    make_comment,
    make_comment_author,
    make_playlist,
    make_playlist_item,
    make_search_term,
    make_traffic_source,
    make_video,
    make_video_analytics,
)

_MIGRATION_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "issue-48-migration.py"
_spec = importlib.util.spec_from_file_location("issue_48_migration", _MIGRATION_SCRIPT)
assert _spec is not None and _spec.loader is not None
_migration_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration_module)
migrate_videos_own = _migration_module.migrate

_client = create_test_client(router)


def _get(path: str, **params: str) -> dict:
    """Return a successful endpoint response body."""
    response = _client.get(path, params=params)
    assert response.status_code == 200, (path, response.status_code)
    return response.json()


def _worklist_ids(published_through: str | None = None) -> list[str | None]:
    """Return the sync stages' owned-video worklist IDs in processing order."""
    return [video.id for video in catalog.owned_video_worklist(published_through)]


class VideosOwnSchemaTest(IsolatedDatabaseTestCase):
    def test_fresh_database_defaults_own_to_true(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        with database.get_connection() as conn:
            row = conn.execute("SELECT own FROM videos WHERE id = 'v-1'").fetchone()
        self.assertEqual(row["own"], 1)

    def test_own_column_rejects_values_outside_zero_or_one(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        with self.assertRaises(sqlite3.IntegrityError):
            with database.get_connection() as conn:
                conn.execute("UPDATE videos SET own = 2 WHERE id = 'v-1'")

    def test_repeated_init_db_is_safe(self) -> None:
        database.init_db()
        database.init_db()
        with database.get_connection() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(videos)")}
        self.assertIn("own", columns)


class MigrateVideosOwnColumnTest(IsolatedDatabaseTestCase):
    def _drop_own_column(self) -> None:
        """Recreate videos without `own`, simulating a pre-Issue-48 database."""
        with database.get_connection() as conn:
            conn.executescript(
                """
                ALTER TABLE videos RENAME TO videos_new_schema;
                CREATE TABLE videos (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    published_at TEXT,
                    duration_seconds INTEGER,
                    thumbnail_url TEXT,
                    content_type TEXT,
                    privacy_status TEXT,
                    view_count INTEGER,
                    like_count INTEGER,
                    comment_count INTEGER,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO videos (id, channel_id, title, description, published_at, duration_seconds,
                    thumbnail_url, content_type, privacy_status, view_count, like_count, comment_count, updated_at)
                SELECT id, channel_id, title, description, published_at, duration_seconds,
                    thumbnail_url, content_type, privacy_status, view_count, like_count, comment_count, updated_at
                FROM videos_new_schema;
                DROP TABLE videos_new_schema;
                """
            )

    def test_migration_adds_own_column_defaulting_existing_rows_to_owned(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        self._drop_own_column()
        with database.get_connection() as conn:
            columns_before = {row["name"] for row in conn.execute("PRAGMA table_info(videos)")}
        self.assertNotIn("own", columns_before)

        with database.get_connection() as conn:
            added = migrate_videos_own(conn)

        self.assertTrue(added)
        with database.get_connection() as conn:
            row = conn.execute("SELECT own FROM videos WHERE id = 'v-1'").fetchone()
        self.assertEqual(row["own"], 1)

    def test_migration_is_idempotent(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        self._drop_own_column()

        with database.get_connection() as conn:
            first_run_added = migrate_videos_own(conn)
        with database.get_connection() as conn:
            second_run_added = migrate_videos_own(conn)

        self.assertTrue(first_run_added)
        self.assertFalse(second_run_added)

    def test_migration_is_a_no_op_against_an_already_migrated_database(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        with database.get_connection() as conn:
            added = migrate_videos_own(conn)
        self.assertFalse(added)


class OwnedVideoWriteTest(IsolatedDatabaseTestCase):
    """Writing a Video with own=True always stores own=1; the writer only ever raises a
    stored own (0 -> 1), never lowers it."""

    def _set_own(self, video_id: str, own: int) -> None:
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = ? WHERE id = ?", (own, video_id))

    def _get_own(self, video_id: str) -> int:
        with database.get_connection() as conn:
            row = conn.execute("SELECT own FROM videos WHERE id = ?", (video_id,)).fetchone()
        return row["own"]

    def test_upsert_of_a_previously_external_row_promotes_it_to_owned(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        self._set_own("v-1", 0)
        self.assertEqual(self._get_own("v-1"), 0)

        writer.write(make_video("v-1", "Alpha Updated"))

        self.assertEqual(self._get_own("v-1"), 1)

    def test_upsert_of_an_already_owned_row_stays_owned(self) -> None:
        writer.write(make_video("v-1", "Alpha"))
        writer.write(make_video("v-1", "Alpha Updated"))
        self.assertEqual(self._get_own("v-1"), 1)


class ReferrerVideoWriteTest(IsolatedDatabaseTestCase):
    """A Related referrer's metadata row is written with own=True or own=False. An
    existing own=1 is never lowered, and a later owned write can still promote a row
    first written as own=False."""

    def _get_own(self, video_id: str) -> int:
        with database.get_connection() as conn:
            row = conn.execute("SELECT own FROM videos WHERE id = ?", (video_id,)).fetchone()
        return row["own"]

    def test_own_true_writes_an_owned_row(self) -> None:
        writer.write(make_video("ref-1", "Mine", own=True))
        self.assertEqual(self._get_own("ref-1"), 1)

    def test_own_false_writes_an_external_row(self) -> None:
        writer.write(make_video("ref-1", "Other", own=False))
        self.assertEqual(self._get_own("ref-1"), 0)

    def test_new_row_written_as_external_is_queryable_without_being_owned(self) -> None:
        writer.write(make_video("ref-1", "Other", own=False))
        self.assertEqual(_client.get("/videos/ref-1").status_code, 404)
        with database.get_connection() as conn:
            row = conn.execute("SELECT title FROM videos WHERE id = 'ref-1'").fetchone()
        self.assertEqual(row["title"], "Other")

    def test_never_downgrades_an_already_owned_row(self) -> None:
        writer.write(make_video("v-1", "Mine"))
        writer.write(make_video("v-1", "Mine Updated", own=False))
        self.assertEqual(self._get_own("v-1"), 1)

    def test_a_later_confirmed_owned_upsert_promotes_a_row_written_as_external(self) -> None:
        writer.write(make_video("v-1", "First Seen As Referrer", own=False))
        writer.write(make_video("v-1", "Now Confirmed Owned"))
        self.assertEqual(self._get_own("v-1"), 1)


class OwnershipQueryBoundaryTest(IsolatedDatabaseTestCase):
    """A video row with own=0 (only reachable today via a direct write, standing in for
    Step 6's future external-metadata writer) must never surface through any owner-only
    worklist, catalog, statistic, playlist, analytics, traffic-source, search-term, or
    comment query."""

    def setUp(self) -> None:
        super().setUp()
        writer.write(make_video(
            "v-owned", "Owned Video", published_at="2024-01-01T00:00:00Z", view_count=100,
        ))
        writer.write(make_video(
            "v-external", "External Video", published_at="2024-01-02T00:00:00Z", view_count=999,
        ))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-external'")

    def test_owned_video_worklist_excludes_external(self) -> None:
        self.assertEqual(_worklist_ids(), ["v-owned"])

    def test_stored_video_ids_still_include_external(self) -> None:
        self.assertEqual({video.id for video in reader.select(Video, ("id",))}, {"v-owned", "v-external"})

    def test_video_detail_404s_for_external_id(self) -> None:
        self.assertEqual(_client.get("/videos/v-external").status_code, 404)

    def test_video_catalog_excludes_external(self) -> None:
        body = _get("/videos")
        items, total = body["items"], body["total"]
        self.assertEqual(total, 1)
        self.assertEqual([v["id"] for v in items], ["v-owned"])
        self.assertIs(items[0]["own"], True)

    def test_published_videos_exclude_external(self) -> None:
        items = _get("/videos/published")["items"]
        self.assertEqual([v["id"] for v in items], ["v-owned"])

    def test_earliest_published_year_ignores_external(self) -> None:
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-owned'")
        self.assertIsNone(_get("/meta/date-range")["earliest_year"])

    def test_get_video_stats_excludes_external(self) -> None:
        stats = video_statistics.get_video_stats()
        self.assertEqual(stats["total_public"], 1)

    def test_pruning_an_empty_owned_set_deletes_only_owned_rows(self) -> None:
        counts = SyncCounts()
        stages.sync_pruning(counts, set())
        self.assertEqual(counts.rows_deleted, 1)
        with database.get_connection() as conn:
            remaining = {r["id"] for r in conn.execute("SELECT id FROM videos")}
        self.assertEqual(remaining, {"v-external"})

    def test_pruning_a_populated_owned_set_never_deletes_external_rows(self) -> None:
        counts = SyncCounts()
        stages.sync_pruning(counts, {"some-other-owned-id"})
        self.assertEqual(counts.rows_deleted, 1)
        with database.get_connection() as conn:
            remaining = {r["id"] for r in conn.execute("SELECT id FROM videos")}
        self.assertEqual(remaining, {"v-external"})

    def test_pruning_keeps_retained_owned_rows(self) -> None:
        counts = SyncCounts()
        stages.sync_pruning(counts, {"v-owned"})
        self.assertEqual(counts.rows_deleted, 0)
        with database.get_connection() as conn:
            remaining = {r["id"] for r in conn.execute("SELECT id FROM videos")}
        self.assertEqual(remaining, {"v-owned", "v-external"})

    def test_playlist_aggregate_excludes_external_member(self) -> None:
        writer.write(make_playlist("p-1", "Mixed Playlist"))
        writer.write(make_playlist_item("pi-1", "p-1", "v-owned"))
        writer.write(make_playlist_item("pi-2", "p-1", "v-external"))

        playlist = _get("/playlists/p-1")["item"]
        self.assertEqual(playlist["total_views"], 100)

        video_ids = resolve_playlist_video_ids("p-1")
        self.assertEqual(video_ids, ["v-owned"])

        body = _get("/playlists/p-1/videos")
        items, total = body["items"], body["total"]
        self.assertEqual(total, 1)
        self.assertEqual([v["id"] for v in items], ["v-owned"])

    def test_playlist_video_stats_excludes_external_member(self) -> None:
        writer.write(make_playlist("p-1", "Mixed Playlist"))
        writer.write(make_playlist_item("pi-1", "p-1", "v-owned"))
        writer.write(make_playlist_item("pi-2", "p-1", "v-external"))

        stats = video_statistics.get_video_stats(video_ids=resolve_playlist_video_ids("p-1"))
        self.assertEqual(stats["total_public"], 1)

    def test_video_analytics_excludes_external_video(self) -> None:
        writer.write(make_video_analytics("v-owned", "2024-01-05", views=10))
        writer.write(make_video_analytics("v-external", "2024-01-05", views=20))

        self.assertEqual(analytics.daily_analytics(video_ids=["v-external"], fill_content_types=None), [])
        self.assertNotEqual(analytics.daily_analytics(video_ids=["v-owned"], fill_content_types=None), [])

        aggregated = analytics.daily_analytics()
        self.assertEqual(sum(r["views"] for r in aggregated), 10)

        top = _get("/analytics/videos/top")["items"]
        self.assertEqual([v["id"] for v in top], ["v-owned"])

    def test_traffic_sources_exclude_external_video(self) -> None:
        writer.write(make_traffic_source("v-owned", "2024-01-05", views=10))
        writer.write(make_traffic_source("v-external", "2024-01-05", views=20))

        self.assertEqual(traffic.daily_traffic_sources(video_ids=["v-external"]), [])
        self.assertNotEqual(traffic.daily_traffic_sources(video_ids=["v-owned"]), [])

        aggregated = traffic.daily_traffic_sources()
        self.assertEqual(sum(r["views"] for r in aggregated), 10)

        top = traffic.top_videos_by_traffic_source()
        ids = {v["id"] for videos in top.values() for v in videos}
        self.assertEqual(ids, {"v-owned"})

    def test_search_terms_exclude_external_video(self) -> None:
        writer.write_many(search_term_rows("v-owned", "2024-01", [make_search_term("cats", views=5)], updated_at=FIXED_NOW))
        writer.write_many(search_term_rows("v-external", "2024-01", [make_search_term("dogs", views=7)], updated_at=FIXED_NOW))

        self.assertEqual(traffic.search_terms(video_ids=["v-external"]), [])
        self.assertNotEqual(traffic.search_terms(video_ids=["v-owned"]), [])
        self.assertEqual(_client.get("/analytics/videos/v-external/search-insights").status_code, 404)

        terms = _get("/analytics/search-insights")["items"]
        self.assertEqual([t["search_term"] for t in terms], ["cats"])

        videos = _get("/analytics/search-insights/videos", search_term="dogs")["items"]
        self.assertEqual(videos, [])

    def test_comments_exclude_external_video(self) -> None:
        writer.write(make_comment_author("author-1", "Ann"))
        writer.write(make_comment("c-owned", "v-owned", "author-1"))
        writer.write(make_comment("c-external", "v-external", "author-1"))

        body = _get("/comments")
        items, total = body["items"], body["total"]
        self.assertEqual(total, 1)
        self.assertEqual([c["id"] for c in items], ["c-owned"])


class PublishedThroughWorklistBoundaryTest(IsolatedDatabaseTestCase):
    """owned_video_worklist(published_through=...) is the period-aware sync stages'
    pre-loop eligibility filter: a video published after the bound must never reach
    per-video processing, while a video published on the bound (any time of day),
    an older video, or one with no known publish date remains eligible."""

    def setUp(self) -> None:
        super().setUp()
        writer.write(make_video("v-before", "Before", published_at="2024-01-10T00:00:00Z"))
        writer.write(make_video("v-on-bound-early", "On bound early", published_at="2024-01-15T00:00:01Z"))
        writer.write(make_video("v-on-bound-late", "On bound late", published_at="2024-01-15T23:59:59Z"))
        writer.write(make_video("v-after", "After", published_at="2024-01-16T00:00:00Z"))
        writer.write(make_video("v-unknown", "Unknown publish date"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET published_at = NULL WHERE id = 'v-unknown'")
        writer.write(make_video("v-external", "External", published_at="2024-01-01T00:00:00Z"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-external'")

    def test_bounded_call_includes_before_on_bound_and_unknown_only(self) -> None:
        ids = set(_worklist_ids("2024-01-15"))
        self.assertEqual(ids, {"v-before", "v-on-bound-early", "v-on-bound-late", "v-unknown"})

    def test_bounded_call_excludes_a_video_published_after_the_bound(self) -> None:
        ids = _worklist_ids("2024-01-15")
        self.assertNotIn("v-after", ids)

    def test_bounded_call_still_excludes_external_rows(self) -> None:
        ids = _worklist_ids("2024-01-15")
        self.assertNotIn("v-external", ids)

    def test_unbounded_call_still_returns_every_owned_video(self) -> None:
        ids = set(_worklist_ids())
        self.assertEqual(ids, {"v-before", "v-on-bound-early", "v-on-bound-late", "v-after", "v-unknown"})


class WorklistOrderTest(IsolatedDatabaseTestCase):
    """owned_video_worklist() must return a deterministic oldest-first order regardless
    of insertion order: dated rows ascending by published_at, ties broken by ascending
    id, then undated rows last ordered by ascending id. Every SQL-backed per-video sync
    stage relies on this single worklist for its processing order."""

    def setUp(self) -> None:
        super().setUp()
        # IDs are deliberately anti-correlated with publication date — the oldest video
        # ("v-z") has the lexically latest ID and the newest video ("v-a") has the
        # lexically earliest — so an incorrect implementation ordering by id alone (or
        # by insertion/primary-key order) cannot coincidentally pass. "v-m"/"v-n" share
        # a timestamp to prove ties still break by ascending id, and "v-x"/"v-y" are
        # undated to prove undated rows sort last, also by ascending id.
        writer.write(make_video("v-a", "Newest", published_at="2024-03-01T00:00:00Z"))
        writer.write(make_video("v-x", "Undated 1"))
        writer.write(make_video("v-n", "Tied 2", published_at="2024-02-01T00:00:00Z"))
        writer.write(make_video("v-z", "Oldest", published_at="2024-01-01T00:00:00Z"))
        writer.write(make_video("v-y", "Undated 2"))
        writer.write(make_video("v-m", "Tied 1", published_at="2024-02-01T00:00:00Z"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET published_at = NULL WHERE id IN ('v-x', 'v-y')")

    def test_unbounded_worklist_is_dated_oldest_first_then_id_tied_then_undated_by_id(self) -> None:
        ids = _worklist_ids()
        self.assertEqual(ids, ["v-z", "v-m", "v-n", "v-a", "v-x", "v-y"])

    def test_bounded_worklist_keeps_the_same_relative_order_excluding_only_dated_rows_after_the_bound(self) -> None:
        ids = _worklist_ids("2024-02-01")
        self.assertEqual(ids, ["v-z", "v-m", "v-n", "v-x", "v-y"])
