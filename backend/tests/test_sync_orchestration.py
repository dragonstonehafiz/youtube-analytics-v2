from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from unittest import mock

from logging_config import configure_logging, reset_logging
from sync import status
from sync.orchestration import execute_plan, run_plan
from sync.plans import PlanStage, PlanValidationError, full_incremental_plan

# Direct imports of `sync.orchestration` self-configure logging at module load, before
# any test's setUp runs. Redirect it to a disposable directory for this whole module so
# the suite never appends to a developer's real `backend/data/*.log`, then reset to an
# unconfigured state afterwards. Teardown must not call `configure_logging()` with no
# arguments: that would rebind handlers to the real log paths and leave every later test
# module in the process writing to them.
_tmpdir: Optional[TemporaryDirectory] = None


def setUpModule() -> None:
    global _tmpdir
    _tmpdir = TemporaryDirectory()
    configure_logging(
        app_path=Path(_tmpdir.name) / "application.log",
        sync_path=Path(_tmpdir.name) / "sync.log",
    )


def tearDownModule() -> None:
    reset_logging()
    assert _tmpdir is not None
    _tmpdir.cleanup()


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


class PlanLevelLoggingTest(OrchestrationTestCase):
    def test_accepted_plan_logs_selected_types_without_counts(self) -> None:
        with self.assertLogs("youtube_analytics.sync", level="INFO") as captured:
            execute_plan([PlanStage("videos"), PlanStage("fx_rates")])

        plan_messages = [
            record.getMessage() for record in captured.records
            if record.getMessage().startswith("Sync plan started")
        ]
        self.assertEqual(plan_messages, ["Sync plan started sync_types=videos,fx_rates"])
        self.assertNotIn("rows_fetched", plan_messages[0])

    def test_validation_failure_logs_error_and_still_raises(self) -> None:
        with self.assertLogs("youtube_analytics.sync", level="ERROR") as captured:
            with self.assertRaises(PlanValidationError):
                execute_plan([])

        messages = [record.getMessage() for record in captured.records]
        self.assertTrue(any(m.startswith("Sync plan rejected") for m in messages))
        for record in captured.records:
            self.assertEqual(record.levelname, "ERROR")

    def test_already_active_logs_warning_and_returns_false(self) -> None:
        self.assertTrue(status.try_start("already running"))

        with self.assertLogs("youtube_analytics.sync", level="WARNING") as captured:
            result = run_plan(full_incremental_plan())

        self.assertFalse(result)
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["Sync plan skipped reason=already_active"])


class StageLoggingTest(OrchestrationTestCase):
    def test_each_sync_type_logs_start_and_completion(self) -> None:
        with self.assertLogs("youtube_analytics.sync", level="INFO") as captured:
            execute_plan(list(full_incremental_plan()))

        messages = [record.getMessage() for record in captured.records]
        for sync_type in ("videos", "playlists", "video_analytics", "video_traffic_sources", "fx_rates"):
            self.assertIn(
                f"Sync stage started sync_type={sync_type} rows_fetched=0 rows_written=0 rows_deleted=0",
                messages,
            )
            self.assertTrue(any(m.startswith(f"Sync stage completed sync_type={sync_type} ") for m in messages))

    def test_no_op_stage_logs_rows_fetched_zero(self) -> None:
        with self.assertLogs("youtube_analytics.sync", level="INFO") as captured:
            execute_plan([PlanStage("fx_rates")])

        messages = [record.getMessage() for record in captured.records]
        self.assertIn(
            "Sync stage completed sync_type=fx_rates rows_fetched=0 rows_written=0 rows_deleted=0", messages
        )

    def test_independent_stage_counts_are_never_summed(self) -> None:
        def videos_side_effect(counts: object) -> None:
            self.calls.append("sync_videos")
            counts.rows_fetched = 10  # type: ignore[attr-defined]

        def fx_side_effect(counts: object) -> None:
            self.calls.append("sync_fx_rates")
            counts.rows_fetched = 3  # type: ignore[attr-defined]

        self.stage_mocks["sync_videos"].side_effect = videos_side_effect
        self.stage_mocks["sync_fx_rates"].side_effect = fx_side_effect

        with self.assertLogs("youtube_analytics.sync", level="INFO") as captured:
            execute_plan([PlanStage("videos"), PlanStage("fx_rates")])

        messages = [record.getMessage() for record in captured.records]
        self.assertIn(
            "Sync stage completed sync_type=videos rows_fetched=10 rows_written=0 rows_deleted=0", messages
        )
        self.assertIn(
            "Sync stage completed sync_type=fx_rates rows_fetched=3 rows_written=0 rows_deleted=0", messages
        )

    def test_run_plan_full_incremental_uses_the_same_templates(self) -> None:
        with self.assertLogs("youtube_analytics.sync", level="INFO") as captured:
            self.assertTrue(run_plan(full_incremental_plan()))

        messages = [record.getMessage() for record in captured.records]
        self.assertTrue(any(m.startswith("Sync stage completed sync_type=fx_rates") for m in messages))


class StageFailureLoggingTest(OrchestrationTestCase):
    def test_stage_failure_logs_partial_counts_and_safe_context_not_secret_text(self) -> None:
        def fail(counts: object) -> None:
            self.calls.append("sync_videos")
            counts.rows_fetched = 7  # type: ignore[attr-defined]
            raise RuntimeError('access_token=FAKE_OAUTH_TOKEN body={"quotaExceeded": true}')

        self.stage_mocks["sync_videos"].side_effect = fail

        with self.assertLogs("youtube_analytics.sync", level="ERROR") as captured:
            with self.assertRaises(RuntimeError):
                execute_plan([PlanStage("videos")])

        messages = [record.getMessage() for record in captured.records]
        failure_messages = [m for m in messages if m.startswith("Sync stage failed")]
        self.assertEqual(len(failure_messages), 1)
        self.assertIn("sync_type=videos rows_fetched=7", failure_messages[0])
        self.assertIn("exception_type=RuntimeError", failure_messages[0])
        self.assertNotIn("FAKE_OAUTH_TOKEN", failure_messages[0])
        self.assertNotIn("quotaExceeded", failure_messages[0])

        self.db.fail_sync_run.assert_called_once()
        self.assertEqual(
            self.db.fail_sync_run.call_args[0][1],
            'access_token=FAKE_OAUTH_TOKEN body={"quotaExceeded": true}',
        )


class PersistenceFailureLoggingTest(OrchestrationTestCase):
    def test_create_sync_run_failure_logs_error_and_reraises_without_stage_call(self) -> None:
        self.db.create_sync_run.side_effect = RuntimeError("db locked")

        with self.assertLogs("youtube_analytics.sync", level="ERROR") as captured:
            with self.assertRaises(RuntimeError):
                execute_plan([PlanStage("videos")])

        messages = [record.getMessage() for record in captured.records]
        self.assertTrue(any("operation=create_sync_run" in m for m in messages))
        self.stage_mocks["sync_videos"].assert_not_called()
        self.db.complete_sync_run.assert_not_called()
        self.db.fail_sync_run.assert_not_called()

    def test_complete_sync_run_failure_logs_error_and_reraises(self) -> None:
        self.db.complete_sync_run.side_effect = RuntimeError("db locked")

        with self.assertLogs("youtube_analytics.sync", level="ERROR") as captured:
            with self.assertRaises(RuntimeError):
                execute_plan([PlanStage("videos")])

        messages = [record.getMessage() for record in captured.records]
        self.assertTrue(any("operation=complete_sync_run" in m for m in messages))
        self.db.fail_sync_run.assert_not_called()

    def test_fail_sync_run_failure_logs_error_and_reraises_the_persistence_exception(self) -> None:
        self.stage_mocks["sync_videos"].side_effect = RuntimeError("stage boom")
        self.db.fail_sync_run.side_effect = RuntimeError("persist boom")

        with self.assertLogs("youtube_analytics.sync", level="ERROR") as captured:
            with self.assertRaises(RuntimeError) as ctx:
                execute_plan([PlanStage("videos")])

        self.assertEqual(str(ctx.exception), "persist boom")
        messages = [record.getMessage() for record in captured.records]
        self.assertTrue(any("operation=fail_sync_run" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
