from __future__ import annotations

import unittest

import database
from tests.support import IsolatedDatabaseTestCase, freeze_now, make_video


class SyncCoverageSchemaTest(IsolatedDatabaseTestCase):
    def test_schema_initializes_idempotently_against_an_existing_database(self) -> None:
        database.init_db()
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_coverage'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_video_deletion_cascades_to_sync_coverage(self) -> None:
        database.upsert_own_video(make_video("v-1", "Alpha"))
        database.upsert_coverage("video_analytics", "v-1", ["2024-01"])
        with database.get_connection() as conn:
            conn.execute("DELETE FROM videos WHERE id = 'v-1'")
            rows = conn.execute("SELECT * FROM sync_coverage WHERE video_id = 'v-1'").fetchall()
        self.assertEqual(rows, [])


class UpsertCoverageTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Alpha"))
        database.upsert_own_video(make_video("v-2", "Beta"))

    def test_upsert_returns_the_number_of_periods_written(self) -> None:
        rows_written = database.upsert_coverage("video_analytics", "v-1", ["2024-01", "2024-02"])
        self.assertEqual(rows_written, 2)

    def test_empty_period_keys_is_a_no_op(self) -> None:
        rows_written = database.upsert_coverage("video_analytics", "v-1", [])
        self.assertEqual(rows_written, 0)
        self.assertEqual(database.get_covered_periods("video_analytics", "v-1", "2024-01", "2024-12"), set())

    def test_two_collectors_on_the_same_video_and_month_are_independent(self) -> None:
        database.upsert_coverage("video_analytics", "v-1", ["2024-01"])
        self.assertEqual(database.get_covered_periods("video_traffic_sources", "v-1", "2024-01", "2024-01"), set())

    def test_two_videos_on_the_same_collector_and_month_are_independent(self) -> None:
        database.upsert_coverage("video_analytics", "v-1", ["2024-01"])
        self.assertEqual(database.get_covered_periods("video_analytics", "v-2", "2024-01", "2024-01"), set())

    def test_repeated_upsert_of_the_same_period_is_idempotent(self) -> None:
        database.upsert_coverage("video_analytics", "v-1", ["2024-01"])
        database.upsert_coverage("video_analytics", "v-1", ["2024-01"])
        self.assertEqual(database.get_covered_periods("video_analytics", "v-1", "2024-01", "2024-01"), {"2024-01"})

    def test_repeated_upsert_refreshes_completed_at(self) -> None:
        with freeze_now("2024-06-01T00:00:00+00:00"):
            database.upsert_coverage("video_analytics", "v-1", ["2024-01"])
        with freeze_now("2024-06-02T00:00:00+00:00"):
            database.upsert_coverage("video_analytics", "v-1", ["2024-01"])
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT completed_at FROM sync_coverage WHERE video_id = 'v-1' AND period_key = '2024-01'"
            ).fetchone()
        self.assertEqual(row["completed_at"], "2024-06-02T00:00:00+00:00")


class GetCoveredPeriodsTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_own_video(make_video("v-1", "Alpha"))
        database.upsert_coverage("video_analytics", "v-1", ["2023-11", "2023-12", "2024-01", "2024-06"])

    def test_range_is_inclusive_of_both_bounds(self) -> None:
        covered = database.get_covered_periods("video_analytics", "v-1", "2023-12", "2024-01")
        self.assertEqual(covered, {"2023-12", "2024-01"})

    def test_periods_outside_the_range_are_excluded(self) -> None:
        covered = database.get_covered_periods("video_analytics", "v-1", "2023-12", "2024-01")
        self.assertNotIn("2023-11", covered)
        self.assertNotIn("2024-06", covered)

    def test_no_coverage_in_range_returns_empty_set(self) -> None:
        covered = database.get_covered_periods("video_analytics", "v-1", "2024-02", "2024-05")
        self.assertEqual(covered, set())

    def test_unknown_video_returns_empty_set(self) -> None:
        covered = database.get_covered_periods("video_analytics", "missing-video", "2024-01", "2024-12")
        self.assertEqual(covered, set())


if __name__ == "__main__":
    unittest.main()
