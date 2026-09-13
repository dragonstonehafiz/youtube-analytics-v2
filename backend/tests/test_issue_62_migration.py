from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import database
from tests.support import IsolatedDatabaseTestCase, make_video, make_video_analytics

_MIGRATION_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "issue-62-migration.py"
_spec = importlib.util.spec_from_file_location("issue_62_migration", _MIGRATION_SCRIPT)
assert _spec is not None and _spec.loader is not None
_migration_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration_module)
migrate = _migration_module.migrate
COLLECTORS = _migration_module.COLLECTORS


class MigrateTest(IsolatedDatabaseTestCase):
    def test_marks_every_month_from_publish_through_current_month_for_all_collectors(self) -> None:
        database.upsert_own_video(make_video("v1", "Alpha", published_at="2023-11-15T00:00:00Z"))

        migrate(today=date(2024, 3, 10))

        expected = {"2023-11", "2023-12", "2024-01", "2024-02", "2024-03"}
        for collector in COLLECTORS:
            with self.subTest(collector=collector):
                covered = database.get_covered_periods(collector, "v1", "2023-01", "2024-12")
                self.assertEqual(covered, expected)

    def test_two_videos_with_different_publish_dates_get_independent_ranges(self) -> None:
        database.upsert_own_video(make_video("v1", "Alpha", published_at="2024-01-01T00:00:00Z"))
        database.upsert_own_video(make_video("v2", "Beta", published_at="2024-02-01T00:00:00Z"))

        migrate(today=date(2024, 3, 1))

        self.assertEqual(
            database.get_covered_periods("video_analytics", "v1", "2024-01", "2024-03"),
            {"2024-01", "2024-02", "2024-03"},
        )
        self.assertEqual(
            database.get_covered_periods("video_analytics", "v2", "2024-01", "2024-03"),
            {"2024-02", "2024-03"},
        )

    def test_external_video_is_not_touched(self) -> None:
        database.upsert_own_video(make_video("v-ext", "External", published_at="2020-01-01T00:00:00Z"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-ext'")

        migrate(today=date(2024, 3, 1))

        for collector in COLLECTORS:
            self.assertEqual(database.get_covered_periods(collector, "v-ext", "2000-01", "2100-01"), set())

    def test_rerun_produces_the_identical_key_set(self) -> None:
        database.upsert_own_video(make_video("v1", "Alpha", published_at="2023-11-15T00:00:00Z"))

        migrate(today=date(2024, 3, 10))
        first = database.get_covered_periods("video_analytics", "v1", "2023-01", "2024-12")
        migrate(today=date(2024, 3, 10))
        second = database.get_covered_periods("video_analytics", "v1", "2023-01", "2024-12")

        self.assertEqual(first, second)

    def test_missing_published_at_aborts_with_no_writes(self) -> None:
        database.upsert_own_video(make_video("v-good", "Good", published_at="2024-01-01T00:00:00Z"))
        database.upsert_own_video(make_video("v-bad", "Bad", published_at="2024-01-01T00:00:00Z"))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET published_at = NULL WHERE id = 'v-bad'")

        with self.assertRaises(ValueError) as ctx:
            migrate(today=date(2024, 3, 1))

        self.assertIn("v-bad", str(ctx.exception))
        for collector in COLLECTORS:
            self.assertEqual(database.get_covered_periods(collector, "v-good", "2000-01", "2100-01"), set())

    def test_return_value_reports_owned_video_count_and_per_collector_totals(self) -> None:
        database.upsert_own_video(make_video("v1", "Alpha", published_at="2024-01-01T00:00:00Z"))

        result = migrate(today=date(2024, 3, 1))

        self.assertEqual(result["owned_videos"], 1)
        for collector in COLLECTORS:
            self.assertEqual(result[collector], 3)

    def test_never_touches_analytics_reporting_tables(self) -> None:
        database.upsert_own_video(make_video("v1", "Alpha", published_at="2024-01-01T00:00:00Z"))
        database.upsert_video_analytics(make_video_analytics("v1", "2024-01-05", views=42))

        migrate(today=date(2024, 3, 1))

        rows = database.get_video_analytics("v1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["views"], 42)

    def test_creates_the_coverage_table_on_a_pre_issue_62_database(self) -> None:
        with database.get_connection() as conn:
            conn.execute("DROP TABLE sync_coverage")
        database.upsert_own_video(make_video("v1", "Alpha", published_at="2024-01-01T00:00:00Z"))

        migrate(today=date(2024, 3, 1))

        self.assertEqual(
            database.get_covered_periods("video_analytics", "v1", "2024-01", "2024-03"),
            {"2024-01", "2024-02", "2024-03"},
        )
