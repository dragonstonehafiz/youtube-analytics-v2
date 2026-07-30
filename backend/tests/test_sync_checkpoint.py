from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import database
from database import connection
from sync.plans import FULL_SYNC_TYPES


class CheckpointTestCase(unittest.TestCase):
    """Runs against a throwaway SQLite file so the app database is never touched."""

    def setUp(self) -> None:
        # get_connection() commits but never closes, so Windows still holds the WAL file
        # open at teardown; leaving the temp file behind is harmless.
        tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmpdir.cleanup)

        patcher = mock.patch.object(connection, "_DB_PATH", Path(tmpdir.name) / "test.db")
        self.addCleanup(patcher.stop)
        patcher.start()

        database.init_db()

    def _succeed(self, batch_id: str, sync_type: str) -> None:
        run_id = database.create_sync_run(batch_id, sync_type, "incremental", None)
        database.complete_sync_run(run_id, 0, 0, 0)

    def _fail(self, batch_id: str, sync_type: str) -> None:
        run_id = database.create_sync_run(batch_id, sync_type, "incremental", None)
        database.fail_sync_run(run_id, "boom", 0, 0, 0)

    def _start(self, batch_id: str, sync_type: str) -> None:
        database.create_sync_run(batch_id, sync_type, "incremental", None)

    def _complete_batch(self, batch_id: str) -> None:
        for sync_type in FULL_SYNC_TYPES:
            self._succeed(batch_id, sync_type)

    @property
    def checkpoint(self) -> str | None:
        return database.get_last_successful_batch_completed_at(FULL_SYNC_TYPES)


class QualifyingBatchTest(CheckpointTestCase):
    def test_no_history_has_no_checkpoint(self) -> None:
        self.assertIsNone(self.checkpoint)

    def test_complete_successful_batch_qualifies(self) -> None:
        self._complete_batch("batch-1")
        self.assertIsNotNone(self.checkpoint)

    def test_partial_manual_batch_does_not_qualify(self) -> None:
        self._succeed("batch-1", "video_analytics")
        self._succeed("batch-1", "video_traffic_sources")
        self.assertIsNone(self.checkpoint)

    def test_batch_without_fx_rates_does_not_qualify(self) -> None:
        for sync_type in FULL_SYNC_TYPES:
            if sync_type != "fx_rates":
                self._succeed("batch-1", sync_type)
        self.assertIsNone(self.checkpoint)

    def test_batch_with_failed_fx_rates_does_not_qualify(self) -> None:
        for sync_type in FULL_SYNC_TYPES:
            if sync_type == "fx_rates":
                self._fail("batch-1", sync_type)
            else:
                self._succeed("batch-1", sync_type)
        self.assertIsNone(self.checkpoint)

    def test_batch_with_a_still_running_stage_does_not_qualify(self) -> None:
        for sync_type in FULL_SYNC_TYPES:
            if sync_type == "video_analytics":
                self._start("batch-1", sync_type)
            else:
                self._succeed("batch-1", sync_type)
        self.assertIsNone(self.checkpoint)

    def test_single_stage_plan_does_not_qualify(self) -> None:
        self._succeed("batch-1", "fx_rates")
        self.assertIsNone(self.checkpoint)


class CheckpointSelectionTest(CheckpointTestCase):
    def test_newer_partial_batch_does_not_hide_older_complete_batch(self) -> None:
        self._complete_batch("batch-1")
        complete_checkpoint = self.checkpoint

        self._succeed("batch-2", "fx_rates")

        self.assertEqual(self.checkpoint, complete_checkpoint)

    def test_newer_complete_batch_replaces_the_older_one(self) -> None:
        self._complete_batch("batch-1")
        first = self.checkpoint

        self._complete_batch("batch-2")

        self.assertIsNotNone(self.checkpoint)
        assert first is not None and self.checkpoint is not None
        self.assertGreaterEqual(self.checkpoint, first)

    def test_failed_batch_does_not_hide_older_complete_batch(self) -> None:
        self._complete_batch("batch-1")
        complete_checkpoint = self.checkpoint

        for sync_type in FULL_SYNC_TYPES:
            self._fail("batch-2", sync_type)

        self.assertEqual(self.checkpoint, complete_checkpoint)


class NoPersistedCheckpointStateTest(CheckpointTestCase):
    def test_schema_has_no_sync_state_table(self) -> None:
        with connection.get_connection() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        self.assertIn("sync_runs", tables)
        self.assertNotIn("sync_state", tables)

    def test_sync_runs_has_no_last_synced_at_column(self) -> None:
        with connection.get_connection() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(sync_runs)")}
        self.assertNotIn("last_synced_at", columns)

    def test_database_exposes_no_checkpoint_write_helper(self) -> None:
        for name in dir(database):
            self.assertNotIn("last_synced", name)
            self.assertNotIn("sync_state", name)


if __name__ == "__main__":
    unittest.main()
