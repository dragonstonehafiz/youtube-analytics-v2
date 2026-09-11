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
from sync.monthly_insights import MonthlyWindow
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
    responses; asserts one ordered record per page, no paired before/after records, and
    that each record carries the owning entity's name and the page's `nextPageToken`.
    The token is an opaque result-set cursor, not a credential, and is logged so a
    repeating token can be told apart from fresh tokens walking an empty region."""

    def test_fetch_shorts_video_ids_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "s1"}}], "nextPageToken": "TOKEN_1"},
            {"items": [{"contentDetails": {"videoId": "s2"}}, {"contentDetails": {"videoId": "s3"}}]},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result, truncated = data_api.fetch_shorts_video_ids("UUxxxxxxxxxxxxxxxxxxxx")

        self.assertEqual(result, {"s1", "s2", "s3"})
        self.assertFalse(truncated)
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages,
            [
                "shorts_video_ids page=1 items=1 owner=UUSHxxxxxxxxxxxxxxxxxxxx "
                "next_page_token=TOKEN_1 owner_name='Shorts'",
                "shorts_video_ids page=2 items=2 owner=UUSHxxxxxxxxxxxxxxxxxxxx owner_name='Shorts'",
            ],
        )

    def test_fetch_all_video_ids_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "v1"}}], "nextPageToken": "TOKEN_2"},
            {"items": [{"contentDetails": {"videoId": "v2"}}]},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result, truncated = data_api.fetch_all_video_ids("UUuploadsplaylist")

        self.assertEqual(result, ["v1", "v2"])
        self.assertFalse(truncated)
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages,
            [
                "video_ids page=1 items=1 owner=UUuploadsplaylist "
                "next_page_token=TOKEN_2 owner_name='Uploads'",
                "video_ids page=2 items=1 owner=UUuploadsplaylist owner_name='Uploads'",
            ],
        )

    def test_fetch_playlists_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlists.return_value.list.return_value.execute.side_effect = [
            {
                "items": [{"id": "p1", "snippet": {"title": "sentinel title"}, "contentDetails": {}}],
                "nextPageToken": "TOKEN_3",
            },
            {"items": []},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                data_api.fetch_playlists()

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages,
            [
                "playlists page=1 items=1 next_page_token=TOKEN_3 owner_name='Playlists'",
                "playlists page=2 items=0 owner_name='Playlists'",
            ],
        )

    def test_fetch_playlist_items_logs_one_record_per_page(self) -> None:
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {
                "items": [{"id": "i1", "snippet": {"resourceId": {"videoId": "v1"}, "position": 0}}],
                "nextPageToken": "TOKEN_4",
            },
            {"items": [{"id": "i2", "snippet": {"resourceId": {"videoId": "v2"}, "position": 1}}]},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                data_api.fetch_playlist_items("PL123", playlist_title="My Playlist")

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages,
            [
                "playlist_items page=1 items=1 owner=PL123 next_page_token=TOKEN_4 "
                "owner_name='My Playlist'",
                "playlist_items page=2 items=1 owner=PL123 owner_name='My Playlist'",
            ],
        )

    def test_empty_page_carrying_a_token_ends_pagination_as_a_warning(self) -> None:
        """An empty page that still supplies a token would otherwise spin pagination
        until quota is gone. It ends the loop, is logged at WARNING, and reports the
        result as truncated."""
        client = mock.Mock()
        execute = client.playlistItems.return_value.list.return_value.execute
        execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "v1"}}], "nextPageToken": "TOKEN_A"},
            {"items": [], "nextPageToken": "TOKEN_B"},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result, truncated = data_api.fetch_all_video_ids("UUuploadsplaylist")

        self.assertEqual(result, ["v1"])
        self.assertTrue(truncated)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual([r.levelname for r in captured.records], ["DEBUG", "WARNING"])
        self.assertEqual(
            captured.records[1].getMessage(),
            "video_ids page=2 items=0 empty_page_with_token=true owner=UUuploadsplaylist "
            "next_page_token=TOKEN_B owner_name='Uploads'",
        )

    def test_observed_incident_repeated_cursor_stops_after_two_requests(self) -> None:
        """The production incident: page 1 returns items with TOKEN_A, page 2 returns the
        same TOKEN_A. Following it again re-requests the same page forever, so pagination
        ends at the repeat and reports truncation."""
        client = mock.Mock()
        execute = client.playlistItems.return_value.list.return_value.execute
        execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "v1"}}], "nextPageToken": "TOKEN_A"},
            {"items": [{"contentDetails": {"videoId": "v2"}}], "nextPageToken": "TOKEN_A"},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result, truncated = data_api.fetch_all_video_ids("UUuploadsplaylist")

        self.assertEqual(execute.call_count, 2)
        self.assertTrue(truncated)
        # Items from the repeated-token page are kept, exactly once.
        self.assertEqual(result, ["v1", "v2"])
        self.assertEqual([r.levelname for r in captured.records], ["DEBUG", "WARNING"])
        self.assertEqual(
            captured.records[1].getMessage(),
            "video_ids page=2 items=1 repeated_page_token=true owner=UUuploadsplaylist "
            "next_page_token=TOKEN_A owner_name='Uploads'",
        )

    def test_longer_cursor_cycle_is_detected(self) -> None:
        """A cycle need not be an immediate repeat — `A → B → A` must also terminate."""
        client = mock.Mock()
        execute = client.playlists.return_value.list.return_value.execute
        execute.side_effect = [
            {"items": [{"id": "p1", "snippet": {}, "contentDetails": {}}], "nextPageToken": "TOKEN_A"},
            {"items": [{"id": "p2", "snippet": {}, "contentDetails": {}}], "nextPageToken": "TOKEN_B"},
            {"items": [{"id": "p3", "snippet": {}, "contentDetails": {}}], "nextPageToken": "TOKEN_A"},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                playlists, truncated = data_api.fetch_playlists()

        self.assertEqual(execute.call_count, 3)
        self.assertTrue(truncated)
        self.assertEqual([p["id"] for p in playlists], ["p1", "p2", "p3"])
        self.assertEqual([r.levelname for r in captured.records], ["DEBUG", "DEBUG", "WARNING"])
        self.assertIn("repeated_page_token=true", captured.records[2].getMessage())

    def test_token_history_does_not_leak_between_playlists(self) -> None:
        """Cursor history is per invocation. Two playlists may legitimately hand back the
        same token string, and the second must still follow it normally."""
        client = mock.Mock()
        execute = client.playlistItems.return_value.list.return_value.execute
        page_with_token = {
            "items": [{"id": "i1", "snippet": {"resourceId": {"videoId": "v1"}, "position": 0}}],
            "nextPageToken": "SHARED_TOKEN",
        }
        final_page = {"items": [{"id": "i2", "snippet": {"resourceId": {"videoId": "v2"}, "position": 1}}]}
        execute.side_effect = [page_with_token, final_page, page_with_token, final_page]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            first, first_truncated = data_api.fetch_playlist_items("PL_ONE")
            second, second_truncated = data_api.fetch_playlist_items("PL_TWO")

        self.assertEqual(execute.call_count, 4)
        self.assertFalse(first_truncated)
        self.assertFalse(second_truncated)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)

    def test_empty_final_page_without_a_token_is_not_truncated(self) -> None:
        """An empty page with no token is an ordinary terminal response, not a problem."""
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "v1"}}], "nextPageToken": "TOKEN_A"},
            {"items": []},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                result, truncated = data_api.fetch_all_video_ids("UUuploadsplaylist")

        self.assertEqual(result, ["v1"])
        self.assertFalse(truncated)
        self.assertEqual([r.levelname for r in captured.records], ["DEBUG", "DEBUG"])

    def test_owner_name_is_quoted_so_it_cannot_corrupt_earlier_fields(self) -> None:
        """Titles are arbitrary YouTube-authored text. Rendering the name last and
        `repr`-quoted keeps a newline or `=` inside it from breaking the key=value
        fields ahead of it."""
        client = mock.Mock()
        client.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"id": "i1", "snippet": {"resourceId": {"videoId": "v1"}, "position": 0}}]},
        ]

        with mock.patch("youtube.data_api._data_client", return_value=client):
            with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
                data_api.fetch_playlist_items("PL123", playlist_title="line\nbreak items=999")

        message = captured.records[0].getMessage()
        self.assertEqual(len(message.splitlines()), 1)
        self.assertTrue(message.startswith("playlist_items page=1 items=1 owner=PL123 owner_name="))
        self.assertIn("\\n", message)


class AnalyticsRetryLoggingTest(unittest.TestCase):
    """Exercises `_analytics_query`'s retry branch with `time.sleep` mocked.

    A retry is a problem the operator should see without raising the log level, so these
    records are WARNING — which also routes them to `application.log`, not `sync.log`
    alone."""

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
        self.assertEqual([record.levelname for record in captured.records], ["WARNING"])
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
        self.assertEqual([record.levelname for record in captured.records], ["WARNING"])
        self.assertNotIn("FAKE", messages[0])
        self.assertNotIn("quotaExceeded", messages[0])


class VideoAnalyticsStageDetailLoggingTest(unittest.TestCase):
    """Exercises `sync_video_analytics()`'s per-video processed/skipped records with
    external calls mocked; counts and call sequences must stay unchanged."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.update_sync_progress").start()

    def test_video_skipped_without_publish_date(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"published_at": None, "title": "No Publish Date"}).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_analytics("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_analytics 1/1 video=v1 skipped reason=no_publish_date title='No Publish Date'"])
        self.assertEqual(counts.rows_fetched, 0)

    def test_a_video_published_after_the_effective_end_is_prefiltered_out(self) -> None:
        """A future-published video is now excluded by the bounded worklist query
        itself, before any per-video processing — sync_video_analytics() never sees
        it, so it never reaches the defensive empty-range skip branch at all."""
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.iter_video_analytics").start()
        counts = SyncCounts()

        with self.assertNoLogs("youtube_analytics.sync", level="DEBUG"):
            stages.sync_video_analytics("all", None, counts)

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        worklist.assert_called_once_with(published_through=yesterday)
        get_video.assert_not_called()
        fetch.assert_not_called()
        self.assertEqual(counts.rows_fetched, 0)

    def test_incremental_and_all_request_yesterday_as_the_effective_end(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        stages.sync_video_analytics("incremental", None, SyncCounts())
        worklist.assert_called_once_with(published_through=yesterday)
        worklist.reset_mock()

        stages.sync_video_analytics("all", None, SyncCounts())
        worklist.assert_called_once_with(published_through=yesterday)

    def test_year_scope_clamps_the_effective_end_to_the_earlier_of_year_end_and_yesterday(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()

        stages.sync_video_analytics("year", 2020, SyncCounts())
        worklist.assert_called_once_with(published_through="2020-12-31")
        worklist.reset_mock()

        current_year = date.today().year
        stages.sync_video_analytics("year", current_year, SyncCounts())
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        worklist.assert_called_once_with(published_through=yesterday)

    def test_an_empty_worklist_makes_no_per_video_calls_and_completes_normally(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.iter_video_analytics").start()
        progress = mock.patch("sync.stages.status.update_sync_progress").start()
        counts = SyncCounts()

        stages.sync_video_analytics("incremental", None, counts)

        get_video.assert_not_called()
        fetch.assert_not_called()
        progress.assert_not_called()
        self.assertEqual((counts.rows_fetched, counts.rows_written), (0, 0))

    def test_progress_ordinals_and_logging_cover_only_the_prefiltered_worklist(self) -> None:
        """A mixed two-video worklist (the excluded future video already removed by the
        real database query, simulated here by the mock only ever returning the
        eligible ID) numbers progress 1/1, never 1/2 — the excluded video was never
        part of `total` to begin with."""
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video", return_value={"published_at": "2020-01-01T00:00:00Z", "title": "Eligible Video"}
        ).start()
        mock.patch("sync.stages.database.get_last_analytics_date", return_value=None).start()
        mock.patch("sync.stages.database.upsert_video_analytics").start()
        mock.patch("sync.stages.youtube.iter_video_analytics", return_value=iter([])).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_analytics("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_analytics 1/1 video=v1 rows=0 title='Eligible Video'"])

    def test_video_processed_logs_its_own_row_count_only(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video", return_value={"published_at": "2020-01-01T00:00:00Z", "title": "Sample Video"}
        ).start()
        mock.patch("sync.stages.database.get_last_analytics_date", return_value=None).start()
        upsert_mock = mock.patch("sync.stages.database.upsert_video_analytics").start()
        rows = [{"video_id": "v1", "date": "2020-01-01"}, {"video_id": "v1", "date": "2020-01-02"}]
        mock.patch("sync.stages.youtube.iter_video_analytics", return_value=iter(rows)).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_analytics("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_analytics 1/1 video=v1 rows=2 title='Sample Video'"])
        self.assertEqual(counts.rows_fetched, 2)
        self.assertEqual(counts.rows_written, 2)
        self.assertEqual(upsert_mock.call_count, 2)

    def test_no_record_per_row_only_one_per_video(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video", return_value={"published_at": "2020-01-01T00:00:00Z", "title": "Sample Video"}
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
        mock.patch("sync.stages.status.update_sync_progress").start()

    def test_video_skipped_without_publish_date(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"published_at": None, "title": "No Publish Date"}).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_traffic_sources("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_traffic_sources 1/1 video=v1 skipped reason=no_publish_date title='No Publish Date'"])

    def test_a_video_published_after_the_effective_end_is_prefiltered_out(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.iter_video_traffic_sources").start()
        counts = SyncCounts()

        with self.assertNoLogs("youtube_analytics.sync", level="DEBUG"):
            stages.sync_video_traffic_sources("all", None, counts)

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        worklist.assert_called_once_with(published_through=yesterday)
        get_video.assert_not_called()
        fetch.assert_not_called()
        self.assertEqual(counts.rows_fetched, 0)

    def test_year_scope_clamps_the_effective_end_to_the_earlier_of_year_end_and_yesterday(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()

        stages.sync_video_traffic_sources("year", 2020, SyncCounts())
        worklist.assert_called_once_with(published_through="2020-12-31")
        worklist.reset_mock()

        current_year = date.today().year
        stages.sync_video_traffic_sources("year", current_year, SyncCounts())
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        worklist.assert_called_once_with(published_through=yesterday)

    def test_an_empty_worklist_makes_no_per_video_calls_and_completes_normally(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.iter_video_traffic_sources").start()
        counts = SyncCounts()

        stages.sync_video_traffic_sources("incremental", None, counts)

        get_video.assert_not_called()
        fetch.assert_not_called()
        self.assertEqual((counts.rows_fetched, counts.rows_written), (0, 0))

    def test_video_processed_logs_its_own_row_count_only(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video", return_value={"published_at": "2020-01-01T00:00:00Z", "title": "Sample Video"}
        ).start()
        mock.patch("sync.stages.database.get_last_traffic_source_date", return_value=None).start()
        upsert_mock = mock.patch("sync.stages.database.upsert_video_traffic_source").start()
        rows = [{"video_id": "v1", "date": "2020-01-01", "traffic_source_type": "YT_SEARCH"}]
        mock.patch("sync.stages.youtube.iter_video_traffic_sources", return_value=iter(rows)).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_video_traffic_sources("incremental", None, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages, ["video_traffic_sources 1/1 video=v1 rows=1 title='Sample Video'"])
        self.assertEqual(counts.rows_fetched, 1)
        self.assertEqual(upsert_mock.call_count, 1)


class RelatedVideoInsightsStageDetailLoggingTest(unittest.TestCase):
    """Mirrors `VideoAnalyticsStageDetailLoggingTest` for `sync_related_video_insights()`,
    whose per-video record uses search_insights's months/calls/rows shape rather than
    video_analytics's plain rows count."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.update_sync_progress").start()
        # Metadata resolution runs once after the per-video loop; keep it a no-op here
        # so these tests only capture the per-video record they're each checking.
        mock.patch("sync.stages.database.get_all_video_ids", return_value=[]).start()
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU1")).start()

    def test_video_skipped_without_publish_date(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_owned_video", return_value={"published_at": None, "title": "No Publish Date"}).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_related_video_insights("year", 2024, counts)

        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(
            messages, ["related_video_insights 1/1 video=v1 skipped reason=no_publish_date title='No Publish Date'"]
        )
        self.assertEqual(counts.rows_fetched, 0)

    def test_a_video_published_after_the_effective_end_is_prefiltered_out(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.fetch_video_related_videos").start()
        counts = SyncCounts()

        with self.assertNoLogs("youtube_analytics.sync", level="DEBUG"):
            stages.sync_related_video_insights("all", None, counts)

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        worklist.assert_called_once_with(published_through=yesterday)
        get_video.assert_not_called()
        fetch.assert_not_called()
        self.assertEqual(counts.rows_fetched, 0)

    def test_year_scope_clamps_the_effective_end_to_the_earlier_of_year_end_and_yesterday(self) -> None:
        worklist = mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()

        stages.sync_related_video_insights("year", 2020, SyncCounts())
        worklist.assert_called_once_with(published_through="2020-12-31")
        worklist.reset_mock()

        current_year = date.today().year
        stages.sync_related_video_insights("year", current_year, SyncCounts())
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        worklist.assert_called_once_with(published_through=yesterday)

    def test_an_empty_worklist_makes_no_per_video_calls_and_completes_normally(self) -> None:
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=[]).start()
        get_video = mock.patch("sync.stages.database.get_owned_video").start()
        fetch = mock.patch("sync.stages.youtube.fetch_video_related_videos").start()
        counts = SyncCounts()

        stages.sync_related_video_insights("incremental", None, counts)

        get_video.assert_not_called()
        fetch.assert_not_called()
        self.assertEqual((counts.rows_fetched, counts.rows_written), (0, 0))

    def test_video_processed_logs_its_own_row_count_only(self) -> None:
        # scope="year" with a single frozen window keeps the months/calls/rows values
        # exact and deterministic, mirroring how the Scope tests freeze "today".
        mock.patch(
            "sync.stages.monthly_insights.monthly_windows_for_range",
            return_value=[MonthlyWindow("2020-01", "2020-01-01", "2020-01-07")],
        ).start()
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video", return_value={"published_at": "2020-01-01T00:00:00Z", "title": "Sample Video"}
        ).start()
        upsert_mock = mock.patch("sync.stages.database.upsert_related_videos", return_value=1).start()
        result = analytics_api.RelatedVideosResult(
            raw_row_count=1, referrers=[{"referrer_video_id": "ref-1", "views": 5}]
        )
        mock.patch("sync.stages.youtube.fetch_video_related_videos", return_value=result).start()
        mock.patch("sync.stages.youtube.fetch_videos", return_value=[]).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_related_video_insights("year", 2020, counts)

        # The per-video record is the first line; a later metadata-resolution summary
        # (from the newly encountered "ref-1" referrer) is a separate, stage-level line.
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages[0], "related_video_insights 1/1 video=v1 months=1 rows=1 title='Sample Video'")
        self.assertEqual(counts.rows_fetched, 1)
        upsert_mock.assert_called_once_with("v1", "2020-01", [{"referrer_video_id": "ref-1", "views": 5}])

    def test_no_record_per_month_only_one_per_video(self) -> None:
        mock.patch(
            "sync.stages.monthly_insights.monthly_windows_for_range",
            return_value=[
                MonthlyWindow("2020-01", "2020-01-01", "2020-01-31"),
                MonthlyWindow("2020-02", "2020-02-01", "2020-02-29"),
            ],
        ).start()
        mock.patch("sync.stages.database.get_owned_video_ids", return_value=["v1"]).start()
        mock.patch(
            "sync.stages.database.get_owned_video", return_value={"published_at": "2020-01-01T00:00:00Z", "title": "Sample Video"}
        ).start()
        mock.patch("sync.stages.database.get_last_related_videos_month", return_value="2020-01").start()
        mock.patch("sync.stages.database.upsert_related_videos", return_value=0).start()
        mock.patch(
            "sync.stages.youtube.fetch_video_related_videos",
            return_value=analytics_api.RelatedVideosResult(raw_row_count=0, referrers=[]),
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_related_video_insights("incremental", None, counts)

        self.assertEqual(len(captured.records), 1)


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
