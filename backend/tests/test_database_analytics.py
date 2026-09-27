from __future__ import annotations

import unittest
from typing import Any

import database
from database import writer
from database import FxRate, Video, queries, reader
from routes.analytics import _analytics_totals, _traffic_source_totals
from routes.videos import router as videos_router
from tests.support import (
    IsolatedDatabaseTestCase,
    create_test_client,
    make_fx_rate,
    make_traffic_source,
    make_video,
    make_video_analytics,
)


def _top_video_ids(**filters: Any) -> list[str | None]:
    """Return the top-videos spec's ranked video IDs."""
    rows = reader.fetch_joined(queries.top_videos_by_views(**filters), (Video,), queries.TOP_VIDEO_VALUES)
    return [row[Video].id for row in rows]


class AnalyticsFixtureTestCase(IsolatedDatabaseTestCase):
    def _seed(self) -> None:
        """Seed videos and analytics with both present and missing FX rates."""
        writer.write(make_video("v-1", "Alpha", content_type="video"))
        writer.write(make_video("v-2", "Beta", content_type="short"))
        writer.write(make_video_analytics("v-1", "2024-01-01", views=100, watch_time_minutes=60, estimated_revenue=10.0))
        writer.write(make_video_analytics("v-2", "2024-01-01", views=50, watch_time_minutes=20, estimated_revenue=5.0))
        writer.write(make_video_analytics("v-1", "2024-01-03", views=200, watch_time_minutes=90, estimated_revenue=20.0))
        writer.write(make_fx_rate("2024-01-01", 1.5))


class AggregatedAnalyticsTest(AnalyticsFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed()

    def test_per_content_type_groups_stay_independent(self) -> None:
        rows = _analytics_totals(start_date="2024-01-01", end_date="2024-01-03")
        by_key = {(r["date"], r["content_type"]): r for r in rows}
        self.assertEqual(by_key[("2024-01-01", "video")]["views"], 100)
        self.assertEqual(by_key[("2024-01-01", "short")]["views"], 50)

    def test_date_bounds_are_inclusive(self) -> None:
        rows = _analytics_totals(start_date="2024-01-01", end_date="2024-01-01")
        self.assertEqual({r["date"] for r in rows}, {"2024-01-01"})

    def test_missing_date_content_type_combination_is_zero_filled(self) -> None:
        rows = _analytics_totals(start_date="2024-01-01", end_date="2024-01-03")
        missing = next(r for r in rows if r["date"] == "2024-01-02" and r["content_type"] == "video")
        self.assertEqual(missing["views"], 0)

    def test_trailing_dates_after_the_last_real_row_are_trimmed(self) -> None:
        rows = _analytics_totals(start_date="2024-01-01", end_date="2024-01-10")
        self.assertEqual(max(r["date"] for r in rows), "2024-01-03")

    def test_fx_conversion_uses_the_matching_date_rate(self) -> None:
        rows = _analytics_totals(start_date="2024-01-01", end_date="2024-01-01", content_type="video")
        self.assertAlmostEqual(rows[0]["estimated_revenue_sgd"], 15.0)

    def test_missing_fx_rate_contributes_zero_not_an_error(self) -> None:
        rows = _analytics_totals(start_date="2024-01-03", end_date="2024-01-03", content_type="video")
        self.assertEqual(rows[0]["estimated_revenue_sgd"], 0)

    def test_no_data_in_range_returns_empty_list(self) -> None:
        rows = _analytics_totals(start_date="2025-01-01", end_date="2025-01-31")
        self.assertEqual(rows, [])

    def test_leading_gap_and_absent_requested_content_type_are_zero_filled(self) -> None:
        writer.write(make_video("v-3", "Gamma", content_type="video"))
        writer.write(make_video_analytics("v-3", "2023-12-30", views=0))
        rows = _analytics_totals(start_date="2023-12-29", end_date="2024-01-03", content_type="short")
        self.assertEqual([r["date"] for r in rows], ["2023-12-29", "2023-12-30", "2023-12-31", "2024-01-01"])
        self.assertEqual({r["content_type"] for r in rows}, {"short"})
        self.assertEqual(sum(r["views"] for r in rows), 50)

    def test_zero_filled_rows_have_every_metric_key_and_no_video_id(self) -> None:
        rows = _analytics_totals(start_date="2024-01-01", end_date="2024-01-03")
        real = next(r for r in rows if r["date"] == "2024-01-01" and r["content_type"] == "video")
        synthetic = next(r for r in rows if r["date"] == "2024-01-02" and r["content_type"] == "video")
        self.assertEqual(set(synthetic), set(real))
        self.assertNotIn("video_id", synthetic)
        self.assertTrue(all(synthetic[key] == 0 for key in synthetic if key not in ("date", "content_type")))


class VideoAnalyticsRouteTest(AnalyticsFixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed()
        self.client = create_test_client(videos_router)

    def _items(self, video_id: str, **params: str) -> list[dict]:
        response = self.client.get(f"/videos/{video_id}/analytics", params=params)
        self.assertEqual(response.status_code, 200)
        return response.json()["items"]

    def test_real_rows_keep_stored_fields_and_convert_revenue(self) -> None:
        rows = self._items("v-1", start_date="2024-01-01", end_date="2024-01-03")
        first = rows[0]
        self.assertEqual((first["video_id"], first["date"], first["views"]), ("v-1", "2024-01-01", 100))
        self.assertEqual(first["content_type"], "video")
        self.assertIsNotNone(first["updated_at"])
        self.assertAlmostEqual(first["estimated_revenue_sgd"], 15.0)
        self.assertEqual(rows[-1]["estimated_revenue_sgd"], 0)

    def test_synthetic_rows_keep_identity_and_zero_only_metrics(self) -> None:
        rows = self._items("v-1", start_date="2024-01-01", end_date="2024-01-10")
        self.assertEqual([r["date"] for r in rows], ["2024-01-01", "2024-01-02", "2024-01-03"])
        synthetic = rows[1]
        self.assertEqual(set(synthetic), set(rows[0]))
        self.assertEqual((synthetic["video_id"], synthetic["content_type"]), ("v-1", "video"))
        self.assertIsNone(synthetic["updated_at"])
        for key in (*queries.ANALYTICS_METRIC_FIELDS, *queries.ANALYTICS_VALUES):
            self.assertEqual(synthetic[key], 0)

    def test_leading_gap_starts_at_the_requested_date(self) -> None:
        rows = self._items("v-2", start_date="2023-12-31", end_date="2024-01-01")
        self.assertEqual([r["date"] for r in rows], ["2023-12-31", "2024-01-01"])
        self.assertEqual(rows[0]["content_type"], "short")

    def test_a_video_without_rows_returns_empty(self) -> None:
        writer.write(make_video("v-3", "Gamma"))
        self.assertEqual(self._items("v-3"), [])


class AggregatedTrafficSourcesTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(videos_router)
        writer.write(make_video("v-1", "Alpha"))
        writer.write(make_video("v-2", "Beta"))
        # Both videos have SEARCH data on the same date, so aggregation must sum across
        # videos rather than just echoing one video's number.
        writer.write(make_traffic_source("v-1", "2024-01-01", "SEARCH", views=30, watch_time_minutes=10))
        writer.write(make_traffic_source("v-1", "2024-01-01", "SUGGESTED", views=20, watch_time_minutes=5))
        writer.write(make_traffic_source("v-2", "2024-01-01", "SEARCH", views=40, watch_time_minutes=15))
        # v-1 also has a real row in March, so February sits strictly between two real
        # dates and must be zero-filled rather than trimmed as trailing.
        writer.write(make_traffic_source("v-1", "2024-03-15", "SEARCH", views=5, watch_time_minutes=2))

    def _video_traffic(self, video_id: str, **params: str) -> list[dict]:
        response = self.client.get(f"/videos/{video_id}/traffic-sources", params=params)
        self.assertEqual(response.status_code, 200)
        return response.json()["items"]

    def test_per_video_traffic_sources_are_grouped_by_type(self) -> None:
        rows = self._video_traffic("v-1")
        self.assertEqual({r["traffic_source_type"] for r in rows if r["views"]}, {"SEARCH", "SUGGESTED"})

    def test_aggregated_traffic_sums_across_videos(self) -> None:
        rows = _traffic_source_totals(start_date="2024-01-01", end_date="2024-01-01")
        search_row = next(r for r in rows if r["traffic_source_type"] == "SEARCH" and r["date"] == "2024-01-01")
        self.assertEqual(search_row["views"], 70)

    def test_every_missing_intermediate_day_is_zero_filled_for_each_source_type(self) -> None:
        rows = self._video_traffic("v-1", start_date="2024-01-01", end_date="2024-03-15")
        february_rows = [r for r in rows if r["date"].startswith("2024-02")]
        self.assertEqual({r["date"] for r in february_rows}, {f"2024-02-{d:02d}" for d in range(1, 30)})
        self.assertEqual({r["traffic_source_type"] for r in february_rows}, {"SEARCH", "SUGGESTED"})
        self.assertTrue(all(r["views"] == 0 and r["watch_time_minutes"] == 0 for r in february_rows))

    def test_real_rows_are_preserved_alongside_zero_fill(self) -> None:
        rows = self._video_traffic("v-1", start_date="2024-01-01", end_date="2024-03-15")
        by_key = {(r["date"], r["traffic_source_type"]): r for r in rows}
        self.assertEqual(by_key[("2024-01-01", "SEARCH")]["views"], 30)
        self.assertEqual(by_key[("2024-01-01", "SUGGESTED")]["views"], 20)
        self.assertEqual(by_key[("2024-03-15", "SEARCH")]["views"], 5)

    def test_explicit_mid_month_start_date_is_not_moved_back_to_the_first(self) -> None:
        rows = self._video_traffic("v-1", start_date="2024-03-10", end_date="2024-03-15")
        self.assertEqual(min(r["date"] for r in rows), "2024-03-10")

    def test_trailing_dates_after_the_last_real_row_are_trimmed(self) -> None:
        rows = self._video_traffic("v-1", start_date="2024-01-01", end_date="2024-06-01")
        self.assertEqual(max(r["date"] for r in rows), "2024-03-15")

    def test_rows_carry_only_the_response_fields(self) -> None:
        rows = self._video_traffic("v-1", start_date="2024-01-01", end_date="2024-01-02")
        self.assertEqual({tuple(r) for r in rows}, {("date", "traffic_source_type", "views", "watch_time_minutes")})
        self.assertEqual([(r["date"], r["traffic_source_type"]) for r in rows], [
            ("2024-01-01", "SEARCH"), ("2024-01-01", "SUGGESTED"),
        ])

    def test_aggregated_source_types_are_those_observed_in_the_filtered_result(self) -> None:
        rows = _traffic_source_totals(start_date="2024-03-01", end_date="2024-03-15")
        self.assertEqual({r["traffic_source_type"] for r in rows}, {"SEARCH"})

    def test_synthetic_zero_rows_do_not_change_real_totals(self) -> None:
        rows = self._video_traffic("v-1", start_date="2024-01-01", end_date="2024-03-15")
        self.assertEqual(sum(r["views"] for r in rows), 30 + 20 + 5)
        self.assertEqual(sum(r["watch_time_minutes"] for r in rows), 10 + 5 + 2)


class FxRatesTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write(make_fx_rate("2024-01-01", 1.30))
        writer.write(make_fx_rate("2024-01-15", 1.35))
        writer.write(make_fx_rate("2024-02-01", 1.40))

    def test_range_filter_is_inclusive(self) -> None:
        rows = reader.select(
            FxRate, ("date", "usd_to_sgd"),
            where=[("date", ">=", "2024-01-01"), ("date", "<=", "2024-01-15")], order_by=("date",),
        )
        self.assertEqual([r.date for r in rows], ["2024-01-01", "2024-01-15"])

    def test_last_fx_rate_is_the_latest_date(self) -> None:
        latest = reader.select_one(FxRate, ("date", "usd_to_sgd"), order_by=("-date",))
        assert latest is not None
        self.assertEqual(latest.date, "2024-02-01")

    def test_empty_table_returns_none(self) -> None:
        with database.get_connection() as conn:
            conn.execute("DELETE FROM fx_rates")
        self.assertIsNone(reader.select_one(FxRate, ("date", "usd_to_sgd"), order_by=("-date",)))


class TopVideosOrderingTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write(make_video("v-1", "Alpha"))
        writer.write(make_video("v-2", "Beta"))
        writer.write(make_video("v-3", "Gamma"))
        # v-1 and v-2 tie on views to prove the deterministic id tie-breaker.
        writer.write(make_video_analytics("v-1", "2024-01-01", views=100, watch_time_minutes=5))
        writer.write(make_video_analytics("v-2", "2024-01-01", views=100, watch_time_minutes=50))
        writer.write(make_video_analytics("v-3", "2024-01-01", views=50, watch_time_minutes=10))

    def test_orders_by_views_descending_by_default(self) -> None:
        ids = _top_video_ids(start_date="2024-01-01", end_date="2024-01-01")
        self.assertEqual(ids[:2], ["v-1", "v-2"])
        self.assertEqual(ids[-1], "v-3")

    def test_tied_views_break_ties_by_ascending_id(self) -> None:
        ids = _top_video_ids(start_date="2024-01-01", end_date="2024-01-01")
        tied = [video_id for video_id in ids if video_id in ("v-1", "v-2")]
        self.assertEqual(tied, ["v-1", "v-2"])

    def test_watch_time_sort_reorders_by_watch_time(self) -> None:
        ids = _top_video_ids(start_date="2024-01-01", end_date="2024-01-01", sort_by="watch_time")
        self.assertEqual(ids[0], "v-2")

    def test_limit_truncates_results(self) -> None:
        ids = _top_video_ids(start_date="2024-01-01", end_date="2024-01-01", limit=1)
        self.assertEqual(len(ids), 1)


if __name__ == "__main__":
    unittest.main()
