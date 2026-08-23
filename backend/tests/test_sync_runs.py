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

    def _seed(
        self,
        started_at: str,
        batch_id: str = "batch-1",
        sync_type: str = "videos",
        rows_fetched: int = 0,
        rows_written: int = 0,
        rows_deleted: int = 0,
    ) -> int:
        """Insert one running stage row with explicit batch, start time, and counters."""
        with connection.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs (batch_id, sync_type, scope, year, status, started_at,
                                       rows_fetched, rows_written, rows_deleted)
                VALUES (?, ?, 'incremental', NULL, 'running', ?, ?, ?, ?)
                """,
                (batch_id, sync_type, started_at, rows_fetched, rows_written, rows_deleted),
            )
            assert cursor.lastrowid is not None
            return cursor.lastrowid


class GroupingTest(SyncRunsTestCase):
    def test_stages_sharing_a_batch_collapse_into_one_group(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "playlists")
        self._seed("2024-05-01T10:01:00+00:00", "batch-a", "videos")
        self._seed("2024-05-01T10:02:00+00:00", "batch-a", "fx_rates")

        items, total = database.get_sync_runs(1, 25)

        self.assertEqual(total, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["batch_id"], "batch-a")
        self.assertEqual(items[0]["run_count"], 3)
        self.assertEqual(len(items[0]["runs"]), 3)

    def test_two_batches_on_the_same_date_stay_separate(self) -> None:
        self._seed("2024-05-01T09:00:00+00:00", "batch-a", "videos")
        self._seed("2024-05-01T18:00:00+00:00", "batch-b", "videos")

        items, total = database.get_sync_runs(1, 25)

        self.assertEqual(total, 2)
        self.assertEqual([g["batch_id"] for g in items], ["batch-b", "batch-a"])

    def test_group_start_time_is_the_earliest_stage_start(self) -> None:
        self._seed("2024-05-01T10:05:00+00:00", "batch-a", "videos")
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "playlists")
        self._seed("2024-05-01T10:09:00+00:00", "batch-a", "fx_rates")

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual(items[0]["started_at"], "2024-05-01T10:00:00+00:00")

    def test_a_batch_spanning_midnight_remains_one_group_keyed_to_its_earliest_start(self) -> None:
        self._seed("2024-05-01T23:50:00+00:00", "batch-a", "videos")
        self._seed("2024-05-02T00:10:00+00:00", "batch-a", "comments")

        items, total = database.get_sync_runs(1, 25)

        self.assertEqual(total, 1)
        self.assertEqual(items[0]["run_count"], 2)
        self.assertEqual(items[0]["started_at"], "2024-05-01T23:50:00+00:00")

    def test_batches_are_ordered_by_earliest_start_not_latest(self) -> None:
        self._seed("2024-05-01T08:00:00+00:00", "batch-early", "videos")
        self._seed("2024-05-01T23:00:00+00:00", "batch-early", "fx_rates")
        self._seed("2024-05-01T09:00:00+00:00", "batch-later", "videos")

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual([g["batch_id"] for g in items], ["batch-later", "batch-early"])

    def test_equal_earliest_timestamps_fall_back_to_descending_batch_id(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "videos")
        self._seed("2024-05-01T10:00:00+00:00", "batch-b", "videos")
        self._seed("2024-05-01T10:00:00+00:00", "batch-c", "videos")

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual([g["batch_id"] for g in items], ["batch-c", "batch-b", "batch-a"])

    def test_children_are_newest_first_within_a_group(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "playlists")
        self._seed("2024-05-01T10:01:00+00:00", "batch-a", "videos")
        self._seed("2024-05-01T10:02:00+00:00", "batch-a", "comments")

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual(
            [r["sync_type"] for r in items[0]["runs"]], ["comments", "videos", "playlists"])

    def test_children_with_equal_timestamps_use_the_descending_id_tie_breaker(self) -> None:
        ids = [self._seed("2024-05-01T10:00:00+00:00", "batch-a") for _ in range(4)]

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual([r["id"] for r in items[0]["runs"]], sorted(ids, reverse=True))


class RollupTest(SyncRunsTestCase):
    def test_counters_are_summed_from_the_batch_children(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "videos", 10, 5, 1)
        self._seed("2024-05-01T10:01:00+00:00", "batch-a", "comments", 7, 3, 0)
        self._seed("2024-05-01T10:02:00+00:00", "batch-a", "pruning", 0, 0, 4)

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual(items[0]["rows_fetched"], 17)
        self.assertEqual(items[0]["rows_written"], 8)
        self.assertEqual(items[0]["rows_deleted"], 5)

    def test_rollups_equal_the_sum_of_the_returned_children(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "videos", 10, 5, 1)
        self._seed("2024-05-01T10:01:00+00:00", "batch-a", "comments", 7, 3, 2)

        group = database.get_sync_runs(1, 25)[0][0]

        for key in ("rows_fetched", "rows_written", "rows_deleted"):
            self.assertEqual(group[key], sum(r[key] for r in group["runs"]))

    def test_a_failed_stage_contributes_its_partial_counters(self) -> None:
        run_id = self._seed("2024-05-01T10:00:00+00:00", "batch-a", "videos")
        self._seed("2024-05-01T10:01:00+00:00", "batch-a", "comments", 4, 2, 0)
        database.fail_sync_run(run_id, "quota exceeded", 3, 1, 0)

        items, _ = database.get_sync_runs(1, 25)

        self.assertEqual(items[0]["rows_fetched"], 7)
        self.assertEqual(items[0]["rows_written"], 3)

    def test_counters_do_not_leak_between_batches(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "videos", 10, 5, 1)
        self._seed("2024-05-02T10:00:00+00:00", "batch-b", "videos", 100, 50, 10)

        items, _ = database.get_sync_runs(1, 25)

        by_id = {g["batch_id"]: g for g in items}
        self.assertEqual(by_id["batch-a"]["rows_fetched"], 10)
        self.assertEqual(by_id["batch-b"]["rows_fetched"], 100)


class BatchPaginationTest(SyncRunsTestCase):
    def _seed_batches(self, count: int, stages_each: int = 1) -> None:
        for i in range(count):
            for stage in range(stages_each):
                self._seed(f"2024-05-{i + 1:02d}T{stage:02d}:00:00+00:00", f"batch-{i:02d}")

    def test_empty_history_returns_no_groups_and_a_zero_total(self) -> None:
        items, total = database.get_sync_runs(1, 25)

        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_total_counts_distinct_batches_not_stage_rows(self) -> None:
        self._seed_batches(3, stages_each=7)

        _, total = database.get_sync_runs(1, 25)

        self.assertEqual(total, 3)

    def test_page_size_limits_batches_not_stage_rows(self) -> None:
        self._seed_batches(4, stages_each=5)

        items, total = database.get_sync_runs(1, 2)

        self.assertEqual(total, 4)
        self.assertEqual(len(items), 2)
        self.assertEqual(sum(len(g["runs"]) for g in items), 10)

    def test_second_page_continues_without_overlapping_batches(self) -> None:
        self._seed_batches(30)

        first, _ = database.get_sync_runs(1, 25)
        second, total = database.get_sync_runs(2, 25)

        self.assertEqual(total, 30)
        self.assertEqual(len(first), 25)
        self.assertEqual(len(second), 5)
        self.assertFalse({g["batch_id"] for g in first} & {g["batch_id"] for g in second})

    def test_a_multi_stage_batch_is_never_split_across_pages(self) -> None:
        self._seed_batches(4, stages_each=7)

        first, _ = database.get_sync_runs(1, 2)
        second, _ = database.get_sync_runs(2, 2)

        for group in first + second:
            self.assertEqual(group["run_count"], 7)
            self.assertEqual(len(group["runs"]), 7)

    def test_page_beyond_the_end_is_empty_but_still_reports_the_total(self) -> None:
        self._seed_batches(3)

        items, total = database.get_sync_runs(4, 25)

        self.assertEqual(items, [])
        self.assertEqual(total, 3)


class MarkIncompleteTest(SyncRunsTestCase):
    def _status(self, run_id: int) -> str:
        with connection.get_connection() as conn:
            row = conn.execute("SELECT status FROM sync_runs WHERE id = ?", (run_id,)).fetchone()
        return str(row["status"])

    def test_a_stranded_running_row_becomes_incomplete(self) -> None:
        run_id = self._seed("2024-05-01T10:00:00+00:00")

        changed = database.mark_incomplete_sync_runs()

        self.assertEqual(changed, 1)
        self.assertEqual(self._status(run_id), "incomplete")

    def test_an_incomplete_row_keeps_its_null_completion_time(self) -> None:
        run_id = self._seed("2024-05-01T10:00:00+00:00")

        database.mark_incomplete_sync_runs()

        with connection.get_connection() as conn:
            row = conn.execute(
                "SELECT completed_at FROM sync_runs WHERE id = ?", (run_id,)).fetchone()
        self.assertIsNone(row["completed_at"])

    def test_terminal_rows_are_untouched(self) -> None:
        succeeded = self._seed("2024-05-01T10:00:00+00:00")
        failed = self._seed("2024-05-01T10:01:00+00:00")
        database.complete_sync_run(succeeded, 1, 1, 0)
        database.fail_sync_run(failed, "boom", 0, 0, 0)

        changed = database.mark_incomplete_sync_runs()

        self.assertEqual(changed, 0)
        self.assertEqual(self._status(succeeded), "success")
        self.assertEqual(self._status(failed), "failed")

    def test_an_already_incomplete_row_is_not_swept_again(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00")
        database.mark_incomplete_sync_runs()

        self.assertEqual(database.mark_incomplete_sync_runs(), 0)

    def test_every_stranded_row_across_batches_is_swept(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        self._seed("2024-05-01T10:01:00+00:00", "batch-a")
        self._seed("2024-05-02T10:00:00+00:00", "batch-b")

        self.assertEqual(database.mark_incomplete_sync_runs(), 3)

    def test_an_empty_history_sweeps_nothing(self) -> None:
        self.assertEqual(database.mark_incomplete_sync_runs(), 0)


class BatchStatusTest(SyncRunsTestCase):
    def _status_of_only_batch(self) -> str:
        items, _ = database.get_sync_runs(1, 25)
        return str(items[0]["status"])

    def test_all_successful_stages_report_success(self) -> None:
        for offset in range(3):
            run_id = self._seed(f"2024-05-01T10:0{offset}:00+00:00", "batch-a")
            database.complete_sync_run(run_id, 1, 1, 0)

        self.assertEqual(self._status_of_only_batch(), "success")

    def test_an_in_flight_stage_reports_running(self) -> None:
        done = self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        database.complete_sync_run(done, 1, 1, 0)
        self._seed("2024-05-01T10:01:00+00:00", "batch-a")

        self.assertEqual(self._status_of_only_batch(), "running")

    def test_a_stranded_stage_reports_incomplete(self) -> None:
        done = self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        database.complete_sync_run(done, 1, 1, 0)
        self._seed("2024-05-01T10:01:00+00:00", "batch-a")
        database.mark_incomplete_sync_runs()

        self.assertEqual(self._status_of_only_batch(), "incomplete")

    def test_a_failed_stage_outranks_an_incomplete_one(self) -> None:
        failed = self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        self._seed("2024-05-01T10:01:00+00:00", "batch-a")
        database.mark_incomplete_sync_runs()
        database.fail_sync_run(failed, "boom", 0, 0, 0)

        self.assertEqual(self._status_of_only_batch(), "failed")

    def test_incomplete_outranks_running(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        database.mark_incomplete_sync_runs()
        self._seed("2024-05-01T10:01:00+00:00", "batch-a")

        self.assertEqual(self._status_of_only_batch(), "incomplete")

    def test_status_is_scoped_to_its_own_batch(self) -> None:
        healthy = self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        database.complete_sync_run(healthy, 1, 1, 0)
        broken = self._seed("2024-05-02T10:00:00+00:00", "batch-b")
        database.fail_sync_run(broken, "boom", 0, 0, 0)

        items, _ = database.get_sync_runs(1, 25)

        by_id = {g["batch_id"]: g["status"] for g in items}
        self.assertEqual(by_id, {"batch-a": "success", "batch-b": "failed"})


class ChildContentTest(SyncRunsTestCase):
    def test_children_keep_every_stored_field(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a", "videos")

        child = database.get_sync_runs(1, 25)[0][0]["runs"][0]

        self.assertEqual(set(child), {
            "id", "batch_id", "sync_type", "scope", "year", "status", "started_at",
            "completed_at", "rows_fetched", "rows_written", "rows_deleted", "error_message",
        })

    def test_a_running_child_keeps_a_null_completion_time(self) -> None:
        self._seed("2024-05-01T10:00:00+00:00", "batch-a")

        child = database.get_sync_runs(1, 25)[0][0]["runs"][0]

        self.assertEqual(child["status"], "running")
        self.assertIsNone(child["completed_at"])

    def test_a_completed_child_reports_its_counters_and_completion(self) -> None:
        run_id = self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        database.complete_sync_run(run_id, 10, 7, 2)

        child = database.get_sync_runs(1, 25)[0][0]["runs"][0]

        self.assertEqual(child["status"], "success")
        self.assertIsNotNone(child["completed_at"])
        self.assertEqual(
            (child["rows_fetched"], child["rows_written"], child["rows_deleted"]), (10, 7, 2))

    def test_a_failed_child_still_carries_its_stored_error(self) -> None:
        run_id = self._seed("2024-05-01T10:00:00+00:00", "batch-a")
        database.fail_sync_run(run_id, "quota exceeded", 3, 0, 0)

        child = database.get_sync_runs(1, 25)[0][0]["runs"][0]

        self.assertEqual(child["status"], "failed")
        self.assertEqual(child["error_message"], "quota exceeded")


if __name__ == "__main__":
    unittest.main()
