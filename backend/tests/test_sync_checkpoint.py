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
        return database.get_last_successful_run_completed_at()


class QualifyingRunTest(CheckpointTestCase):
    def test_no_history_has_no_checkpoint(self) -> None:
        self.assertIsNone(self.checkpoint)

    def test_complete_successful_batch_qualifies(self) -> None:
        self._complete_batch("batch-1")
        self.assertIsNotNone(self.checkpoint)

    def test_single_successful_stage_qualifies(self) -> None:
        """Any one succeeded stage is enough — this is the whole point of the check."""
        self._succeed("batch-1", "fx_rates")
        self.assertIsNotNone(self.checkpoint)

    def test_partial_manual_batch_qualifies(self) -> None:
        self._succeed("batch-1", "video_analytics")
        self._succeed("batch-1", "video_traffic_sources")
        self.assertIsNotNone(self.checkpoint)

    def test_batch_missing_fx_rates_still_qualifies(self) -> None:
        for sync_type in FULL_SYNC_TYPES:
            if sync_type != "fx_rates":
                self._succeed("batch-1", sync_type)
        self.assertIsNotNone(self.checkpoint)

    def test_failed_stage_alongside_a_success_does_not_disqualify_the_batch(self) -> None:
        self._succeed("batch-1", "videos")
        self._fail("batch-1", "fx_rates")
        self.assertIsNotNone(self.checkpoint)

    def test_only_failed_runs_do_not_qualify(self) -> None:
        for sync_type in FULL_SYNC_TYPES:
            self._fail("batch-1", sync_type)
        self.assertIsNone(self.checkpoint)

    def test_only_still_running_runs_do_not_qualify(self) -> None:
        for sync_type in FULL_SYNC_TYPES:
            self._start("batch-1", sync_type)
        self.assertIsNone(self.checkpoint)


class CheckpointSelectionTest(CheckpointTestCase):
    def test_newest_success_wins_regardless_of_batch(self) -> None:
        self._complete_batch("batch-1")
        first = self.checkpoint

        self._succeed("batch-2", "fx_rates")

        self.assertIsNotNone(self.checkpoint)
        assert first is not None and self.checkpoint is not None
        self.assertGreaterEqual(self.checkpoint, first)

    def test_later_failure_does_not_hide_an_earlier_success(self) -> None:
        self._succeed("batch-1", "videos")
        success_checkpoint = self.checkpoint

        for sync_type in FULL_SYNC_TYPES:
            self._fail("batch-2", sync_type)

        self.assertEqual(self.checkpoint, success_checkpoint)

    def test_later_still_running_run_does_not_hide_an_earlier_success(self) -> None:
        self._succeed("batch-1", "videos")
        success_checkpoint = self.checkpoint

        self._start("batch-2", "playlists")

        self.assertEqual(self.checkpoint, success_checkpoint)


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
