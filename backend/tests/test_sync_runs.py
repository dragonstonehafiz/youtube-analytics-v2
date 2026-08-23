from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import database
from database import connection


class SyncRunsTestCase(unittest.TestCase):
    """Runs against a throwaway SQLite file so the app database is never touched."""

    def setUp(self) -> None:
        tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmpdir.cleanup)

        patcher = mock.patch.object(connection, "_DB_PATH", Path(tmpdir.name) / "test.db")
        self.addCleanup(patcher.stop)
        patcher.start()

        database.init_db()

    def _seed(self, started_at: str, sync_type: str = "videos") -> int:
        """Insert one running stage row with an explicit start time and return its ID."""
        with connection.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs (batch_id, sync_type, scope, year, status, started_at)
                VALUES ('batch-1', ?, 'incremental', NULL, 'running', ?)
                """,
                (sync_type, started_at),
            )
            assert cursor.lastrowid is not None
            return cursor.lastrowid


class PaginationTest(SyncRunsTestCase):
    def _seed_many(self, count: int) -> None:
        for i in range(count):
            self._seed(f"2024-05-{i + 1:02d}T00:00:00+00:00")

    def test_empty_history_returns_no_rows_and_a_zero_total(self) -> None:
        items, total = database.get_sync_runs(1, 25)

        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_first_page_returns_the_newest_rows(self) -> None:
        self._seed_many(30)

        items, total = database.get_sync_runs(1, 25)

        self.assertEqual(total, 30)
        self.assertEqual(len(items), 25)
        self.assertEqual(items[0]["started_at"], "2024-05-30T00:00:00+00:00")
        self.assertEqual(items[-1]["started_at"], "2024-05-06T00:00:00+00:00")

    def test_second_page_continues_without_overlap(self) -> None:
        self._seed_many(30)

        first, _ = database.get_sync_runs(1, 25)
        second, total = database.get_sync_runs(2, 25)

        self.assertEqual(total, 30)
        self.assertEqual(len(second), 5)
        self.assertEqual(second[0]["started_at"], "2024-05-05T00:00:00+00:00")
        self.assertFalse({r["id"] for r in first} & {r["id"] for r in second})

    def test_total_counts_every_row_not_just_the_page(self) -> None:
        self._seed_many(30)

        _, total = database.get_sync_runs(2, 10)

        self.assertEqual(total, 30)

    def test_page_beyond_the_end_is_empty_but_still_reports_the_total(self) -> None:
        self._seed_many(5)

        items, total = database.get_sync_runs(4, 25)

        self.assertEqual(items, [])
        self.assertEqual(total, 5)

    def test_equal_timestamps_are_ordered_by_descending_id_without_overlap(self) -> None:
        ids = [self._seed("2024-05-01T00:00:00+00:00") for _ in range(6)]

        first, _ = database.get_sync_runs(1, 3)
        second, _ = database.get_sync_runs(2, 3)

        self.assertEqual([r["id"] for r in first], sorted(ids, reverse=True)[:3])
        self.assertEqual([r["id"] for r in second], sorted(ids, reverse=True)[3:])


class RowContentTest(SyncRunsTestCase):
    def test_a_running_row_keeps_a_null_completion_time(self) -> None:
        self._seed("2024-05-01T00:00:00+00:00")

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual(items[0]["status"], "running")
        self.assertIsNone(items[0]["completed_at"])

    def test_completed_counters_are_returned(self) -> None:
        run_id = self._seed("2024-05-01T00:00:00+00:00")
        database.complete_sync_run(run_id, 10, 7, 2)

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual(items[0]["status"], "success")
        self.assertIsNotNone(items[0]["completed_at"])
        self.assertEqual(
            (items[0]["rows_fetched"], items[0]["rows_written"], items[0]["rows_deleted"]),
            (10, 7, 2),
        )

    def test_a_failed_row_stores_its_error_without_affecting_ordering(self) -> None:
        older = self._seed("2024-05-01T00:00:00+00:00")
        self._seed("2024-05-02T00:00:00+00:00")
        database.fail_sync_run(older, "quota exceeded", 3, 0, 0)

        items, total = database.get_sync_runs(1, 25)

        self.assertEqual(total, 2)
        self.assertEqual(items[0]["started_at"], "2024-05-02T00:00:00+00:00")
        self.assertEqual(items[1]["error_message"], "quota exceeded")


if __name__ == "__main__":
    unittest.main()
