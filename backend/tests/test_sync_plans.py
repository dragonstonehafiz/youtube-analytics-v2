from __future__ import annotations

import unittest
from unittest import mock

from sync.plans import (
    PlanStage,
    PlanValidationError,
    available_years,
    full_incremental_plan,
    recorded_scope,
    recorded_year,
    validate_plan,
)


class AvailableYearsTest(unittest.TestCase):
    def test_spans_earliest_to_current_newest_first(self) -> None:
        with mock.patch("sync.plans.database.get_earliest_published_year", return_value=2023), \
                mock.patch("sync.plans.date") as fake_date:
            fake_date.today.return_value.year = 2025
            self.assertEqual(available_years(), (2025, 2024, 2023))

    def test_empty_when_no_videos_synced(self) -> None:
        with mock.patch("sync.plans.database.get_earliest_published_year", return_value=None):
            self.assertEqual(available_years(), ())

    def test_empty_when_earliest_year_is_in_the_future(self) -> None:
        with mock.patch("sync.plans.database.get_earliest_published_year", return_value=2099), \
                mock.patch("sync.plans.date") as fake_date:
            fake_date.today.return_value.year = 2025
            self.assertEqual(available_years(), ())


class ValidatePlanTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch("sync.plans.available_years", return_value=(2025, 2024, 2023))
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_accepts_full_incremental_plan(self) -> None:
        self.assertEqual(validate_plan(full_incremental_plan()), full_incremental_plan())

    def test_accepts_independent_periods_per_stage(self) -> None:
        stages = validate_plan([
            PlanStage("video_traffic_sources", "all"),
            PlanStage("video_analytics", "year", 2024),
        ])
        self.assertEqual(stages, (
            PlanStage("video_analytics", "year", 2024),
            PlanStage("video_traffic_sources", "all"),
        ))

    def test_returns_canonical_order_regardless_of_submission_order(self) -> None:
        stages = validate_plan([
            PlanStage("fx_rates"),
            PlanStage("video_analytics", "incremental"),
            PlanStage("videos"),
        ])
        self.assertEqual([s.stage for s in stages], ["videos", "video_analytics", "fx_rates"])

    def test_is_idempotent(self) -> None:
        once = validate_plan([PlanStage("videos"), PlanStage("video_analytics", "all")])
        self.assertEqual(validate_plan(once), once)

    def test_rejects_empty_plan(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([])

    def test_rejects_duplicate_stage(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("videos"), PlanStage("videos")])

    def test_rejects_unknown_stage(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("comments")])

    def test_rejects_period_aware_stage_without_scope(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("video_analytics")])

    def test_rejects_unknown_scope(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("video_analytics", "last_week")])

    def test_rejects_year_scope_without_year(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("video_analytics", "year")])

    def test_rejects_year_supplied_with_incremental_scope(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("video_analytics", "incremental", 2024)])

    def test_rejects_year_supplied_with_all_scope(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("video_analytics", "all", 2024)])

    def test_rejects_scope_on_non_period_stage(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("videos", "all")])

    def test_rejects_year_on_non_period_stage(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("fx_rates", None, 2024)])

    def test_rejects_scope_on_pruning(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("pruning", "all"), PlanStage("playlists"), PlanStage("videos")])

    def test_rejects_pruning_without_playlists_or_videos(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("pruning")])

    def test_rejects_pruning_without_videos(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("pruning"), PlanStage("playlists")])

    def test_rejects_pruning_without_playlists(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("pruning"), PlanStage("videos")])

    def test_accepts_pruning_with_both_prerequisites_in_any_submission_order(self) -> None:
        stages = validate_plan([PlanStage("pruning"), PlanStage("videos"), PlanStage("playlists")])
        self.assertEqual([s.stage for s in stages], ["playlists", "videos", "pruning"])

    def test_rejects_year_before_earliest_available(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("video_analytics", "year", 2022)])

    def test_rejects_future_year(self) -> None:
        with self.assertRaises(PlanValidationError):
            validate_plan([PlanStage("video_analytics", "year", 2026)])


class ValidatePlanWithoutVideosTest(unittest.TestCase):
    def test_rejects_year_scope_when_no_years_available(self) -> None:
        with mock.patch("sync.plans.available_years", return_value=()):
            with self.assertRaises(PlanValidationError):
                validate_plan([PlanStage("video_analytics", "year", 2024)])

    def test_still_accepts_incremental_and_full_history(self) -> None:
        with mock.patch("sync.plans.available_years", return_value=()):
            stages = validate_plan([
                PlanStage("video_analytics", "incremental"),
                PlanStage("video_traffic_sources", "all"),
            ])
        self.assertEqual(len(stages), 2)


class RecordedValuesTest(unittest.TestCase):
    def test_period_aware_stage_records_its_own_scope_and_year(self) -> None:
        stage = PlanStage("video_analytics", "year", 2024)
        self.assertEqual(recorded_scope(stage), "year")
        self.assertEqual(recorded_year(stage), 2024)

    def test_non_period_stage_records_incremental_and_no_year(self) -> None:
        stage = PlanStage("fx_rates")
        self.assertEqual(recorded_scope(stage), "incremental")
        self.assertIsNone(recorded_year(stage))


class FullIncrementalPlanTest(unittest.TestCase):
    def test_contains_all_five_non_destructive_stages_in_canonical_order(self) -> None:
        self.assertEqual(
            [s.stage for s in full_incremental_plan()],
            ["playlists", "videos", "video_analytics", "video_traffic_sources", "fx_rates"],
        )

    def test_excludes_pruning(self) -> None:
        self.assertNotIn("pruning", [s.stage for s in full_incremental_plan()])

    def test_both_period_aware_stages_are_incremental(self) -> None:
        by_stage = {s.stage: s for s in full_incremental_plan()}
        self.assertEqual(by_stage["video_analytics"].scope, "incremental")
        self.assertEqual(by_stage["video_traffic_sources"].scope, "incremental")
        self.assertIsNone(by_stage["video_analytics"].year)
        self.assertIsNone(by_stage["video_traffic_sources"].year)


if __name__ == "__main__":
    unittest.main()
