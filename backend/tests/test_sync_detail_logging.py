from __future__ import annotations

import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Optional
from unittest import mock

import pandas as pd
from googleapiclient.errors import HttpError

from logging_config import configure_logging, reset_logging
from sync import stages
from sync.stages import SyncCounts
from youtube import analytics_api, data_api

# Every test in this module logs through the real `youtube_analytics.sync` logger.
# Redirect it to a disposable directory for the whole module so the suite never appends
# to a developer's real `backend/data/*.log`, then restore the default configuration
# (closing the temp-path handlers first, so Windows does not keep the files locked
# before the directory is removed).
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


def _http_error(status: int, body: bytes) -> HttpError:
    """Build an HttpError carrying only the attributes `_analytics_query` reads.

    `resp.reason` is required by `HttpError.__init__` itself (unrelated to anything
    `_analytics_query` inspects), so a placeholder value is supplied here.
    """
    return HttpError(resp=SimpleNamespace(status=status, reason="error"), content=body)


class DataApiPaginationLoggingTest(unittest.TestCase):
    """Exercises the four `data_api.py` token-pagination loops with mocked multi-page
    responses; asserts one ordered DEBUG record per page and no paired before/after
    records, with the raw pagination token never appearing in a logged message."""

    def test_fetch_shorts_video_ids_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "s1"}}], "nextPageToken": "SECRET_TOKEN_1"},
            {"items": [{"contentDetails": {"videoId": "s2"}}, {"contentDetails": {"videoId": "s3"}}]},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result = data_api.fetch_shorts_video_ids("UUxxxxxxxxxxxxxxxxxxxx")

        self.assertEqual(result, {"s1", "s2", "s3"})
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages,
            [
                "shorts_video_ids page=1 items=1 playlist=UUSHxxxxxxxxxxxxxxxxxxxx",
                "shorts_video_ids page=2 items=2 playlist=UUSHxxxxxxxxxxxxxxxxxxxx",
            ],
        )
        self.assertNotIn("SECRET_TOKEN_1", " ".join(messages))

    def test_fetch_all_video_ids_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "v1"}}], "nextPageToken": "SECRET_TOKEN_2"},
            {"items": [{"contentDetails": {"videoId": "v2"}}]},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result = data_api.fetch_all_video_ids("UUuploadsplaylist")

        self.assertEqual(result, ["v1", "v2"])
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages,
            [
                "video_ids page=1 items=1 playlist=UUuploadsplaylist",
                "video_ids page=2 items=1 playlist=UUuploadsplaylist",
            ],
        )
        self.assertNotIn("SECRET_TOKEN_2", " ".join(messages))

    def test_fetch_playlists_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlists.return_value.list.return_value.execute.side_effect = [
            {
                "items": [{"id": "p1", "snippet": {"title": "sentinel title"}, "contentDetails": {}}],
                "nextPageToken": "SECRET_TOKEN_3",
            },
            {"items": []},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                data_api.fetch_playlists()

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["playlists page=1 items=1", "playlists page=2 items=0"])
        self.assertNotIn("sentinel title", " ".join(messages))
        self.assertNotIn("SECRET_TOKEN_3", " ".join(messages))

    def test_fetch_playlist_items_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {
                "items": [{"id": "i1", "snippet": {"resourceId": {"videoId": "v1"}, "position": 0}}],
                "nextPageToken": "SECRET_TOKEN_4",
            },
            {"items": [{"id": "i2", "snippet": {"resourceId": {"videoId": "v2"}, "position": 1}}]},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                data_api.fetch_playlist_items("PL123")

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages,
            ["playlist_items page=1 items=1 playlist=PL123", "playlist_items page=2 items=1 playlist=PL123"],
        )
        self.assertNotIn("SECRET_TOKEN_4", " ".join(messages))


class AnalyticsRetryLoggingTest(unittest.TestCase):
    """Exercises `_analytics_query`'s retry branch with `time.sleep` mocked."""

    def test_server_error_retry_is_logged_and_classified_as_server(self) -> None:
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = [
            _http_error(500, b"sentinel response body SENTINEL_BODY_TEXT"),
            {"rows": [], "columnHeaders": []},
        ]

        with mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result = analytics_api._analytics_query(service, {"startIndex": 1})

        self.assertEqual(result, {"rows": [], "columnHeaders": []})
        sleep_mock.assert_called_once_with(1)
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["analytics_query retry attempt=1 status=500 reason=server delay=1"])
        self.assertNotIn("SENTINEL_BODY_TEXT", messages[0])

    def test_quota_error_retry_is_logged_and_classified_as_quota(self) -> None:
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = [
            _http_error(403, b'{"error": {"errors": [{"reason": "quotaExceeded"}]}, "access_token": "FAKE"}'),
            {"rows": [], "columnHeaders": []},
        ]

        with mock.patch("youtube.analytics_api.time.sleep"):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                analytics_api._analytics_query(service, {"startIndex": 1})

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["analytics_query retry attempt=1 status=403 reason=quota delay=1"])
        self.assertNotIn("FAKE", messages[0])
        self.assertNotIn("quotaExceeded", messages[0])


class VideoAnalyticsStageDetailLoggingTest(unittest.TestCase):
    """Exercises `sync_video_analytics()`'s per-video processed/skipped records with
    external calls mocked; counts and call sequences must stay unchanged."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.set_message").start()

    def test_video_skipped_without_publish_date(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_video", return_value={"published_at": None}).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_analytics("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_analytics 1/1 video=v1 skipped reason=no_publish_date"])
        self.assertEqual(counts.rows_fetched, 0)

    def test_video_skipped_when_range_is_empty(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_video", return_value={"published_at": "2999-01-01T00:00:00Z"}
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_analytics("all", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_analytics 1/1 video=v1 skipped reason=empty_range"])
        self.assertEqual(counts.rows_fetched, 0)

    def test_video_processed_logs_its_own_row_count_only(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_video", return_value={"published_at": "2020-01-01T00:00:00Z"}
        ).start()
        mock.patch("sync.stages.database.get_last_analytics_date", return_value=None).start()
        upsert_mock = mock.patch("sync.stages.database.upsert_video_analytics").start()
        rows = [{"video_id": "v1", "date": "2020-01-01"}, {"video_id": "v1", "date": "2020-01-02"}]
        mock.patch("sync.stages.youtube.iter_video_analytics", return_value=iter(rows)).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_analytics("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_analytics 1/1 video=v1 rows=2"])
        self.assertEqual(counts.rows_fetched, 2)
        self.assertEqual(counts.rows_written, 2)
        self.assertEqual(upsert_mock.call_count, 2)

    def test_no_record_per_row_only_one_per_video(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_video", return_value={"published_at": "2020-01-01T00:00:00Z"}
        ).start()
        mock.patch("sync.stages.database.get_last_analytics_date", return_value=None).start()
        mock.patch("sync.stages.database.upsert_video_analytics").start()
        rows = [{"video_id": "v1", "date": f"2020-01-{i:02d}"} for i in range(1, 11)]
        mock.patch("sync.stages.youtube.iter_video_analytics", return_value=iter(rows)).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_analytics("incremental", None, counts)

        self.assertEqual(len(captured.records), 1)


class VideoTrafficSourcesStageDetailLoggingTest(unittest.TestCase):
    """Mirrors `VideoAnalyticsStageDetailLoggingTest` for `sync_video_traffic_sources()`."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.set_message").start()

    def test_video_skipped_without_publish_date(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_video", return_value={"published_at": None}).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_traffic_sources("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_traffic_sources 1/1 video=v1 skipped reason=no_publish_date"])

    def test_video_skipped_when_range_is_empty(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_video", return_value={"published_at": "2999-01-01T00:00:00Z"}
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_traffic_sources("all", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_traffic_sources 1/1 video=v1 skipped reason=empty_range"])

    def test_video_processed_logs_its_own_row_count_only(self) -> None:
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_video", return_value={"published_at": "2020-01-01T00:00:00Z"}
        ).start()
        mock.patch("sync.stages.database.get_last_traffic_source_date", return_value=None).start()
        upsert_mock = mock.patch("sync.stages.database.upsert_video_traffic_source").start()
        rows = [{"video_id": "v1", "date": "2020-01-01", "traffic_source_type": "YT_SEARCH"}]
        mock.patch("sync.stages.youtube.iter_video_traffic_sources", return_value=iter(rows)).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_traffic_sources("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_traffic_sources 1/1 video=v1 rows=1"])
        self.assertEqual(counts.rows_fetched, 1)
        self.assertEqual(upsert_mock.call_count, 1)


class FxRatesDetailLoggingTest(unittest.TestCase):
    """Exercises `sync_fx_rates()`'s no-work and download paths."""

    def test_no_work_condition_logs_one_record(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        last_row = {"date": yesterday.isoformat(), "usd_to_sgd": 1.35}

        with mock.patch("sync.stages.database.get_last_fx_rate", return_value=last_row):
            counts = SyncCounts()
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                stages.sync_fx_rates(counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith("fx_rates start="))
        self.assertIn("no_work=true", messages[0])

    def test_download_path_logs_days_written(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        last_date = yesterday - timedelta(days=2)
        last_row = {"date": last_date.isoformat(), "usd_to_sgd": 1.30}
        day1 = last_date + timedelta(days=1)
        day2 = yesterday
        df = pd.DataFrame(
            {"Close": [1.31, 1.32]},
            index=pd.to_datetime([day1.isoformat(), day2.isoformat()]),
        )

        with mock.patch("sync.stages.database.get_last_fx_rate", return_value=last_row), \
                mock.patch("sync.stages.database.upsert_fx_rate") as upsert_mock, \
                mock.patch("yfinance.download", return_value=df):
            counts = SyncCounts()
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                stages.sync_fx_rates(counts)

        self.assertEqual(upsert_mock.call_count, 2)
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(len(messages), 1)
        self.assertIn("days_written=2", messages[0])
        self.assertTrue(messages[0].startswith("fx_rates start="))


if __name__ == "__main__":
    unittest.main()
