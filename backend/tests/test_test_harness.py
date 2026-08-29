from __future__ import annotations

import unittest
from unittest import mock

import youtube.analytics_api as analytics_api
import youtube.data_api as data_api
from database import connection
from tests.conftest import ExternalAccessError
from tests.support import (
    APPLICATION_DB_PATH,
    FIXED_NOW,
    IsolatedDatabaseTestCase,
    SeededDatabaseTestCase,
)

EXPECTED_TABLES = {
    "videos", "video_analytics", "video_traffic_sources", "playlists", "playlist_items",
    "comment_authors", "comments", "fx_rates", "sync_runs",
}


class PathGuardTest(unittest.TestCase):
    def test_refuses_to_initialize_the_application_database_path(self) -> None:
        # Point APPLICATION_DB_PATH at exactly the path setUp() will resolve to
        # (tmpdir/"test.db"), so the guard sees a genuine collision rather than
        # proving nothing by comparing a patched path to itself after the fact.
        with mock.patch("tests.support.tempfile.TemporaryDirectory") as mock_tmpdir:
            mock_tmpdir.return_value.name = str(APPLICATION_DB_PATH.parent)
            colliding_path = APPLICATION_DB_PATH.parent / "test.db"
            with mock.patch("tests.support.APPLICATION_DB_PATH", colliding_path):
                case = IsolatedDatabaseTestCase()
                with self.assertRaises(AssertionError):
                    case.setUp()


class OAuthGuardTest(unittest.TestCase):
    """Both API client builders import get_credentials directly (`from .auth import
    get_credentials`), binding their own module-level reference at import time. Patching
    youtube.auth.get_credentials alone would leave these aliases pointing at the real
    function, so each client builder must be proven to raise independently."""

    def test_data_api_client_builder_raises(self) -> None:
        with self.assertRaises(ExternalAccessError):
            data_api._data_client()

    def test_analytics_api_client_builder_raises(self) -> None:
        with self.assertRaises(ExternalAccessError):
            analytics_api._analytics_client()


class SchemaInitializationTest(IsolatedDatabaseTestCase):
    def test_every_current_table_is_created(self) -> None:
        with connection.get_connection() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        self.assertEqual(tables - {"sqlite_sequence"}, EXPECTED_TABLES)

    def test_each_test_starts_with_an_empty_database(self) -> None:
        with connection.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        self.assertEqual(count, 0)

    def test_isolated_path_is_not_the_application_path(self) -> None:
        self.assertNotEqual(connection._DB_PATH.resolve(), APPLICATION_DB_PATH.resolve())


class SeededDatasetTest(SeededDatabaseTestCase):
    def test_every_issue_required_table_is_populated(self) -> None:
        with connection.get_connection() as conn:
            counts = {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in EXPECTED_TABLES
            }
        for table, count in counts.items():
            with self.subTest(table=table):
                self.assertGreater(count, 0, f"{table} should be seeded")

    def test_fixed_ids_are_present(self) -> None:
        with connection.get_connection() as conn:
            video_ids = {r["id"] for r in conn.execute("SELECT id FROM videos")}
        self.assertEqual(video_ids, {"v-1", "v-2", "v-3", "v-4"})

    def test_generated_updated_at_timestamps_are_frozen(self) -> None:
        with connection.get_connection() as conn:
            video_stamps = {r["updated_at"] for r in conn.execute("SELECT updated_at FROM videos")}
            run_stamps = {r["started_at"] for r in conn.execute("SELECT started_at FROM sync_runs")}
        self.assertEqual(video_stamps, {FIXED_NOW})
        self.assertEqual(run_stamps, {FIXED_NOW})


if __name__ == "__main__":
    unittest.main()
