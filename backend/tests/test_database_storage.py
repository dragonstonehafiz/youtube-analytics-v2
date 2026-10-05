from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest import mock

import apsw

from database import Video, connection, tables, writer
from database.reports import storage
from routes.synchronization import router as sync_router
from tests.support import IsolatedDatabaseTestCase, create_test_client, make_video

_ROW_PADDING = "x" * 2000


def _videos(count: int) -> list[Video]:
    return [make_video(f"v{index:04d}", description=_ROW_PADDING) for index in range(count)]


def _dbstat_bytes(name: str) -> int:
    conn = apsw.Connection(str(connection.database_path()), flags=apsw.SQLITE_OPEN_READONLY)
    try:
        rows = conn.execute("SELECT pgsize FROM dbstat WHERE name = ? AND aggregate = TRUE", (name,)).fetchall()
        return cast(int, rows[0][0])
    finally:
        conn.close()


class DatabaseStorageTest(IsolatedDatabaseTestCase):
    def _tables(self, result: dict) -> dict[str, dict]:
        return {table["name"]: table for table in result["tables"]}

    def _assert_reconciles(self, result: dict) -> None:
        attributed = sum(table["size_bytes"] for table in result["tables"])
        self.assertEqual(attributed + result["other_bytes"], result["total_bytes"])

    def test_every_application_table_is_listed_with_zero_rows_when_empty(self) -> None:
        result = storage.database_storage()

        self.assertEqual([table["name"] for table in result["tables"]], list(tables.TABLES.values()))
        self.assertEqual(len(result["tables"]), 12)
        self.assertTrue(all(table["row_count"] == 0 for table in result["tables"]))
        self.assertGreater(result["total_bytes"], 0)
        self._assert_reconciles(result)

    def test_row_counts_are_exact(self) -> None:
        writer.write_many(_videos(7))

        result = self._tables(storage.database_storage())

        self.assertEqual(result["videos"]["row_count"], 7)
        self.assertEqual(result["comments"]["row_count"], 0)

    def test_index_bytes_are_attributed_to_their_table(self) -> None:
        writer.write_many(_videos(200))

        result = self._tables(storage.database_storage())

        # videos' TEXT primary key lives in an automatic index alongside the table b-tree.
        table_only = _dbstat_bytes("videos")
        index_only = _dbstat_bytes("sqlite_autoindex_videos_1")
        self.assertEqual(result["videos"]["size_bytes"], table_only + index_only)

    def test_free_pages_count_as_other(self) -> None:
        writer.write_many(_videos(200))
        before = storage.database_storage()
        writer.delete(Video, where=[("id", "LIKE", "v%")])

        after = storage.database_storage()

        self.assertEqual(self._tables(after)["videos"]["row_count"], 0)
        self.assertGreater(after["other_bytes"], before["other_bytes"])
        self._assert_reconciles(after)

    def test_uncheckpointed_wal_writes_are_measured_consistently(self) -> None:
        conn = connection.get_connection()
        self.addCleanup(conn.close)
        conn.execute("PRAGMA wal_autocheckpoint = 0")
        conn.execute("BEGIN")
        writer.write_many(_videos(300), conn=conn)
        conn.commit()

        result = storage.database_storage()

        self.assertEqual(self._tables(result)["videos"]["row_count"], 300)
        self.assertGreater(result["total_bytes"], connection.database_path().stat().st_size)
        self._assert_reconciles(result)

    def test_missing_database_is_reported_unavailable(self) -> None:
        missing = Path(connection.database_path()).with_name("missing.db")
        with mock.patch.object(connection, "_DB_PATH", missing):
            with self.assertRaises(storage.StorageUnavailable):
                storage.database_storage()


class DatabaseStorageRouteTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(sync_router)

    def test_returns_storage_and_row_counts(self) -> None:
        writer.write_many(_videos(3))

        response = self.client.get("/sync/database")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"total_bytes", "other_bytes", "tables"})
        videos = next(table for table in body["tables"] if table["name"] == "videos")
        self.assertEqual(videos["row_count"], 3)
        self.assertGreater(videos["size_bytes"], 0)

    def test_failed_measurement_returns_503_without_internal_details(self) -> None:
        missing = Path(connection.database_path()).with_name("missing.db")
        with mock.patch.object(connection, "_DB_PATH", missing):
            response = self.client.get("/sync/database")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Database statistics are unavailable"})
