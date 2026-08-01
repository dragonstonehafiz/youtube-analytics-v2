from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from sync import scheduler


def _iso(moment: datetime) -> str:
    """Render a UTC ISO 8601 timestamp the way database._now() does."""
    return moment.astimezone(timezone.utc).isoformat()


class SyncedTodayTest(unittest.TestCase):
    def _with_checkpoint(self, completed_at: str | None) -> mock.Mock:
        patcher = mock.patch.object(
            scheduler.database,
            "get_last_successful_run_completed_at",
            return_value=completed_at,
        )
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_true_when_any_sync_succeeded_today(self) -> None:
        self._with_checkpoint(_iso(datetime.now().astimezone()))
        self.assertTrue(scheduler.synced_today())

    def test_false_when_the_last_success_was_yesterday(self) -> None:
        self._with_checkpoint(_iso(datetime.now().astimezone() - timedelta(days=1)))
        self.assertFalse(scheduler.synced_today())

    def test_false_when_nothing_has_ever_succeeded(self) -> None:
        self._with_checkpoint(None)
        self.assertFalse(scheduler.synced_today())

    def test_false_when_the_timestamp_is_unparseable(self) -> None:
        self._with_checkpoint("not-a-timestamp")
        self.assertFalse(scheduler.synced_today())

    def test_queries_any_successful_run_without_naming_sync_types(self) -> None:
        """The check no longer depends on the five-stage pipeline being complete."""
        query = self._with_checkpoint(None)
        scheduler.synced_today()
        query.assert_called_once_with()


class StartBackgroundSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run_plan = self._patch("sync.scheduler.run_plan")
        self.thread = self._patch("sync.scheduler.threading.Thread")

    def _patch(self, target: str) -> mock.Mock:
        patcher = mock.patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_does_nothing_when_already_synced_today(self) -> None:
        with mock.patch("sync.scheduler.synced_today", return_value=True):
            scheduler.start_background_scheduler()

        self.thread.assert_not_called()
        self.run_plan.assert_not_called()

    def test_starts_a_daemon_thread_when_stale(self) -> None:
        with mock.patch("sync.scheduler.synced_today", return_value=False):
            scheduler.start_background_scheduler()

        self.thread.assert_called_once()
        self.assertTrue(self.thread.call_args.kwargs["daemon"])
        self.thread.return_value.start.assert_called_once()

    def test_thread_runs_the_complete_incremental_plan(self) -> None:
        with mock.patch("sync.scheduler.synced_today", return_value=False):
            scheduler.start_background_scheduler()

        self.thread.call_args.kwargs["target"]()

        self.run_plan.assert_called_once()
        stages = self.run_plan.call_args[0][0]
        self.assertEqual(
            [s.stage for s in stages],
            ["playlists", "videos", "video_analytics", "video_traffic_sources", "fx_rates"],
        )
        by_stage = {s.stage: s for s in stages}
        self.assertEqual(by_stage["video_analytics"].scope, "incremental")
        self.assertEqual(by_stage["video_traffic_sources"].scope, "incremental")

    def test_startup_plan_never_includes_pruning(self) -> None:
        """Pruning deletes videos and must never run unattended, even if the startup
        plan is later extended with more stages."""
        with mock.patch("sync.scheduler.synced_today", return_value=False):
            scheduler.start_background_scheduler()

        self.thread.call_args.kwargs["target"]()

        stages = self.run_plan.call_args[0][0]
        self.assertNotIn("pruning", [s.stage for s in stages])

    def test_schedules_no_recurring_timer(self) -> None:
        with mock.patch("sync.scheduler.synced_today", return_value=False), \
                mock.patch("sync.scheduler.threading.Timer", create=True) as timer:
            scheduler.start_background_scheduler()

        timer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
