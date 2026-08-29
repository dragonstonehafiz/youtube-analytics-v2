from __future__ import annotations

import unittest

import database
from tests.support import (
    IsolatedDatabaseTestCase,
    make_fx_rate,
    make_traffic_source,
    make_video,
    make_video_analytics,
)


class AnalyticsFixtureTestCase(IsolatedDatabaseTestCase):
    def _seed(self) -> None:
        """Two videos with analytics on 2024-01-01 (has FX) and 2024-01-03 (no FX),
        leaving 2024-01-02 with no analytics row at all for zero-fill coverage."""
        database.upsert_video(make_video("v-1", "Alpha", content_type="video"))
        database.upsert_video(make_video("v-2", "Beta", content_type="short"))
        database.upsert_video_analytics(make_video_analytics("v-1", "2024-01-01", views=100, watch_time_minutes=60, estimated_revenue=10.0))
        database.upsert_video_analytics(make_video_analytics("v-2", "2024-01-01", views=50, watch_time_minutes=20, estimated_revenue=5.0))
        database.upsert_video_analytics(make_video_analytics("v-1", "2024-01-03", views=200, watch_time_minutes=90, estimated_revenue=20.0))
        database.upsert_fx_rate(make_fx_rate("2024-01-01", 1.5))


class AggregatedAnalyticsTest(AnalyticsFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed()

    def test_per_content_type_groups_stay_independent(self) -> None:
        rows = database.get_aggregated_analytics(start_date="2024-01-01", end_date="2024-01-03")
        by_key = {(r["date"], r["content_type"]): r for r in rows}
        self.assertEqual(by_key[("2024-01-01", "video")]["views"], 100)
        self.assertEqual(by_key[("2024-01-01", "short")]["views"], 50)

    def test_date_bounds_are_inclusive(self) -> None:
        rows = database.get_aggregated_analytics(start_date="2024-01-01", end_date="2024-01-01")
        self.assertEqual({r["date"] for r in rows}, {"2024-01-01"})

    def test_missing_date_content_type_combination_is_zero_filled(self) -> None:
        rows = database.get_aggregated_analytics(start_date="2024-01-01", end_date="2024-01-03")
        missing = next(r for r in rows if r["date"] == "2024-01-02" and r["content_type"] == "video")
        self.assertEqual(missing["views"], 0)

    def test_trailing_dates_after_the_last_real_row_are_trimmed(self) -> None:
        rows = database.get_aggregated_analytics(start_date="2024-01-01", end_date="2024-01-10")
        self.assertEqual(max(r["date"] for r in rows), "2024-01-03")

    def test_fx_conversion_uses_the_matching_date_rate(self) -> None:
        rows = database.get_aggregated_analytics(start_date="2024-01-01", end_date="2024-01-01", content_type="video")
        self.assertAlmostEqual(rows[0]["estimated_revenue_sgd"], 15.0)

    def test_missing_fx_rate_contributes_zero_not_an_error(self) -> None:
        rows = database.get_aggregated_analytics(start_date="2024-01-03", end_date="2024-01-03", content_type="video")
        self.assertEqual(rows[0]["estimated_revenue_sgd"], 0)

    def test_no_data_in_range_returns_empty_list(self) -> None:
        rows = database.get_aggregated_analytics(start_date="2025-01-01", end_date="2025-01-31")
        self.assertEqual(rows, [])


class AggregatedTrafficSourcesTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_video(make_video("v-1", "Alpha"))
        database.upsert_video(make_video("v-2", "Beta"))
        # Both videos have SEARCH data on the same date, so aggregation must sum across
        # videos rather than just echoing one video's number.
        database.upsert_video_traffic_source(make_traffic_source("v-1", "2024-01-01", "SEARCH", views=30, watch_time_minutes=10))
        database.upsert_video_traffic_source(make_traffic_source("v-1", "2024-01-01", "SUGGESTED", views=20, watch_time_minutes=5))
        database.upsert_video_traffic_source(make_traffic_source("v-2", "2024-01-01", "SEARCH", views=40, watch_time_minutes=15))
        # v-1 also has a real row in March, so February sits strictly between two real
        # dates and must be zero-filled rather than trimmed as trailing.
        database.upsert_video_traffic_source(make_traffic_source("v-1", "2024-03-15", "SEARCH", views=5, watch_time_minutes=2))

    def test_per_video_traffic_sources_are_grouped_by_type(self) -> None:
        rows = database.get_video_traffic_sources("v-1")
        self.assertEqual({r["traffic_source_type"] for r in rows if r["views"]}, {"SEARCH", "SUGGESTED"})

    def test_aggregated_traffic_sums_across_videos(self) -> None:
        rows = database.get_aggregated_traffic_sources(start_date="2024-01-01", end_date="2024-01-01")
        search_row = next(r for r in rows if r["traffic_source_type"] == "SEARCH" and r["date"] == "2024-01-01")
        self.assertEqual(search_row["views"], 70)

    def test_missing_month_is_zero_filled_on_the_first_of_the_month_only(self) -> None:
        rows = database.get_video_traffic_sources("v-1", start_date="2024-01-01", end_date="2024-03-15")
        february_rows = [r for r in rows if r["date"].startswith("2024-02")]
        self.assertEqual([r["date"] for r in february_rows], ["2024-02-01", "2024-02-01"])
        self.assertEqual({r["traffic_source_type"] for r in february_rows}, {"SEARCH", "SUGGESTED"})
        self.assertTrue(all(r["views"] == 0 for r in february_rows))


class FxRatesTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_fx_rate(make_fx_rate("2024-01-01", 1.30))
        database.upsert_fx_rate(make_fx_rate("2024-01-15", 1.35))
        database.upsert_fx_rate(make_fx_rate("2024-02-01", 1.40))

    def test_range_filter_is_inclusive(self) -> None:
        rows = database.get_fx_rates(start_date="2024-01-01", end_date="2024-01-15")
        self.assertEqual([r["date"] for r in rows], ["2024-01-01", "2024-01-15"])

    def test_last_fx_rate_is_the_latest_date(self) -> None:
        latest = database.get_last_fx_rate()
        assert latest is not None
        self.assertEqual(latest["date"], "2024-02-01")

    def test_empty_table_returns_none(self) -> None:
        with database.get_connection() as conn:
            conn.execute("DELETE FROM fx_rates")
        self.assertIsNone(database.get_last_fx_rate())


class TopVideosOrderingTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_video(make_video("v-1", "Alpha"))
        database.upsert_video(make_video("v-2", "Beta"))
        database.upsert_video(make_video("v-3", "Gamma"))
        # v-1 and v-2 tie on views to prove the deterministic id tie-breaker.
        database.upsert_video_analytics(make_video_analytics("v-1", "2024-01-01", views=100, watch_time_minutes=5))
        database.upsert_video_analytics(make_video_analytics("v-2", "2024-01-01", views=100, watch_time_minutes=50))
        database.upsert_video_analytics(make_video_analytics("v-3", "2024-01-01", views=50, watch_time_minutes=10))

    def test_orders_by_views_descending_by_default(self) -> None:
        rows = database.get_top_videos_by_views(start_date="2024-01-01", end_date="2024-01-01")
        self.assertEqual([r["id"] for r in rows][:2], ["v-1", "v-2"])
        self.assertEqual(rows[-1]["id"], "v-3")

    def test_tied_views_break_ties_by_ascending_id(self) -> None:
        rows = database.get_top_videos_by_views(start_date="2024-01-01", end_date="2024-01-01")
        tied = [r["id"] for r in rows if r["id"] in ("v-1", "v-2")]
        self.assertEqual(tied, ["v-1", "v-2"])

    def test_watch_time_sort_reorders_by_watch_time(self) -> None:
        rows = database.get_top_videos_by_views(start_date="2024-01-01", end_date="2024-01-01", sort_by="watch_time")
        self.assertEqual(rows[0]["id"], "v-2")

    def test_limit_truncates_results(self) -> None:
        rows = database.get_top_videos_by_views(start_date="2024-01-01", end_date="2024-01-01", limit=1)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
