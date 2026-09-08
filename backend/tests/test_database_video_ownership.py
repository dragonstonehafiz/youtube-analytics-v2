from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import database
from tests.support import (
    IsolatedDatabaseTestCase,
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


class VideosOwnSchemaTest(IsolatedDatabaseTestCase):
    def test_fresh_database_defaults_own_to_true(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        with database.get_connection() as conn:
            row = conn.execute("SELECT own FROM videos WHERE id = 'v-1'").fetchone()
        self.assertEqual(row["own"], 1)

    def test_own_column_rejects_values_outside_zero_or_one(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
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
        database.upsert_own_video(make_video("v-1", "Alpha"))
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
        database.upsert_own_video(make_video("v-1", "Alpha"))
        self._drop_own_column()

        with database.get_connection() as conn:
            first_run_added = migrate_videos_own(conn)
        with database.get_connection() as conn:
            second_run_added = migrate_videos_own(conn)

        self.assertTrue(first_run_added)
        self.assertFalse(second_run_added)

    def test_migration_is_a_no_op_against_an_already_migrated_database(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        with database.get_connection() as conn:
            added = migrate_videos_own(conn)
        self.assertFalse(added)


class UpsertOwnVideoConflictTest(IsolatedDatabaseTestCase):
    """upsert_own_video() always writes own=1; a row's own value can only ever move
    0 -> 1 (via the ON CONFLICT MAX rule), never back down. upsert_own_video() itself
    has no own parameter and never writes own=0 — only upsert_related_video() (Step 6)
    can write an external row, tested separately below."""

    def _set_own(self, video_id: str, own: int) -> None:
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = ? WHERE id = ?", (own, video_id))

    def _get_own(self, video_id: str) -> int:
        with database.get_connection() as conn:
            row = conn.execute("SELECT own FROM videos WHERE id = ?", (video_id,)).fetchone()
        return row["own"]

    def test_upsert_of_a_previously_external_row_promotes_it_to_owned(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        self._set_own("v-1", 0)
        self.assertEqual(self._get_own("v-1"), 0)

        database.upsert_own_video(make_video("v-1", "Alpha Updated"))

        self.assertEqual(self._get_own("v-1"), 1)

    def test_upsert_of_an_already_owned_row_stays_owned(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        database.upsert_own_video(make_video("v-1", "Alpha Updated"))
        self.assertEqual(self._get_own("v-1"), 1)


class UpsertRelatedVideoTest(IsolatedDatabaseTestCase):
    """upsert_related_video() writes a Related referrer's metadata row, classifying
    own per caller-supplied bool. Shares upsert_own_video's no-downgrade ON CONFLICT
    rule: an existing own=1 is never lowered, and a later confirmed-owned upsert (from
    either writer) can still promote a row this one wrote as own=False."""

    def _get_own(self, video_id: str) -> int:
        with database.get_connection() as conn:
            row = conn.execute("SELECT own FROM videos WHERE id = ?", (video_id,)).fetchone()
        return row["own"]

    def test_own_true_writes_an_owned_row(self) -> None:
        database.upsert_related_video(make_video("ref-1", "Mine"), own=True)
        self.assertEqual(self._get_own("ref-1"), 1)

    def test_own_false_writes_an_external_row(self) -> None:
        database.upsert_related_video(make_video("ref-1", "Other"), own=False)
        self.assertEqual(self._get_own("ref-1"), 0)

    def test_new_row_written_as_external_is_queryable_without_being_owned(self) -> None:
        database.upsert_related_video(make_video("ref-1", "Other"), own=False)
        self.assertIsNone(database.get_owned_video("ref-1"))
        with database.get_connection() as conn:
            row = conn.execute("SELECT title FROM videos WHERE id = 'ref-1'").fetchone()
        self.assertEqual(row["title"], "Other")

    def test_never_downgrades_an_already_owned_row(self) -> None:
        database.upsert_own_video(make_video("v-1", "Mine"))
        database.upsert_related_video(make_video("v-1", "Mine Updated"), own=False)
        self.assertEqual(self._get_own("v-1"), 1)

    def test_a_later_confirmed_owned_upsert_promotes_a_row_written_as_external(self) -> None:
        database.upsert_related_video(make_video("v-1", "First Seen As Referrer"), own=False)
        database.upsert_own_video(make_video("v-1", "Now Confirmed Owned"))
        self.assertEqual(self._get_own("v-1"), 1)


class OwnershipQueryBoundaryTest(IsolatedDatabaseTestCase):
    """A video row with own=0 (only reachable today via a direct write, standing in for
    Step 6's future external-metadata writer) must never surface through any owner-only
    worklist, catalog, statistic, playlist, analytics, traffic-source, search-term, or
    comment query."""

    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video(
            "v-owned", "Owned Video", published_at="2024-01-01T00:00:00Z", view_count=100,
        ))
        database.upsert_own_video(make_video(
            "v-external", "External Video", published_at="2024-01-02T00:00:00Z", view_count=999,
        ))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-external'")

    def test_get_owned_video_id_worklist_excludes_external(self) -> None:
        self.assertEqual(database.get_owned_video_ids(), ["v-owned"])

    def test_get_all_video_ids_still_includes_external(self) -> None:
        self.assertEqual(set(database.get_all_video_ids()), {"v-owned", "v-external"})

    def test_get_owned_video_returns_none_for_external_id(self) -> None:
        self.assertIsNone(database.get_owned_video("v-external"))
        assert database.get_owned_video("v-owned") is not None

    def test_get_all_videos_catalog_excludes_external(self) -> None:
        items, total = database.get_all_videos()
        self.assertEqual(total, 1)
        self.assertEqual([v["id"] for v in items], ["v-owned"])
        self.assertIs(items[0]["own"], True)

    def test_get_videos_published_excludes_external(self) -> None:
        items = database.get_videos_published()
        self.assertEqual([v["id"] for v in items], ["v-owned"])

    def test_get_earliest_published_year_ignores_external(self) -> None:
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-owned'")
        self.assertIsNone(database.get_earliest_published_year())

    def test_get_video_stats_excludes_external(self) -> None:
        stats = database.get_video_stats()
        self.assertEqual(stats["total_public"], 1)

    def test_delete_videos_not_in_never_deletes_external_rows(self) -> None:
        deleted = database.delete_videos_not_in([])
        self.assertEqual(deleted, 1)
        with database.get_connection() as conn:
            remaining = {r["id"] for r in conn.execute("SELECT id FROM videos")}
        self.assertEqual(remaining, {"v-external"})

    def test_delete_videos_not_in_with_populated_set_never_deletes_external_rows(self) -> None:
        deleted = database.delete_videos_not_in(["some-other-owned-id"])
        self.assertEqual(deleted, 1)
        with database.get_connection() as conn:
            remaining = {r["id"] for r in conn.execute("SELECT id FROM videos")}
        self.assertEqual(remaining, {"v-external"})

    def test_playlist_aggregate_excludes_external_member(self) -> None:
        database.upsert_playlist(make_playlist("p-1", "Mixed Playlist"))
        database.upsert_playlist_item(make_playlist_item("pi-1", "p-1", "v-owned"))
        database.upsert_playlist_item(make_playlist_item("pi-2", "p-1", "v-external"))

        playlist = database.get_playlist("p-1")
        assert playlist is not None
        self.assertEqual(playlist["total_views"], 100)

        video_ids = database.get_playlist_video_ids("p-1")
        self.assertEqual(video_ids, ["v-owned"])

        items, total = database.get_playlist_videos("p-1")
        self.assertEqual(total, 1)
        self.assertEqual([v["id"] for v in items], ["v-owned"])

    def test_playlist_video_stats_excludes_external_member(self) -> None:
        database.upsert_playlist(make_playlist("p-1", "Mixed Playlist"))
        database.upsert_playlist_item(make_playlist_item("pi-1", "p-1", "v-owned"))
        database.upsert_playlist_item(make_playlist_item("pi-2", "p-1", "v-external"))

        stats = database.get_playlist_video_stats("p-1")
        self.assertEqual(stats["total_public"], 1)

    def test_video_analytics_excludes_external_video(self) -> None:
        database.upsert_video_analytics(make_video_analytics("v-owned", "2024-01-05", views=10))
        database.upsert_video_analytics(make_video_analytics("v-external", "2024-01-05", views=20))

        self.assertEqual(database.get_video_analytics("v-external"), [])
        self.assertNotEqual(database.get_video_analytics("v-owned"), [])

        aggregated = database.get_aggregated_analytics()
        self.assertEqual(sum(r["views"] for r in aggregated), 10)

        top = database.get_top_videos_by_views()
        self.assertEqual([v["id"] for v in top], ["v-owned"])

    def test_traffic_sources_exclude_external_video(self) -> None:
        database.upsert_video_traffic_source(make_traffic_source("v-owned", "2024-01-05", views=10))
        database.upsert_video_traffic_source(make_traffic_source("v-external", "2024-01-05", views=20))

        self.assertEqual(database.get_video_traffic_sources("v-external"), [])
        self.assertNotEqual(database.get_video_traffic_sources("v-owned"), [])

        aggregated = database.get_aggregated_traffic_sources()
        self.assertEqual(sum(r["views"] for r in aggregated), 10)

        top = database.get_top_videos_by_traffic_source()
        ids = {v["id"] for videos in top.values() for v in videos}
        self.assertEqual(ids, {"v-owned"})

    def test_search_terms_exclude_external_video(self) -> None:
        database.upsert_search_terms("v-owned", "2024-01", [make_search_term("cats", views=5)])
        database.upsert_search_terms("v-external", "2024-01", [make_search_term("dogs", views=7)])

        self.assertEqual(database.get_video_search_terms("v-external"), [])
        self.assertNotEqual(database.get_video_search_terms("v-owned"), [])

        terms = database.get_search_terms()
        self.assertEqual([t["search_term"] for t in terms], ["cats"])

        videos = database.get_videos_by_search_term("dogs")
        self.assertEqual(videos, [])

    def test_comments_exclude_external_video(self) -> None:
        database.upsert_comment_author(make_comment_author("author-1", "Ann"))
        database.upsert_comment(make_comment("c-owned", "v-owned", "author-1"))
        database.upsert_comment(make_comment("c-external", "v-external", "author-1"))

        items, total = database.get_comments()
        self.assertEqual(total, 1)
        self.assertEqual([c["id"] for c in items], ["c-owned"])
