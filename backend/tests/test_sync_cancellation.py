from __future__ import annotations

import unittest
from unittest import mock

from sync import status
from sync.stages import SyncCounts
from youtube import analytics_api, data_api


def _raise_after(n: int) -> mock.Mock:
    """Return a checkpoint that raises SyncCancelled starting from its (n+1)th call."""
    calls = {"count": 0}

    def checkpoint() -> None:
        calls["count"] += 1
        if calls["count"] > n:
            raise status.SyncCancelled()

    return mock.Mock(side_effect=checkpoint)


class DataApiPaginationCheckpointTest(unittest.TestCase):
    """A checkpoint that raises stops pagination before the next page's request, never
    mid-page and never on the first page."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)

    def test_fetch_all_video_ids_stops_before_the_second_page(self) -> None:
        yt = mock.Mock()
        yt.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"contentDetails": {"videoId": "v1"}}], "nextPageToken": "t2"},
            {"items": [{"contentDetails": {"videoId": "v2"}}], "nextPageToken": None},
        ]
        mock.patch("youtube.data_api._data_client", return_value=yt).start()
        checkpoint = _raise_after(0)

        with self.assertRaises(status.SyncCancelled):
            data_api.fetch_all_video_ids("UU123", checkpoint=checkpoint)

        self.assertEqual(yt.playlistItems.return_value.list.return_value.execute.call_count, 1)

    def test_fetch_playlists_stops_before_the_second_page(self) -> None:
        yt = mock.Mock()
        yt.playlists.return_value.list.return_value.execute.side_effect = [
            {"items": [{"id": "PL1", "snippet": {}, "contentDetails": {}}], "nextPageToken": "t2"},
            {"items": [{"id": "PL2", "snippet": {}, "contentDetails": {}}], "nextPageToken": None},
        ]
        mock.patch("youtube.data_api._data_client", return_value=yt).start()
        checkpoint = _raise_after(0)

        with self.assertRaises(status.SyncCancelled):
            data_api.fetch_playlists(checkpoint=checkpoint)

        self.assertEqual(yt.playlists.return_value.list.return_value.execute.call_count, 1)

    def test_fetch_playlist_items_stops_before_the_second_page(self) -> None:
        yt = mock.Mock()
        yt.playlistItems.return_value.list.return_value.execute.side_effect = [
            {"items": [{"id": "i1", "snippet": {}}], "nextPageToken": "t2"},
            {"items": [{"id": "i2", "snippet": {}}], "nextPageToken": None},
        ]
        mock.patch("youtube.data_api._data_client", return_value=yt).start()
        checkpoint = _raise_after(0)

        with self.assertRaises(status.SyncCancelled):
            data_api.fetch_playlist_items("PL1", checkpoint=checkpoint)

        self.assertEqual(yt.playlistItems.return_value.list.return_value.execute.call_count, 1)

    def test_iter_comment_threads_stops_before_the_second_page(self) -> None:
        page_item = {
            "id": "thread-1",
            "snippet": {
                "topLevelComment": {
                    "id": "c1",
                    "snippet": {
                        "textDisplay": "hi",
                        "authorDisplayName": "A",
                        "publishedAt": "2024-01-01T00:00:00Z",
                    },
                },
            },
        }
        yt = mock.Mock()
        yt.commentThreads.return_value.list.return_value.execute.side_effect = [
            {"items": [page_item], "nextPageToken": "t2"},
            {"items": [], "nextPageToken": None},
        ]
        mock.patch("youtube.data_api._data_client", return_value=yt).start()
        checkpoint = _raise_after(0)

        with self.assertRaises(status.SyncCancelled):
            list(data_api.iter_comment_threads("v1", checkpoint=checkpoint))

        self.assertEqual(yt.commentThreads.return_value.list.return_value.execute.call_count, 1)

    def test_no_checkpoint_call_when_pagination_never_continues(self) -> None:
        yt = mock.Mock()
        yt.playlists.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "PL1", "snippet": {}, "contentDetails": {}}], "nextPageToken": None,
        }
        mock.patch("youtube.data_api._data_client", return_value=yt).start()
        checkpoint = mock.Mock()

        data_api.fetch_playlists(checkpoint=checkpoint)

        checkpoint.assert_not_called()


class AnalyticsApiCheckpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)

    def test_retry_checkpoint_is_invoked_after_the_backoff_sleep(self) -> None:
        from googleapiclient.errors import HttpError

        response = mock.Mock(status=500)
        error = HttpError(response, b'{"error": {"errors": [{"reason": "backendError"}]}}')
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = [error, {"rows": []}]
        checkpoint = mock.Mock()

        with mock.patch("youtube.analytics_api.time.sleep"):
            analytics_api._analytics_query(service, {}, checkpoint=checkpoint)

        checkpoint.assert_called_once()

    def test_retry_checkpoint_raising_stops_further_attempts(self) -> None:
        from googleapiclient.errors import HttpError

        response = mock.Mock(status=500)
        error = HttpError(response, b'{"error": {"errors": [{"reason": "backendError"}]}}')
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = [error, {"rows": []}]
        checkpoint = _raise_after(0)

        with mock.patch("youtube.analytics_api.time.sleep"):
            with self.assertRaises(status.SyncCancelled):
                analytics_api._analytics_query(service, {}, checkpoint=checkpoint)

        self.assertEqual(service.reports.return_value.query.return_value.execute.call_count, 1)

    def test_fetch_analytics_rows_stops_before_the_second_page(self) -> None:
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = [
            {"rows": [["2024-01-01", 5], ["2024-01-02", 6]], "columnHeaders": [{"name": "day"}, {"name": "views"}]},
            {"rows": [], "columnHeaders": [{"name": "day"}, {"name": "views"}]},
        ]
        checkpoint = _raise_after(0)

        with mock.patch("youtube.analytics_api.time.sleep"):
            with self.assertRaises(status.SyncCancelled):
                analytics_api._fetch_analytics_rows(
                    service, {"startIndex": 1, "maxResults": 2}, checkpoint=checkpoint
                )

        self.assertEqual(service.reports.return_value.query.call_count, 1)


class StageCheckpointWiringTest(unittest.TestCase):
    """Confirms sync stages forward `status.raise_if_stopping` into the YouTube layer
    and check between their own work units, without duplicating full stage coverage."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        status.reset_sync_status()
        self.addCleanup(status.reset_sync_status)

    def test_sync_playlists_stops_between_playlists_without_fetching_the_next(self) -> None:
        from sync import stages

        mock.patch(
            "sync.stages.youtube.fetch_playlists",
            return_value=([{"id": "PL1"}, {"id": "PL2"}], False),
        ).start()
        fetch_items = mock.patch(
            "sync.stages.youtube.fetch_playlist_items", return_value=([], False)
        ).start()
        mock.patch("sync.stages.database.upsert_playlist").start()
        mock.patch("sync.stages.database.delete_playlist_items", return_value=0).start()

        status.try_begin_sync(["playlists"])
        status.request_stop()

        with self.assertRaises(status.SyncCancelled):
            stages.sync_playlists(SyncCounts())

        self.assertEqual(fetch_items.call_count, 1)

    def test_sync_pruning_checks_before_deleting(self) -> None:
        from sync import stages

        delete = mock.patch("sync.stages.database.delete_videos_not_in").start()
        status.try_begin_sync(["pruning"])
        status.request_stop()

        with self.assertRaises(status.SyncCancelled):
            stages.sync_pruning(SyncCounts(), {"v1"})

        delete.assert_not_called()

    def test_sync_fx_rates_stops_between_days(self) -> None:
        from datetime import date, timedelta

        from sync import stages

        # A last-synced date three days ago gives exactly two days of work (yesterday
        # inclusive), regardless of when this test runs.
        last_synced = (date.today() - timedelta(days=3)).isoformat()
        mock.patch(
            "sync.stages.database.get_last_fx_rate",
            return_value={"date": last_synced, "usd_to_sgd": 1.35},
        ).start()
        upsert = mock.patch("sync.stages.database.upsert_fx_rate").start()

        import pandas as pd
        mock.patch("yfinance.download", return_value=pd.DataFrame()).start()

        status.try_begin_sync(["fx_rates"])
        status.request_stop()

        with self.assertRaises(status.SyncCancelled):
            stages.sync_fx_rates(SyncCounts())

        # Day 1 (carried rate) is written before the checkpoint on day 2 raises.
        self.assertEqual(upsert.call_count, 1)


if __name__ == "__main__":
    unittest.main()
