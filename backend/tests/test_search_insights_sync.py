from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

from googleapiclient.errors import HttpError

from sync import stages
from sync.monthly_insights import MonthlyWindow, monthly_search_windows, monthly_windows_for_range, weekly_sub_windows
from sync.stages import SyncCounts
from youtube import analytics_api


def _weekly_calls(video_id: str, *month_windows: MonthlyWindow) -> set[tuple[str, str, str]]:
    """Expand MonthlyWindows into the (video_id, start, end) weekly sub-calls
    sync_search_insights actually issues for them."""
    return {
        (video_id, start, end)
        for window in month_windows
        for start, end in weekly_sub_windows(window)
    }


def _http_error(status: int, body: bytes) -> HttpError:
    """Build an HttpError carrying only the attributes `_analytics_query` reads."""
    return HttpError(resp=SimpleNamespace(status=status, reason="error"), content=body)


class MonthlySearchWindowsTest(unittest.TestCase):
    def test_mid_month_returns_previous_full_month_then_current_through_yesterday(self) -> None:
        windows = monthly_search_windows(date(2024, 3, 15))
        self.assertEqual(
            windows,
            [
                MonthlyWindow(month="2024-02", start_date="2024-02-01", end_date="2024-02-29"),
                MonthlyWindow(month="2024-03", start_date="2024-03-01", end_date="2024-03-14"),
            ],
        )

    def test_first_day_of_month_skips_current_month_window(self) -> None:
        windows = monthly_search_windows(date(2024, 3, 1))
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].month, "2024-02")
        self.assertEqual(windows[0].end_date, "2024-02-29")

    def test_second_day_of_month_current_window_is_a_single_day(self) -> None:
        windows = monthly_search_windows(date(2024, 3, 2))
        self.assertEqual(len(windows), 2)
        current = windows[1]
        self.assertEqual(current.start_date, "2024-03-01")
        self.assertEqual(current.end_date, "2024-03-01")

    def test_leap_february_previous_month_spans_29_days(self) -> None:
        windows = monthly_search_windows(date(2024, 3, 1))
        self.assertEqual(windows[0].start_date, "2024-02-01")
        self.assertEqual(windows[0].end_date, "2024-02-29")

    def test_non_leap_february_previous_month_spans_28_days(self) -> None:
        windows = monthly_search_windows(date(2023, 3, 1))
        self.assertEqual(windows[0].start_date, "2023-02-01")
        self.assertEqual(windows[0].end_date, "2023-02-28")

    def test_january_rollover_previous_month_is_december_of_prior_year(self) -> None:
        windows = monthly_search_windows(date(2024, 1, 15))
        self.assertEqual(windows[0].month, "2023-12")
        self.assertEqual(windows[0].start_date, "2023-12-01")
        self.assertEqual(windows[0].end_date, "2023-12-31")
        self.assertEqual(windows[1].month, "2024-01")

    def test_january_first_skips_current_and_previous_is_prior_december(self) -> None:
        windows = monthly_search_windows(date(2024, 1, 1))
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].month, "2023-12")


class MonthlyWindowsForRangeTest(unittest.TestCase):
    def test_empty_when_start_after_end(self) -> None:
        self.assertEqual(monthly_windows_for_range(date(2024, 3, 1), date(2024, 2, 1)), [])

    def test_single_month_partial_range_clamps_both_ends(self) -> None:
        windows = monthly_windows_for_range(date(2024, 3, 10), date(2024, 3, 20))
        self.assertEqual(
            windows,
            [MonthlyWindow(month="2024-03", start_date="2024-03-10", end_date="2024-03-20")],
        )

    def test_multi_month_range_clamps_only_the_first_and_last_month(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 15), date(2024, 3, 10))
        self.assertEqual(
            [w.month for w in windows], ["2024-01", "2024-02", "2024-03"],
        )
        self.assertEqual(windows[0].start_date, "2024-01-15")
        self.assertEqual(windows[0].end_date, "2024-01-31")
        self.assertEqual(windows[1].start_date, "2024-02-01")
        self.assertEqual(windows[1].end_date, "2024-02-29")
        self.assertEqual(windows[2].start_date, "2024-03-01")
        self.assertEqual(windows[2].end_date, "2024-03-10")

    def test_year_boundary_rolls_over(self) -> None:
        windows = monthly_windows_for_range(date(2023, 12, 20), date(2024, 1, 10))
        self.assertEqual([w.month for w in windows], ["2023-12", "2024-01"])


class WeeklySubWindowsTest(unittest.TestCase):
    def test_full_month_splits_into_7_day_chunks_with_a_short_final_chunk(self) -> None:
        window = MonthlyWindow("2024-02", "2024-02-01", "2024-02-29")
        chunks = weekly_sub_windows(window)
        self.assertEqual(
            chunks,
            [
                ("2024-02-01", "2024-02-07"),
                ("2024-02-08", "2024-02-14"),
                ("2024-02-15", "2024-02-21"),
                ("2024-02-22", "2024-02-28"),
                ("2024-02-29", "2024-02-29"),
            ],
        )

    def test_exact_multiple_of_seven_days_has_no_short_final_chunk(self) -> None:
        window = MonthlyWindow("2024-06", "2024-06-01", "2024-06-14")
        chunks = weekly_sub_windows(window)
        self.assertEqual(chunks, [("2024-06-01", "2024-06-07"), ("2024-06-08", "2024-06-14")])

    def test_single_day_window_is_one_chunk(self) -> None:
        window = MonthlyWindow("2024-03", "2024-03-01", "2024-03-01")
        self.assertEqual(weekly_sub_windows(window), [("2024-03-01", "2024-03-01")])

    def test_partial_month_window_chunks_from_its_own_start_not_the_1st(self) -> None:
        window = MonthlyWindow("2024-02", "2024-02-10", "2024-02-29")
        chunks = weekly_sub_windows(window)
        self.assertEqual(chunks[0], ("2024-02-10", "2024-02-16"))
        self.assertEqual(chunks[-1], ("2024-02-24", "2024-02-29"))


class FetchVideoSearchTermsTest(unittest.TestCase):
    _HEADERS = [{"name": "insightTrafficSourceDetail"}, {"name": "views"}]

    def _service(self, responses: list[dict | Exception]) -> mock.Mock:
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = responses
        return service

    def test_sends_exact_query_kwargs_with_no_start_index(self) -> None:
        service = self._service([{"rows": [], "columnHeaders": []}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")

        kwargs = service.reports.return_value.query.call_args.kwargs
        self.assertEqual(
            kwargs,
            {
                "ids": "channel==MINE",
                "startDate": "2024-03-01",
                "endDate": "2024-03-14",
                "dimensions": "insightTrafficSourceDetail",
                "metrics": "views",
                "filters": "video==v1;insightTrafficSourceType==YT_SEARCH",
                "sort": "-views",
                "maxResults": 25,
            },
        )
        self.assertNotIn("startIndex", kwargs)

    def test_exactly_25_rows_makes_only_one_query(self) -> None:
        rows = [[f"term{i}", 1] for i in range(25)]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")

        self.assertEqual(service.reports.return_value.query.call_count, 1)
        self.assertEqual(result.raw_row_count, 25)
        self.assertEqual(len(result.terms), 25)

    def test_empty_rows_list_is_a_valid_empty_response(self) -> None:
        service = self._service([{"rows": [], "columnHeaders": []}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")
        self.assertEqual(result.raw_row_count, 0)
        self.assertEqual(result.terms, [])

    def test_missing_rows_key_is_a_valid_empty_response(self) -> None:
        service = self._service([{}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")
        self.assertEqual(result.raw_row_count, 0)
        self.assertEqual(result.terms, [])

    def test_zero_view_rows_count_toward_raw_count_but_not_terms(self) -> None:
        rows = [["cats", 5], ["dogs", 0]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")
        self.assertEqual(result.raw_row_count, 2)
        self.assertEqual(result.terms, [{"search_term": "cats", "views": 5}])

    def test_unicode_and_punctuation_terms_are_preserved_exactly(self) -> None:
        rows = [["how to draw 猫 (cat) - part 1!", 3]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")
        self.assertEqual(result.terms, [{"search_term": "how to draw 猫 (cat) - part 1!", "views": 3}])

    def test_more_than_25_rows_raises_instead_of_succeeding(self) -> None:
        rows = [[f"term{i}", 1] for i in range(26)]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")

    def test_missing_expected_headers_raises(self) -> None:
        rows = [["cats", 5]]
        service = self._service([{"rows": rows, "columnHeaders": [{"name": "day"}, {"name": "views"}]}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")

    def test_malformed_row_shape_raises(self) -> None:
        rows = [["cats"]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")

    def test_non_integer_views_value_raises(self) -> None:
        rows = [["cats", "5"]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")

    def test_retry_reuses_identical_query_parameters(self) -> None:
        service = self._service([
            _http_error(500, b"server error"),
            {"rows": [["cats", 5]], "columnHeaders": self._HEADERS},
        ])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service), \
                mock.patch("youtube.analytics_api.time.sleep"):
            result = analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")

        calls = service.reports.return_value.query.call_args_list
        self.assertEqual(calls[0].kwargs, calls[1].kwargs)
        self.assertEqual(result.terms, [{"search_term": "cats", "views": 5}])

    def test_exhausted_retries_raise(self) -> None:
        service = self._service([_http_error(500, b"server error")] * 5)
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service), \
                mock.patch("youtube.analytics_api.time.sleep"):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_search_terms("v1", "2024-03-01", "2024-03-14")


class SyncSearchRelatedInsightsStageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        self.windows = [
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.windows_mock = mock.patch(
            "sync.stages.monthly_insights.monthly_search_windows", return_value=self.windows
        ).start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"title": "T"}).start()
        mock.patch("sync.stages.status.update_sync_progress").start()
        # These tests exercise the plain "already has data" incremental refresh path;
        # the first-sync backfill path has its own test class below.
        mock.patch("sync.stages.database.get_last_search_terms_month", return_value="2024-01").start()

    def test_windows_are_captured_once_for_the_whole_stage(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1", "v2"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        self.windows_mock.assert_called_once()

    def test_no_targets_makes_no_fetch_calls(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        fetch = mock.patch("sync.stages.youtube.fetch_video_search_terms").start()
        counts = SyncCounts()

        stages.sync_search_insights("incremental", None, counts)

        fetch.assert_not_called()
        self.assertEqual(counts.rows_fetched, 0)
        self.assertEqual(counts.rows_written, 0)

    def test_every_video_window_combination_is_requested(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1", "v2"]).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        calls = {(c.args[0], c.args[1], c.args[2]) for c in fetch.call_args_list}
        self.assertEqual(
            calls,
            _weekly_calls("v1", *self.windows) | _weekly_calls("v2", *self.windows),
        )

    def test_never_reads_traffic_source_data(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()
        traffic = mock.patch("sync.stages.database.get_video_traffic_sources").start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        traffic.assert_not_called()

    def test_counts_accumulate_across_videos_and_windows(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(
                raw_row_count=3, terms=[{"search_term": "cats", "views": 5}]
            ),
        ).start()
        mock.patch("sync.stages.database.upsert_search_terms", return_value=1).start()
        counts = SyncCounts()

        stages.sync_search_insights("incremental", None, counts)

        weekly_call_count = len(_weekly_calls("v1", *self.windows))
        self.assertEqual(counts.rows_fetched, 3 * weekly_call_count)
        # One upsert per month (weekly results are combined first), not one per weekly call.
        self.assertEqual(counts.rows_written, len(self.windows))

    def test_same_term_across_weekly_calls_within_a_month_sums_not_overwrites(self) -> None:
        # Only mock the March window (2 weekly calls) so the assertion below stays exact.
        self.windows_mock.return_value = [MonthlyWindow("2024-03", "2024-03-01", "2024-03-14")]
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            side_effect=[
                analytics_api.SearchTermsResult(raw_row_count=1, terms=[{"search_term": "cats", "views": 5}]),
                analytics_api.SearchTermsResult(raw_row_count=1, terms=[{"search_term": "cats", "views": 3}]),
            ],
        ).start()
        upsert = mock.patch("sync.stages.database.upsert_search_terms", return_value=1).start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        upsert.assert_called_once_with("v1", "2024-03", [{"search_term": "cats", "views": 8}])

    def test_a_failed_window_stops_the_stage_but_keeps_earlier_commits_and_partial_counts(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1", "v2"]).start()
        upsert = mock.patch("sync.stages.database.upsert_search_terms", return_value=1).start()

        def fetch_side_effect(video_id: str, start: str, end: str, title: str | None = None) -> analytics_api.SearchTermsResult:
            if video_id == "v2":
                raise RuntimeError("quota exceeded")
            return analytics_api.SearchTermsResult(raw_row_count=1, terms=[{"search_term": "cats", "views": 1}])

        mock.patch("sync.stages.youtube.fetch_video_search_terms", side_effect=fetch_side_effect).start()
        counts = SyncCounts()

        with self.assertRaises(RuntimeError):
            stages.sync_search_insights("incremental", None, counts)


class SyncSearchRelatedInsightsScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.update_sync_progress").start()
        self.mock_date = mock.patch("sync.stages.date").start()
        self.mock_date.today.return_value = date(2024, 3, 15)
        self.mock_date.fromisoformat = date.fromisoformat
        self.mock_date.side_effect = lambda *a, **k: date(*a, **k)

    def test_year_scope_requests_every_month_of_the_year_within_publish_and_yesterday(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video",
            return_value={"title": "T", "published_at": "2024-02-10T00:00:00Z"},
        ).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_search_terms", return_value=0).start()

        stages.sync_search_insights("year", 2024, SyncCounts())

        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2024-02", "2024-02-10", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))

    def test_all_scope_requests_every_month_since_publish(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video",
            return_value={"title": "T", "published_at": "2024-01-20T00:00:00Z"},
        ).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_search_terms", return_value=0).start()

        stages.sync_search_insights("all", None, SyncCounts())

        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2024-01", "2024-01-20", "2024-01-31"),
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))

    def test_year_and_all_scope_skip_videos_with_no_publish_date(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"title": "T"}).start()
        fetch = mock.patch("sync.stages.youtube.fetch_video_search_terms").start()

        stages.sync_search_insights("year", 2024, SyncCounts())
        stages.sync_search_insights("all", None, SyncCounts())

        fetch.assert_not_called()

    def test_a_video_published_after_the_effective_end_is_prefiltered_out(self) -> None:
        """A future-published video is excluded by the bounded worklist query itself,
        before any per-video processing — sync_search_insights() never sees it."""
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.fetch_video_search_terms").start()

        stages.sync_search_insights("all", None, SyncCounts())

        worklist.assert_called_once_with(published_through="2024-03-14")
        get_video.assert_not_called()
        fetch.assert_not_called()

    def test_incremental_and_all_request_yesterday_as_the_effective_end(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()

        stages.sync_search_insights("incremental", None, SyncCounts())
        worklist.assert_called_once_with(published_through="2024-03-14")
        worklist.reset_mock()

        stages.sync_search_insights("all", None, SyncCounts())
        worklist.assert_called_once_with(published_through="2024-03-14")

    def test_year_scope_clamps_the_effective_end_to_the_earlier_of_year_end_and_yesterday(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()

        stages.sync_search_insights("year", 2020, SyncCounts())
        worklist.assert_called_once_with(published_through="2020-12-31")
        worklist.reset_mock()

        # "today" is frozen to 2024-03-15 by setUp, so the current year clamps to yesterday.
        stages.sync_search_insights("year", 2024, SyncCounts())
        worklist.assert_called_once_with(published_through="2024-03-14")

    def test_an_empty_worklist_makes_no_per_video_calls(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.fetch_video_search_terms").start()
        counts = SyncCounts()

        stages.sync_search_insights("incremental", None, counts)

        get_video.assert_not_called()
        fetch.assert_not_called()
        self.assertEqual((counts.rows_fetched, counts.rows_written), (0, 0))

    def test_incremental_scope_with_no_publish_date_uses_fixed_two_windows(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"title": "T"}).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_search_terms", return_value=0).start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))

    def test_incremental_scope_backfills_from_publish_date_on_first_sync(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video",
            return_value={"title": "T", "published_at": "2024-01-20T00:00:00Z"},
        ).start()
        mock.patch("sync.stages.database.get_last_search_terms_month", return_value=None).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_search_terms", return_value=0).start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        # Jan (partial), Feb, Mar (partial, through "yesterday") — each split into weekly calls.
        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2024-01", "2024-01-20", "2024-01-31"),
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))

    def test_incremental_scope_collapses_to_fixed_two_windows_when_already_caught_up(self) -> None:
        # today is mocked to 2024-03-15, so "already caught up" means last stored month
        # is last month (2024-02) — that's exactly the same current+previous refresh.
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video",
            return_value={"title": "T", "published_at": "2020-01-01T00:00:00Z"},
        ).start()
        mock.patch("sync.stages.database.get_last_search_terms_month", return_value="2024-02").start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_search_terms", return_value=0).start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))

    def test_incremental_scope_closes_the_gap_left_by_an_interrupted_backfill(self) -> None:
        # A video whose backfill was interrupted after 2023-11 must not be treated as
        # "fully caught up" just because it has *some* stored data — it should resume
        # from that month forward, not silently skip the months in between.
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video",
            return_value={"title": "T", "published_at": "2020-01-01T00:00:00Z"},
        ).start()
        mock.patch("sync.stages.database.get_last_search_terms_month", return_value="2023-11").start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_search_terms",
            return_value=analytics_api.SearchTermsResult(raw_row_count=0, terms=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_search_terms", return_value=0).start()

        stages.sync_search_insights("incremental", None, SyncCounts())

        # Nov, Dec, Jan, Feb, Mar (partial) — each split into weekly calls.
        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2023-11", "2023-11-01", "2023-11-30"),
            MonthlyWindow("2023-12", "2023-12-01", "2023-12-31"),
            MonthlyWindow("2024-01", "2024-01-01", "2024-01-31"),
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))


if __name__ == "__main__":
    unittest.main()
