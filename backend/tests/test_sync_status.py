from __future__ import annotations

import unittest

from sync import status


class SyncStatusTestCase(unittest.TestCase):
    def setUp(self) -> None:
        status.reset_sync_status()
        self.addCleanup(status.reset_sync_status)


class PerStageStatusTest(SyncStatusTestCase):
    def test_reservation_seeds_selected_stages_in_order(self) -> None:
        self.assertTrue(status.try_begin_sync(["videos", "comments"]))
        self.assertEqual(status.get_sync_status(), {
            "active": True,
            "stop_requested": False,
            "stages": [
                {"key": "videos", "state": "pending", "message": ""},
                {"key": "comments", "state": "pending", "message": ""},
            ],
        })

    def test_only_one_active_reservation_is_allowed(self) -> None:
        self.assertTrue(status.try_begin_sync(["videos"]))
        self.assertFalse(status.try_begin_sync(["comments"]))
        self.assertEqual(status.get_sync_status()["stages"][0]["key"], "videos")

    def test_progress_success_failure_and_cancel_are_independent(self) -> None:
        status.try_begin_sync(["video_analytics", "search_insights", "comments"])
        status.update_sync_progress("video_analytics", "Syncing video analytics (1/5)...")
        status.update_sync_progress("search_insights", "Syncing search insights (1/5)...")
        status.fail_stage("video_analytics", "syncing video analytics")
        status.complete_stage("search_insights")
        status.cancel_stage("comments")
        self.assertEqual(status.get_sync_status()["stages"], [
            {"key": "video_analytics", "state": "failed", "message": "syncing video analytics failed"},
            {"key": "search_insights", "state": "success", "message": ""},
            {"key": "comments", "state": "cancelled", "message": ""},
        ])

    def test_pending_stage_remains_after_plan_finishes(self) -> None:
        status.try_begin_sync(["videos", "comments"])
        status.update_sync_progress("videos", "Syncing videos...")
        status.fail_stage("videos", "syncing videos")
        status.finish_sync()
        self.assertEqual(status.get_sync_status(), {
            "active": False,
            "stop_requested": False,
            "stages": [
                {"key": "videos", "state": "failed", "message": "syncing videos failed"},
                {"key": "comments", "state": "pending", "message": ""},
            ],
        })

    def test_failure_and_running_sibling_have_distinct_states(self) -> None:
        status.try_begin_sync(["video_analytics", "search_insights"])
        status.update_sync_progress("video_analytics", "Syncing video analytics...")
        status.update_sync_progress("search_insights", "Syncing search insights...")
        status.fail_stage("video_analytics", "syncing video analytics")
        stages = status.get_sync_status()["stages"]
        self.assertEqual(stages[0]["state"], "failed")
        self.assertEqual(stages[1]["state"], "running")

    def test_unselected_or_inactive_updates_are_noops(self) -> None:
        status.update_sync_progress("videos", "Syncing videos...")
        status.try_begin_sync(["videos"])
        status.finish_sync()
        status.update_sync_progress("videos", "late update")
        self.assertEqual(status.get_sync_status()["stages"], [
            {"key": "videos", "state": "pending", "message": ""},
        ])


class StopRequestTest(SyncStatusTestCase):
    def test_stop_is_idempotent_and_checkpoint_raises(self) -> None:
        self.assertFalse(status.request_stop())
        status.try_begin_sync(["videos"])
        self.assertTrue(status.request_stop())
        self.assertTrue(status.request_stop())
        self.assertEqual(status.get_sync_status()["stop_requested"], True)
        with self.assertRaises(status.SyncCancelled):
            status.raise_if_stopping()
        status.finish_sync()
        self.assertFalse(status.request_stop())

    def test_new_reservation_clears_stop_flag_and_previous_stages(self) -> None:
        status.try_begin_sync(["videos"])
        status.request_stop()
        status.finish_sync()
        status.try_begin_sync(["comments"])
        self.assertEqual(status.get_sync_status(), {
            "active": True,
            "stop_requested": False,
            "stages": [{"key": "comments", "state": "pending", "message": ""}],
        })

    def test_stop_still_succeeds_after_all_stages_finish_but_before_release(self) -> None:
        status.try_begin_sync(["videos"])
        status.update_sync_progress("videos", "Syncing videos...")
        status.complete_stage("videos")

        self.assertTrue(status.request_stop())
        self.assertTrue(status.get_sync_status()["stop_requested"])
        status.finish_sync()
        self.assertEqual(status.get_sync_status()["stages"][0]["state"], "success")

    def test_stage_completing_after_stop_is_recorded_cancelled_not_success(self) -> None:
        status.try_begin_sync(["videos"])
        status.update_sync_progress("videos", "Syncing videos...")
        status.request_stop()

        status.complete_stage("videos")

        self.assertEqual(status.get_sync_status()["stages"][0]["state"], "cancelled")

    def test_reset_clears_everything(self) -> None:
        status.try_begin_sync(["videos"])
        status.request_stop()
        status.reset_sync_status()
        self.assertEqual(status.get_sync_status(), {"active": False, "stop_requested": False, "stages": []})


if __name__ == "__main__":
    unittest.main()
