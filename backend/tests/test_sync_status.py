from __future__ import annotations

import unittest

from sync import status


class SyncStatusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        status.reset_sync_status()
        self.addCleanup(status.reset_sync_status)


class InitialStateTest(SyncStatusTestCase):
    def test_initial_state_is_idle_with_no_message(self) -> None:
        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": "", "stages": []})


class ReservationTest(SyncStatusTestCase):
    def test_reservation_sets_running_state_and_message(self) -> None:
        self.assertTrue(status.try_begin_sync("Starting sync..."))

        self.assertEqual(
            status.get_sync_status(),
            {"state": "running", "message": "Starting sync...", "stages": []},
        )

    def test_second_reservation_while_running_fails_and_preserves_state(self) -> None:
        status.try_begin_sync("first")

        self.assertFalse(status.try_begin_sync("second"))
        self.assertEqual(
            status.get_sync_status(), {"state": "running", "message": "first", "stages": []}
        )

    def test_reservation_after_a_terminal_result_replaces_it(self) -> None:
        status.try_begin_sync("first run")
        status.complete_sync("Sync complete")

        self.assertTrue(status.try_begin_sync("second run"))
        self.assertEqual(
            status.get_sync_status(), {"state": "running", "message": "second run", "stages": []}
        )


class ProgressTest(SyncStatusTestCase):
    def test_progress_updates_the_message_while_running(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.update_sync_progress("videos", "Syncing videos...")

        self.assertEqual(status.get_sync_status()["message"], "Syncing videos...")

    def test_progress_is_a_no_op_while_idle(self) -> None:
        status.update_sync_progress("videos", "Syncing videos...")

        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": "", "stages": []})

    def test_progress_is_a_no_op_after_a_terminal_result(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.complete_sync("Sync complete")

        status.update_sync_progress("videos", "Syncing videos...")

        self.assertEqual(status.get_sync_status()["message"], "Sync complete")

    def test_two_active_stages_are_both_visible_in_the_combined_message(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.update_sync_progress("video_analytics", "Syncing video analytics (1/5)...")
        status.update_sync_progress("search_insights", "Syncing search insights (1/5)...")

        message = status.get_sync_status()["message"]
        self.assertIn("Syncing video analytics (1/5)...", message)
        self.assertIn("Syncing search insights (1/5)...", message)

    def test_two_active_stages_appear_as_separate_stage_entries(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.update_sync_progress("video_analytics", "Syncing video analytics (1/5)...")
        status.update_sync_progress("search_insights", "Syncing search insights (1/5)...")

        self.assertEqual(
            status.get_sync_status()["stages"],
            [
                {"key": "video_analytics", "message": "Syncing video analytics (1/5)..."},
                {"key": "search_insights", "message": "Syncing search insights (1/5)..."},
            ],
        )

    def test_a_failed_stage_appears_alongside_a_still_active_stage(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.update_sync_progress("search_insights", "Syncing search insights (1/5)...")

        status.fail_stage("video_analytics", "syncing video analytics")

        self.assertEqual(
            status.get_sync_status()["stages"],
            [
                {"key": "search_insights", "message": "Syncing search insights (1/5)..."},
                {"key": "video_analytics", "message": "syncing video analytics failed"},
            ],
        )

    def test_a_second_update_to_the_same_stage_replaces_its_own_entry_only(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.update_sync_progress("video_analytics", "Syncing video analytics (1/5)...")
        status.update_sync_progress("search_insights", "Syncing search insights (1/5)...")
        status.update_sync_progress("video_analytics", "Syncing video analytics (2/5)...")

        message = status.get_sync_status()["message"]
        self.assertNotIn("Syncing video analytics (1/5)...", message)
        self.assertIn("Syncing video analytics (2/5)...", message)
        self.assertIn("Syncing search insights (1/5)...", message)

    def test_end_stage_removes_its_entry_but_keeps_the_others(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.update_sync_progress("video_analytics", "Syncing video analytics (1/5)...")
        status.update_sync_progress("search_insights", "Syncing search insights (1/5)...")

        status.end_stage("video_analytics")

        message = status.get_sync_status()["message"]
        self.assertNotIn("video analytics", message)
        self.assertIn("Syncing search insights (1/5)...", message)

    def test_fail_stage_keeps_a_fixed_label_visible_while_other_work_continues(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.update_sync_progress("video_analytics", "Syncing video analytics (1/5)...")
        status.update_sync_progress("search_insights", "Syncing search insights (1/5)...")

        status.fail_stage("video_analytics", "syncing video analytics")

        message = status.get_sync_status()["message"]
        self.assertIn("syncing video analytics failed", message)
        self.assertIn("Syncing search insights (1/5)...", message)

    def test_multiple_failed_stages_are_all_named(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.fail_stage("video_analytics", "syncing video analytics")
        status.fail_stage("search_insights", "syncing search insights")

        message = status.get_sync_status()["message"]
        self.assertIn("syncing video analytics failed", message)
        self.assertIn("syncing search insights failed", message)

    def test_end_stage_is_a_no_op_on_the_public_message_while_idle(self) -> None:
        status.end_stage("video_analytics")  # must not raise

        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": "", "stages": []})

    def test_reservation_clears_stage_progress_and_failures_from_a_previous_run(self) -> None:
        status.try_begin_sync("first run")
        status.update_sync_progress("video_analytics", "Syncing video analytics (1/5)...")
        status.fail_stage("search_insights", "syncing search insights")
        status.fail_sync("Sync failed while syncing search insights")

        status.try_begin_sync("second run")

        self.assertEqual(
            status.get_sync_status(), {"state": "running", "message": "second run", "stages": []}
        )


class TerminalTransitionTest(SyncStatusTestCase):
    def test_complete_sync_sets_success_state_and_message(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.complete_sync("Sync complete")

        self.assertEqual(
            status.get_sync_status(),
            {"state": "success", "message": "Sync complete", "stages": []},
        )

    def test_fail_sync_sets_failed_state_and_message(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.fail_sync("Sync failed while syncing videos")

        self.assertEqual(
            status.get_sync_status(),
            {"state": "failed", "message": "Sync failed while syncing videos", "stages": []},
        )

    def test_terminal_result_is_retained_across_repeated_reads(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.fail_sync("Sync failed while syncing videos")

        self.assertEqual(status.get_sync_status()["state"], "failed")
        self.assertEqual(status.get_sync_status()["state"], "failed")


class StopRequestTest(SyncStatusTestCase):
    def test_request_stop_while_running_transitions_to_stopping(self) -> None:
        status.try_begin_sync("Starting sync...")

        self.assertTrue(status.request_stop())

        self.assertEqual(
            status.get_sync_status(),
            {"state": "stopping", "message": "Stopping sync...", "stages": []},
        )

    def test_repeated_stop_requests_are_idempotent(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.request_stop()

        self.assertTrue(status.request_stop())
        self.assertEqual(status.get_sync_status()["state"], "stopping")

    def test_stop_request_while_idle_reports_no_active_sync(self) -> None:
        self.assertFalse(status.request_stop())
        self.assertEqual(status.get_sync_status()["state"], "idle")

    def test_stop_request_after_a_terminal_result_reports_no_active_sync(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.complete_sync("Sync complete")

        self.assertFalse(status.request_stop())
        self.assertEqual(status.get_sync_status()["state"], "success")

    def test_progress_updates_do_not_overwrite_the_stopping_message(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.request_stop()

        status.update_sync_progress("videos", "Syncing videos...")

        self.assertEqual(status.get_sync_status()["message"], "Stopping sync...")

    def test_reservation_is_rejected_while_stopping(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.request_stop()

        self.assertFalse(status.try_begin_sync("second run"))
        self.assertEqual(status.get_sync_status()["state"], "stopping")


class CheckpointTest(SyncStatusTestCase):
    def test_raise_if_stopping_is_a_no_op_while_running(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.raise_if_stopping()  # must not raise

    def test_raise_if_stopping_raises_once_stopping_is_requested(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.request_stop()

        with self.assertRaises(status.SyncCancelled):
            status.raise_if_stopping()

    def test_raise_if_stopping_is_a_no_op_while_idle(self) -> None:
        status.raise_if_stopping()  # must not raise


class CancelSyncTest(SyncStatusTestCase):
    def test_cancel_sync_sets_cancelled_state_and_message(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.request_stop()

        status.cancel_sync("Sync stopped")

        self.assertEqual(
            status.get_sync_status(),
            {"state": "cancelled", "message": "Sync stopped", "stages": []},
        )

    def test_cancel_sync_does_not_overwrite_a_result_already_recorded(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.complete_sync("Sync complete")

        status.cancel_sync("Sync stopped")

        self.assertEqual(status.get_sync_status()["state"], "success")

    def test_complete_sync_settles_stopping_to_cancelled_rather_than_success(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.request_stop()

        status.complete_sync("Sync complete")

        self.assertEqual(
            status.get_sync_status(),
            {"state": "cancelled", "message": "Sync stopped", "stages": []},
        )

    def test_fail_sync_still_applies_while_stopping(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.request_stop()

        status.fail_sync("Sync failed while syncing videos")

        self.assertEqual(status.get_sync_status()["state"], "failed")


class ResetTest(SyncStatusTestCase):
    def test_reset_returns_to_idle_with_no_message(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.complete_sync("Sync complete")

        status.reset_sync_status()

        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": "", "stages": []})


if __name__ == "__main__":
    unittest.main()
