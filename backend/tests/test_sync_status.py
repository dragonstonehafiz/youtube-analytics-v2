from __future__ import annotations

import unittest

from sync import status


class SyncStatusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        status.reset_sync_status()
        self.addCleanup(status.reset_sync_status)


class InitialStateTest(SyncStatusTestCase):
    def test_initial_state_is_idle_with_no_message(self) -> None:
        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": ""})


class ReservationTest(SyncStatusTestCase):
    def test_reservation_sets_running_state_and_message(self) -> None:
        self.assertTrue(status.try_begin_sync("Starting sync..."))

        self.assertEqual(
            status.get_sync_status(), {"state": "running", "message": "Starting sync..."}
        )

    def test_second_reservation_while_running_fails_and_preserves_state(self) -> None:
        status.try_begin_sync("first")

        self.assertFalse(status.try_begin_sync("second"))
        self.assertEqual(status.get_sync_status(), {"state": "running", "message": "first"})

    def test_reservation_after_a_terminal_result_replaces_it(self) -> None:
        status.try_begin_sync("first run")
        status.complete_sync("Sync complete")

        self.assertTrue(status.try_begin_sync("second run"))
        self.assertEqual(status.get_sync_status(), {"state": "running", "message": "second run"})


class ProgressTest(SyncStatusTestCase):
    def test_progress_updates_the_message_while_running(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.update_sync_progress("Syncing videos...")

        self.assertEqual(status.get_sync_status()["message"], "Syncing videos...")

    def test_progress_is_a_no_op_while_idle(self) -> None:
        status.update_sync_progress("Syncing videos...")

        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": ""})

    def test_progress_is_a_no_op_after_a_terminal_result(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.complete_sync("Sync complete")

        status.update_sync_progress("Syncing videos...")

        self.assertEqual(status.get_sync_status()["message"], "Sync complete")


class TerminalTransitionTest(SyncStatusTestCase):
    def test_complete_sync_sets_success_state_and_message(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.complete_sync("Sync complete")

        self.assertEqual(
            status.get_sync_status(), {"state": "success", "message": "Sync complete"}
        )

    def test_fail_sync_sets_failed_state_and_message(self) -> None:
        status.try_begin_sync("Starting sync...")

        status.fail_sync("Sync failed while syncing videos")

        self.assertEqual(
            status.get_sync_status(),
            {"state": "failed", "message": "Sync failed while syncing videos"},
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
            status.get_sync_status(), {"state": "stopping", "message": "Stopping sync..."}
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

        status.update_sync_progress("Syncing videos...")

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
            status.get_sync_status(), {"state": "cancelled", "message": "Sync stopped"}
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
            status.get_sync_status(), {"state": "cancelled", "message": "Sync stopped"}
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

        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": ""})


if __name__ == "__main__":
    unittest.main()
