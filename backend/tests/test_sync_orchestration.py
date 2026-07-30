from __future__ import annotations

import unittest
from unittest import mock

from sync import status
from sync.orchestration import execute_plan, run_plan
from sync.plans import PlanStage, PlanValidationError, full_incremental_plan


class OrchestrationTestCase(unittest.TestCase):
    """Base case that stubs every stage function and all sync_runs persistence."""

    def setUp(self) -> None:
        status.finish()
        self.addCleanup(status.finish)

        self.calls: list[str] = []
        self.stage_mocks: dict[str, mock.Mock] = {
            name: self._patch_stage(name)
            for name in (
                "sync_videos",
                "sync_playlists",
                "sync_video_analytics",
                "sync_video_traffic_sources",
                "sync_fx_rates",
            )
        }

        self.db = self._patch("sync.orchestration.database")
        self.created: list[tuple] = []
        self.db.create_sync_run.side_effect = self._record_sync_run

    def _record_sync_run(self, *args: object) -> int:
        """Stand in for database.create_sync_run, capturing its arguments."""
        self.created.append(args)
        return len(self.created)

    def _patch(self, target: str) -> mock.Mock:
        patcher = mock.patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _patch_stage(self, name: str) -> mock.Mock:
        stage_mock = self._patch(f"sync.orchestration.{name}")
        stage_mock.side_effect = lambda *args: self.calls.append(name)
        return stage_mock

    @property
    def recorded_stages(self) -> list[str]:
        return [args[1] for args in self.created]


class SelectedStageExecutionTest(OrchestrationTestCase):
    def test_runs_only_selected_stages(self) -> None:
        execute_plan([PlanStage("fx_rates"), PlanStage("videos")])

        self.assertEqual(self.calls, ["sync_videos", "sync_fx_rates"])
        self.stage_mocks["sync_playlists"].assert_not_called()
        self.stage_mocks["sync_video_analytics"].assert_not_called()
        self.stage_mocks["sync_video_traffic_sources"].assert_not_called()

    def test_runs_in_canonical_order_regardless_of_submission_order(self) -> None:
        execute_plan([
            PlanStage("fx_rates"),
            PlanStage("video_traffic_sources", "all"),
            PlanStage("playlists"),
        ])

        self.assertEqual(
            self.calls,
            ["sync_playlists", "sync_video_traffic_sources", "sync_fx_rates"],
        )

    def test_creates_one_row_per_started_stage_only(self) -> None:
        execute_plan([PlanStage("videos"), PlanStage("fx_rates")])

        self.assertEqual(self.recorded_stages, ["videos", "fx_rates"])
        self.assertEqual(self.db.create_sync_run.call_count, 2)

    def test_all_started_stages_share_one_batch_id(self) -> None:
        execute_plan(full_incremental_plan())

        batch_ids = {args[0] for args in self.created}
        self.assertEqual(len(self.created), 5)
        self.assertEqual(len(batch_ids), 1)

    def test_records_independent_scopes_for_period_aware_stages(self) -> None:
        with mock.patch("sync.plans.available_years", return_value=(2025, 2024)):
            execute_plan([
                PlanStage("video_analytics", "year", 2024),
                PlanStage("video_traffic_sources", "all"),
            ])

        by_stage = {args[1]: args for args in self.created}
        self.assertEqual(by_stage["video_analytics"][2:], ("year", 2024))
        self.assertEqual(by_stage["video_traffic_sources"][2:], ("all", None))

    def test_records_incremental_and_no_year_for_non_period_stages(self) -> None:
        execute_plan([PlanStage("videos"), PlanStage("playlists"), PlanStage("fx_rates")])

        for args in self.created:
            self.assertEqual(args[2:], ("incremental", None))

    def test_passes_independent_scopes_to_stage_functions(self) -> None:
        with mock.patch("sync.plans.available_years", return_value=(2025, 2024)):
            execute_plan([
                PlanStage("video_analytics", "year", 2024),
                PlanStage("video_traffic_sources", "incremental"),
            ])

        analytics_args = self.stage_mocks["sync_video_analytics"].call_args[0]
        traffic_args = self.stage_mocks["sync_video_traffic_sources"].call_args[0]
        self.assertEqual(analytics_args[:2], ("year", 2024))
        self.assertEqual(traffic_args[:2], ("incremental", None))

    def test_marks_every_successful_stage_complete(self) -> None:
        execute_plan([PlanStage("videos"), PlanStage("fx_rates")])

        self.assertEqual(self.db.complete_sync_run.call_count, 2)
        self.db.fail_sync_run.assert_not_called()


class FailFastTest(OrchestrationTestCase):
    def test_failure_stops_later_stages_and_creates_no_rows_for_them(self) -> None:
        self.stage_mocks["sync_playlists"].side_effect = RuntimeError("quota exceeded")

        with self.assertRaises(RuntimeError):
            execute_plan(full_incremental_plan())

        self.assertEqual(self.recorded_stages, ["videos", "playlists"])
        self.assertEqual(self.calls, ["sync_videos"])

    def test_failed_stage_is_recorded_with_its_error(self) -> None:
        self.stage_mocks["sync_videos"].side_effect = RuntimeError("quota exceeded")

        with self.assertRaises(RuntimeError):
            execute_plan([PlanStage("videos"), PlanStage("fx_rates")])

        self.db.fail_sync_run.assert_called_once()
        self.assertEqual(self.db.fail_sync_run.call_args[0][1], "quota exceeded")

    def test_failure_still_releases_active_state(self) -> None:
        self.stage_mocks["sync_videos"].side_effect = RuntimeError("boom")

        self.assertTrue(status.try_start())
        with self.assertRaises(RuntimeError):
            execute_plan([PlanStage("videos")])

        self.assertFalse(status.is_syncing())

    def test_invalid_plan_releases_active_state_without_running_anything(self) -> None:
        self.assertTrue(status.try_start())

        with self.assertRaises(PlanValidationError):
            execute_plan([])

        self.assertFalse(status.is_syncing())
        self.db.create_sync_run.assert_not_called()


class StatusTest(OrchestrationTestCase):
    def test_releases_active_state_on_success(self) -> None:
        self.assertTrue(status.try_start())
        execute_plan([PlanStage("videos")])

        self.assertFalse(status.is_syncing())
        self.assertEqual(status.get_status()["message"], "Sync complete.")

    def test_reports_failure_message(self) -> None:
        self.stage_mocks["sync_videos"].side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            execute_plan([PlanStage("videos")])

        self.assertIn("boom", status.get_status()["message"])


class RunPlanTest(OrchestrationTestCase):
    def test_acquires_reservation_and_runs(self) -> None:
        self.assertTrue(run_plan([PlanStage("videos")]))

        self.assertEqual(self.calls, ["sync_videos"])
        self.assertFalse(status.is_syncing())

    def test_declines_when_a_sync_is_already_active(self) -> None:
        self.assertTrue(status.try_start("manual sync"))

        self.assertFalse(run_plan(full_incremental_plan()))

        self.assertEqual(self.calls, [])
        self.db.create_sync_run.assert_not_called()
        self.assertTrue(status.is_syncing())

    def test_two_concurrent_reservations_cannot_both_succeed(self) -> None:
        self.assertTrue(status.try_start("first"))
        self.assertFalse(status.try_start("second"))
        self.assertEqual(status.get_status()["message"], "first")


if __name__ == "__main__":
    unittest.main()
