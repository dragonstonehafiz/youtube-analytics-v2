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


class ResetTest(SyncStatusTestCase):
    def test_reset_returns_to_idle_with_no_message(self) -> None:
        status.try_begin_sync("Starting sync...")
        status.complete_sync("Sync complete")

        status.reset_sync_status()

        self.assertEqual(status.get_sync_status(), {"state": "idle", "message": ""})


if __name__ == "__main__":
    unittest.main()
