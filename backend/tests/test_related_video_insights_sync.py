from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

from googleapiclient.errors import HttpError

from sync import stages
from sync.monthly_insights import MonthlyWindow, weekly_sub_windows
from sync.stages import SyncCounts
from youtube import analytics_api


def _http_error(status: int, body: bytes) -> HttpError:
    """Build an HttpError carrying only the attributes `_analytics_query` reads."""
    return HttpError(resp=SimpleNamespace(status=status, reason="error"), content=body)


def _weekly_calls(video_id: str, *month_windows: MonthlyWindow) -> set[tuple[str, str, str]]:
    """Expand MonthlyWindows into the (video_id, start, end) weekly sub-calls
    sync_related_video_insights actually issues for them."""
    return {
        (video_id, start, end)
        for window in month_windows
        for start, end in weekly_sub_windows(window)
    }


class FetchVideoRelatedVideosTest(unittest.TestCase):
    _HEADERS = [{"name": "insightTrafficSourceDetail"}, {"name": "views"}]

    def _service(self, responses: list[dict | Exception]) -> mock.Mock:
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = responses
        return service

    def test_sends_exact_query_kwargs_with_no_start_index(self) -> None:
        service = self._service([{"rows": [], "columnHeaders": []}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

        kwargs = service.reports.return_value.query.call_args.kwargs
        self.assertEqual(
            kwargs,
            {
                "ids": "channel==MINE",
                "startDate": "2024-03-01",
                "endDate": "2024-03-07",
                "dimensions": "insightTrafficSourceDetail",
                "metrics": "views",
                "filters": "video==v1;insightTrafficSourceType==RELATED_VIDEO",
                "sort": "-views",
                "maxResults": 25,
            },
        )
        self.assertNotIn("startIndex", kwargs)

    def test_exactly_25_rows_makes_only_one_query(self) -> None:
        rows = [[f"ref{i}", 1] for i in range(25)]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

        self.assertEqual(service.reports.return_value.query.call_count, 1)
        self.assertEqual(result.raw_row_count, 25)
        self.assertEqual(len(result.referrers), 25)

    def test_empty_rows_list_is_a_valid_empty_response(self) -> None:
        service = self._service([{"rows": [], "columnHeaders": []}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")
        self.assertEqual(result.raw_row_count, 0)
        self.assertEqual(result.referrers, [])

    def test_missing_rows_key_is_a_valid_empty_response(self) -> None:
        service = self._service([{}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")
        self.assertEqual(result.raw_row_count, 0)
        self.assertEqual(result.referrers, [])

    def test_zero_and_negative_view_rows_count_toward_raw_count_but_not_referrers(self) -> None:
        rows = [["ref-a", 5], ["ref-b", 0], ["ref-c", -1]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")
        self.assertEqual(result.raw_row_count, 3)
        self.assertEqual(result.referrers, [{"referrer_video_id": "ref-a", "views": 5}])

    def test_more_than_25_rows_raises_instead_of_succeeding(self) -> None:
        rows = [[f"ref{i}", 1] for i in range(26)]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

    def test_missing_expected_headers_raises(self) -> None:
        rows = [["ref-a", 5]]
        service = self._service([{"rows": rows, "columnHeaders": [{"name": "day"}, {"name": "views"}]}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

    def test_reordered_headers_are_read_by_name_not_position(self) -> None:
        rows = [[7, "ref-a"]]
        headers = [{"name": "views"}, {"name": "insightTrafficSourceDetail"}]
        service = self._service([{"rows": rows, "columnHeaders": headers}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            result = analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")
        self.assertEqual(result.referrers, [{"referrer_video_id": "ref-a", "views": 7}])

    def test_malformed_row_shape_raises(self) -> None:
        rows = [["ref-a"]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

    def test_non_string_referrer_id_raises(self) -> None:
        rows = [[12345, 5]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

    def test_non_integer_views_value_raises(self) -> None:
        rows = [["ref-a", "5"]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

    def test_boolean_views_value_raises(self) -> None:
        rows = [["ref-a", True]]
        service = self._service([{"rows": rows, "columnHeaders": self._HEADERS}])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

    def test_retry_reuses_identical_query_parameters(self) -> None:
        service = self._service([
            _http_error(500, b"server error"),
            {"rows": [["ref-a", 5]], "columnHeaders": self._HEADERS},
        ])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service), \
                mock.patch("youtube.analytics_api.time.sleep"):
            result = analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")

        calls = service.reports.return_value.query.call_args_list
        self.assertEqual(calls[0].kwargs, calls[1].kwargs)
        self.assertEqual(result.referrers, [{"referrer_video_id": "ref-a", "views": 5}])

    def test_nonretryable_error_raises_immediately(self) -> None:
        service = self._service([_http_error(400, b"bad request")])
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service), \
                mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")
        sleep_mock.assert_not_called()

    def test_exhausted_retries_raise(self) -> None:
        service = self._service([_http_error(500, b"server error")] * 5)
        with mock.patch("youtube.analytics_api._analytics_client", return_value=service), \
                mock.patch("youtube.analytics_api.time.sleep"):
            with self.assertRaises(RuntimeError):
                analytics_api.fetch_video_related_videos("v1", "2024-03-01", "2024-03-07")


class SyncRelatedVideoInsightsStageTest(unittest.TestCase):
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
        mock.patch("sync.stages.database.get_last_related_videos_month", return_value="2024-01").start()
        # Metadata resolution is exercised by its own test class; keep it a no-op here.
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        self.fetch_channel_identity = mock.patch(
            "sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")
        ).start()

    def test_windows_are_captured_once_for_the_whole_stage(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1", "v2"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        self.windows_mock.assert_called_once()

    def test_no_targets_makes_no_fetch_calls(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        fetch = mock.patch("sync.stages.youtube.fetch_video_related_videos").start()
        counts = SyncCounts()

        stages.sync_related_video_insights("incremental", None, counts)

        fetch.assert_not_called()
        self.assertEqual(counts.rows_fetched, 0)
        self.assertEqual(counts.rows_written, 0)

    def test_every_video_window_combination_is_requested(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1", "v2"]).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        calls = {(c.args[0], c.args[1], c.args[2]) for c in fetch.call_args_list}
        self.assertEqual(
            calls,
            _weekly_calls("v1", *self.windows) | _weekly_calls("v2", *self.windows),
        )

    def test_never_reads_traffic_source_data(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        traffic = mock.patch("sync.stages.database.get_video_traffic_sources").start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        traffic.assert_not_called()

    def test_counts_accumulate_across_videos_and_windows(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(
                raw_row_count=3, referrers=[{"referrer_video_id": "ref-1", "views": 5}]
            ),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=1).start()
        counts = SyncCounts()

        stages.sync_related_video_insights("incremental", None, counts)

        weekly_call_count = len(_weekly_calls("v1", *self.windows))
        self.assertEqual(counts.rows_fetched, 3 * weekly_call_count)
        # One upsert per month (weekly results are combined first), not one per weekly call.
        self.assertEqual(counts.rows_written, len(self.windows))

    def test_same_referrer_across_weekly_calls_within_a_month_sums_not_overwrites(self) -> None:
        # Only mock the March window (2 weekly calls) so the assertion below stays exact.
        self.windows_mock.return_value = [MonthlyWindow("2024-03", "2024-03-01", "2024-03-14")]
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            side_effect=[
                analytics_api.RelatedVideosResult(raw_row_count=1, referrers=[{"referrer_video_id": "ref-1", "views": 5}]),
                analytics_api.RelatedVideosResult(raw_row_count=1, referrers=[{"referrer_video_id": "ref-1", "views": 3}]),
            ],
        ).start()
        upsert = mock.patch("sync.stages.database.upsert_related_videos", return_value=1).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        upsert.assert_called_once_with("v1", "2024-03", [{"referrer_video_id": "ref-1", "views": 8}])

    def test_a_failed_window_stops_the_stage_but_keeps_earlier_commits_and_partial_counts(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1", "v2"]).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=1).start()

        def fetch_side_effect(video_id: str, start: str, end: str) -> analytics_api.RelatedVideosResult:
            if video_id == "v2":
                raise RuntimeError("quota exceeded")
            return analytics_api.RelatedVideosResult(
                raw_row_count=1, referrers=[{"referrer_video_id": "ref-1", "views": 1}]
            )

        mock.patch("sync.stages.youtube.fetch_video_related_videos", side_effect=fetch_side_effect).start()
        counts = SyncCounts()

        with self.assertRaises(RuntimeError):
            stages.sync_related_video_insights("incremental", None, counts)

    def test_does_not_affect_search_insights_state(self) -> None:
        """A Related failure must never touch search_insights's checkpoint or state —
        the two stages share no code path beyond the generic weekly-windowing helper."""
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_related_videos", side_effect=RuntimeError("boom")
        ).start()
        search_upsert = mock.patch("sync.stages.database.upsert_search_terms").start()

        with self.assertRaises(RuntimeError):
            stages.sync_related_video_insights("incremental", None, SyncCounts())

        search_upsert.assert_not_called()


class SyncRelatedVideoInsightsScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.update_sync_progress").start()
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
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
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=0).start()

        stages.sync_related_video_insights("year", 2024, SyncCounts())

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
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=0).start()

        stages.sync_related_video_insights("all", None, SyncCounts())

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
        fetch = mock.patch("sync.stages.youtube.fetch_video_related_videos").start()

        stages.sync_related_video_insights("year", 2024, SyncCounts())
        stages.sync_related_video_insights("all", None, SyncCounts())

        fetch.assert_not_called()

    def test_incremental_scope_with_no_publish_date_uses_fixed_two_windows(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"title": "T"}).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=0).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

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
        mock.patch("sync.stages.database.get_last_related_videos_month", return_value=None).start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=0).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2024-01", "2024-01-20", "2024-01-31"),
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))

    def test_incremental_scope_collapses_to_fixed_two_windows_when_already_caught_up(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video",
            return_value={"title": "T", "published_at": "2020-01-01T00:00:00Z"},
        ).start()
        mock.patch("sync.stages.database.get_last_related_videos_month", return_value="2024-02").start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=0).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))

    def test_incremental_scope_closes_the_gap_left_by_an_interrupted_backfill(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video",
            return_value={"title": "T", "published_at": "2020-01-01T00:00:00Z"},
        ).start()
        mock.patch("sync.stages.database.get_last_related_videos_month", return_value="2023-11").start()
        fetch = mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=0).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        calls = {c.args[0:3] for c in fetch.call_args_list}
        expected_months = [
            MonthlyWindow("2023-11", "2023-11-01", "2023-11-30"),
            MonthlyWindow("2023-12", "2023-12-01", "2023-12-31"),
            MonthlyWindow("2024-01", "2024-01-01", "2024-01-31"),
            MonthlyWindow("2024-02", "2024-02-01", "2024-02-29"),
            MonthlyWindow("2024-03", "2024-03-01", "2024-03-14"),
        ]
        self.assertEqual(calls, _weekly_calls("v1", *expected_months))


class ResolveRelatedVideoMetadataTest(unittest.TestCase):
    """Unit tests for stages._resolve_related_video_metadata, isolated from the
    per-video/month/week fetch loop tested above."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)

    def test_no_new_ids_skips_channel_identity_and_fetch(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        identity = mock.patch("sync.stages.youtube.fetch_channel_identity").start()
        fetch = mock.patch("sync.stages.youtube.fetch_videos").start()

        stages._resolve_related_video_metadata({"v1"}, SyncCounts())

        identity.assert_not_called()
        fetch.assert_not_called()

    def test_a_channel_identity_failure_is_logged_and_does_not_raise(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch(
            "sync.stages.youtube.fetch_channel_identity", side_effect=RuntimeError("quota exceeded")
        ).start()
        fetch = mock.patch("sync.stages.youtube.fetch_videos").start()

        with self.assertLogs("youtube_analytics.sync", level="WARNING"):
            stages._resolve_related_video_metadata({"ref-1"}, SyncCounts())

        fetch.assert_not_called()

    def test_already_known_ids_are_excluded_from_resolution(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["ref-known"]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        fetch = mock.patch("sync.stages.youtube.fetch_videos", return_value=[]).start()

        stages._resolve_related_video_metadata({"ref-known", "ref-new"}, SyncCounts())

        fetch.assert_called_once_with(["ref-new"])

    def test_batches_of_more_than_50_are_split_deterministically(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        fetch = mock.patch("sync.stages.youtube.fetch_videos", return_value=[]).start()
        ids = {f"ref-{i:03d}" for i in range(75)}

        stages._resolve_related_video_metadata(ids, SyncCounts())

        self.assertEqual(fetch.call_count, 2)
        batches = [call.args[0] for call in fetch.call_args_list]
        self.assertEqual(len(batches[0]), 50)
        self.assertEqual(len(batches[1]), 25)
        self.assertEqual(batches[0], sorted(batches[0]))
        self.assertEqual(set(batches[0]) | set(batches[1]), ids)

    def test_owned_referrer_is_classified_true_on_channel_match(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "ref-mine", "channel_id": "UC1", "title": "Mine"}],
        ).start()
        upsert = mock.patch("sync.stages.database.upsert_related_video").start()

        stages._resolve_related_video_metadata({"ref-mine"}, SyncCounts())

        upsert.assert_called_once_with({"id": "ref-mine", "channel_id": "UC1", "title": "Mine"}, own=True)

    def test_external_referrer_is_classified_false_on_channel_mismatch(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "ref-ext", "channel_id": "UCother", "title": "Other"}],
        ).start()
        upsert = mock.patch("sync.stages.database.upsert_related_video").start()

        stages._resolve_related_video_metadata({"ref-ext"}, SyncCounts())

        upsert.assert_called_once_with({"id": "ref-ext", "channel_id": "UCother", "title": "Other"}, own=False)

    def test_id_omitted_from_the_response_gets_no_upsert_call(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        mock.patch("sync.stages.youtube.fetch_videos", return_value=[]).start()
        upsert = mock.patch("sync.stages.database.upsert_related_video").start()

        stages._resolve_related_video_metadata({"ref-unavailable"}, SyncCounts())

        upsert.assert_not_called()

    def test_a_batch_lookup_failure_is_logged_and_does_not_raise(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos", side_effect=RuntimeError("quota exceeded")
        ).start()
        upsert = mock.patch("sync.stages.database.upsert_related_video").start()

        with self.assertLogs("youtube_analytics.sync", level="WARNING"):
            stages._resolve_related_video_metadata({"ref-1"}, SyncCounts())

        upsert.assert_not_called()

    def test_a_failed_batch_does_not_stop_other_batches_from_resolving(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        first_batch = [f"ref-{i:03d}" for i in range(50)]
        second_batch = ["ref-zzz"]

        def fetch_side_effect(ids: list[str]) -> list[dict]:
            if ids == first_batch:
                raise RuntimeError("quota exceeded")
            return [{"id": "ref-zzz", "channel_id": "UCother", "title": "Other"}]

        mock.patch("sync.stages.youtube.fetch_videos", side_effect=fetch_side_effect).start()
        upsert = mock.patch("sync.stages.database.upsert_related_video").start()

        with self.assertLogs("youtube_analytics.sync", level="WARNING"):
            stages._resolve_related_video_metadata(set(first_batch) | set(second_batch), SyncCounts())

        upsert.assert_called_once_with({"id": "ref-zzz", "channel_id": "UCother", "title": "Other"}, own=False)

    def test_resolved_metadata_is_counted_in_stage_counters(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[
                {"id": "ref-1", "channel_id": "UC1", "title": "Mine"},
                {"id": "ref-2", "channel_id": "UCother", "title": "Other"},
            ],
        ).start()
        mock.patch("sync.stages.database.upsert_related_video").start()
        counts = SyncCounts()

        stages._resolve_related_video_metadata({"ref-1", "ref-2"}, counts)

        self.assertEqual(counts.rows_fetched, 2)
        self.assertEqual(counts.rows_written, 2)


class SyncRelatedVideoInsightsMetadataIntegrationTest(unittest.TestCase):
    """Confirms the full stage never treats a referrer resolved mid-run as a target in
    that same run, and that the worklist snapshot is captured exactly once."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.update_sync_progress").start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"title": "T"}).start()
        mock.patch("sync.stages.database.get_last_related_videos_month", return_value="2024-01").start()
        mock.patch(
            "sync.stages.monthly_insights.monthly_search_windows",
            return_value=[MonthlyWindow("2024-03", "2024-03-01", "2024-03-14")],
        ).start()

    def test_worklist_is_captured_once_and_metadata_never_becomes_a_target(self) -> None:
        owned_ids = mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(
                raw_row_count=1, referrers=[{"referrer_video_id": "v1", "views": 5}]
            ),
        ).start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=1).start()
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()
        mock.patch("sync.stages.youtube.fetch_videos", return_value=[]).start()

        stages.sync_related_video_insights("incremental", None, SyncCounts())

        # The referrer happens to equal the only target ID; get_owned_video_ids() being
        # called exactly once proves the worklist can't have picked it up mid-run.
        owned_ids.assert_called_once()


if __name__ == "__main__":
    unittest.main()
