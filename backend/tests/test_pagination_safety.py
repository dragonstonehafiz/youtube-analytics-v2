from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from unittest import mock

from logging_config import configure_logging, reset_logging
from sync import stages
from sync.stages import SyncCounts
from youtube import analytics_api

# These tests drive stages that log through the real `youtube_analytics.sync` logger.
# Redirect it to a disposable directory for the whole module so the suite never appends
# to a developer's real `backend/data/*.log`.
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


class VideoNeverDeletesTest(unittest.TestCase):
    """`sync_videos()` only upserts; it never deletes. Deletion belongs solely to the
    `pruning` stage, regardless of whether uploads-playlist pagination truncated."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU123")).start()
        mock.patch("sync.stages.youtube.fetch_shorts_video_ids", return_value=(set(), False)).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "v1", "channel_id": "UC1", "title": "Kept"}],
        ).start()
        self.upsert = mock.patch("sync.stages.database.upsert_video").start()
        self.delete = mock.patch("sync.stages.database.delete_videos_not_in").start()

    def test_complete_pagination_upserts_and_returns_owned_ids_without_deleting(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=(["v1"], False)
        ).start()
        counts = SyncCounts()

        owned_ids = stages.sync_videos(counts, set())

        self.delete.assert_not_called()
        self.assertEqual(owned_ids, {"v1"})
        self.assertEqual(counts.rows_deleted, 0)

    def test_truncated_pagination_still_upserts_without_deleting(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=(["v1"], True)
        ).start()
        counts = SyncCounts()

        owned_ids = stages.sync_videos(counts, set())

        self.delete.assert_not_called()
        self.assertEqual(owned_ids, {"v1"})
        self.upsert.assert_called_once()
        self.assertEqual(counts.rows_written, 1)


class VideoOwnershipFilterTest(unittest.TestCase):
    """Videos discovered only via a playlist (not the uploads playlist) are imported
    only when the returned `snippet.channelId` matches the authenticated channel, so a
    video from someone else's playlist is never mistaken for this channel's."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU123")).start()
        mock.patch("sync.stages.youtube.fetch_shorts_video_ids", return_value=(set(), False)).start()
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=([], False)
        ).start()
        self.upsert = mock.patch("sync.stages.database.upsert_video").start()
        mock.patch("sync.stages.database.delete_videos_not_in").start()

    def test_playlist_only_video_owned_by_channel_is_upserted_and_retained(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "v1", "channel_id": "UC1", "title": "Mine"}],
        ).start()
        counts = SyncCounts()

        owned_ids = stages.sync_videos(counts, {"v1"})

        self.upsert.assert_called_once()
        self.assertEqual(owned_ids, {"v1"})

    def test_playlist_only_video_owned_by_another_channel_is_not_imported(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "v1", "channel_id": "UCother", "title": "Not mine"}],
        ).start()
        counts = SyncCounts()

        owned_ids = stages.sync_videos(counts, {"v1"})

        self.upsert.assert_not_called()
        self.assertEqual(owned_ids, set())

    def test_uploads_id_is_retained_even_when_details_are_missing(self) -> None:
        mock.patch("sync.stages.youtube.fetch_all_video_ids", return_value=(["v1"], False)).start()
        mock.patch("sync.stages.youtube.fetch_videos", return_value=[]).start()
        counts = SyncCounts()

        owned_ids = stages.sync_videos(counts, set())

        self.upsert.assert_not_called()
        self.assertEqual(owned_ids, {"v1"})


class VideoDetailFetchGapTest(unittest.TestCase):
    """`fetch_videos()` silently omits any id the API doesn't return an item for (e.g.
    region-restricted or transiently unavailable video). `sync_videos()` must not let
    that vanish unnoticed — it diffs the fetched ids against the requested ones and
    logs whatever is missing."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU123")).start()
        mock.patch("sync.stages.youtube.fetch_shorts_video_ids", return_value=(set(), False)).start()
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=(["v1", "v2", "v3"], False)
        ).start()
        mock.patch("sync.stages.database.upsert_video").start()
        mock.patch("sync.stages.database.delete_videos_not_in").start()

    def test_full_detail_fetch_logs_nothing(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[
                {"id": "v1", "channel_id": "UC1"},
                {"id": "v2", "channel_id": "UC1"},
                {"id": "v3", "channel_id": "UC1"},
            ],
        ).start()
        counts = SyncCounts()

        with self.assertNoLogs("youtube_analytics.sync", level="WARNING"):
            stages.sync_videos(counts, set())

    def test_ids_missing_from_detail_fetch_are_logged(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "v1", "channel_id": "UC1"}, {"id": "v3", "channel_id": "UC1"}],
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_videos(counts, set())

        warnings = [r.getMessage() for r in captured.records if r.levelname == "WARNING"]
        self.assertEqual(
            warnings, ["videos missing from detail fetch count=1 ids=['v2']"]
        )


class VideoShortsClassificationGateTest(unittest.TestCase):
    """`sync_videos()` classifies each video as a Short via a separate Shorts-playlist
    enumeration. A truncated enumeration can't tell a real Short that was missed from a
    genuine long-form video, so guessing "video" would silently reclassify already-known
    Shorts. Classification is skipped in that case, leaving `content_type` untouched."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.youtube.fetch_channel_identity", return_value=("UC1", "UU123")).start()
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=(["v1"], False)
        ).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "v1", "channel_id": "UC1", "title": "Kept", "content_type": None}],
        ).start()
        self.upsert = mock.patch("sync.stages.database.upsert_video").start()
        mock.patch("sync.stages.database.delete_videos_not_in").start()

    def test_complete_shorts_pagination_classifies_normally(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_shorts_video_ids", return_value=({"v1"}, False)
        ).start()
        counts = SyncCounts()

        stages.sync_videos(counts, set())

        written = self.upsert.call_args.args[0]
        self.assertEqual(written["content_type"], "short")

    def test_truncated_shorts_pagination_skips_classification_but_still_upserts(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_shorts_video_ids", return_value=(set(), True)
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_videos(counts, set())

        written = self.upsert.call_args.args[0]
        self.assertIsNone(written["content_type"])
        self.assertEqual(counts.rows_written, 1)
        warnings = [r.getMessage() for r in captured.records if r.levelname == "WARNING"]
        self.assertEqual(
            warnings, ["videos classification skipped reason=shorts_pagination_truncated"]
        )


class PlaylistCleanupGateTest(unittest.TestCase):
    """`sync_playlists()` has two deletes: the per-playlist item replace and the
    listing-level reconcile. Each is gated on its own pagination completing."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.database.upsert_playlist").start()
        mock.patch("sync.stages.database.upsert_playlist_item").start()
        self.delete_items = mock.patch(
            "sync.stages.database.delete_playlist_items", return_value=3
        ).start()
        self.delete_playlists = mock.patch(
            "sync.stages.database.delete_playlists_not_in", return_value=2
        ).start()

    def test_complete_pagination_runs_both_deletes(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_playlists",
            return_value=([{"id": "PL1", "title": "One"}], False),
        ).start()
        mock.patch(
            "sync.stages.youtube.fetch_playlist_items",
            return_value=([{"id": "i1", "playlist_id": "PL1", "video_id": "v1"}], False),
        ).start()
        counts = SyncCounts()

        playlist_video_ids = stages.sync_playlists(counts)

        self.delete_items.assert_called_once_with("PL1")
        self.delete_playlists.assert_called_once_with(["PL1"])
        self.assertEqual(playlist_video_ids, {"v1"})

    def test_truncated_items_leave_that_playlist_untouched(self) -> None:
        """The item replace is delete-then-reinsert, so a partial page set must not run
        it at all — otherwise the playlist silently shrinks to what was fetched."""
        mock.patch(
            "sync.stages.youtube.fetch_playlists",
            return_value=([{"id": "PL1", "title": "One"}], False),
        ).start()
        mock.patch(
            "sync.stages.youtube.fetch_playlist_items",
            return_value=([{"id": "i1", "playlist_id": "PL1", "video_id": "v1"}], True),
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_playlists(counts)

        self.delete_items.assert_not_called()
        # The listing itself paginated cleanly, so its own reconcile still runs.
        self.delete_playlists.assert_called_once_with(["PL1"])
        warnings = [r.getMessage() for r in captured.records if r.levelname == "WARNING"]
        self.assertEqual(
            warnings,
            ["playlist_items replace skipped reason=pagination_truncated playlist=PL1 "
             "fetched=1 title='One'"],
        )

    def test_truncated_listing_skips_the_listing_reconcile(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_playlists",
            return_value=([{"id": "PL1", "title": "One"}], True),
        ).start()
        mock.patch(
            "sync.stages.youtube.fetch_playlist_items",
            return_value=([{"id": "i1", "playlist_id": "PL1", "video_id": "v1"}], False),
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_playlists(counts)

        self.delete_playlists.assert_not_called()
        # A cleanly paginated playlist still gets its items replaced.
        self.delete_items.assert_called_once_with("PL1")
        warnings = [r.getMessage() for r in captured.records if r.levelname == "WARNING"]
        self.assertEqual(
            warnings, ["playlists cleanup skipped reason=pagination_truncated fetched=1"]
        )


class PruningTest(unittest.TestCase):
    """`sync_pruning()` is the sole deleter of video rows, and it deletes unconditionally
    against whatever channel-owned set it's given."""

    def test_deletes_against_the_given_owned_set(self) -> None:
        delete = mock.patch("sync.stages.database.delete_videos_not_in", return_value=5).start()
        self.addCleanup(mock.patch.stopall)
        counts = SyncCounts()

        stages.sync_pruning(counts, {"v1", "v2"})

        delete.assert_called_once_with(["v1", "v2"])
        self.assertEqual(counts.rows_deleted, 5)

    def test_empty_owned_set_deletes_everything(self) -> None:
        delete = mock.patch("sync.stages.database.delete_videos_not_in", return_value=0).start()
        self.addCleanup(mock.patch.stopall)
        counts = SyncCounts()

        stages.sync_pruning(counts, set())

        delete.assert_called_once_with([])
        self.assertEqual(counts.rows_deleted, 0)


class AnalyticsPageSizeTerminationTest(unittest.TestCase):
    """`_fetch_analytics_rows()` stops as soon as a page returns fewer rows than
    `maxResults` (including an empty page), and only advances `startIndex`/sleeps
    between requests when the prior page was exactly full. `maxResults=2` throughout
    so full-page fixtures stay readable."""

    _HEADERS = [{"name": "day"}, {"name": "views"}]

    def _service(self, responses: list[dict]) -> mock.Mock:
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = responses
        return service

    def test_empty_first_page_makes_exactly_one_query(self) -> None:
        service = self._service([{"rows": [], "columnHeaders": []}])

        with mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            rows = analytics_api._fetch_analytics_rows(service, {"startIndex": 1, "maxResults": 2})

        self.assertEqual(rows, [])
        self.assertEqual(service.reports.return_value.query.call_count, 1)
        sleep_mock.assert_not_called()

    def test_partial_first_page_returned_with_one_request_and_no_sleep(self) -> None:
        service = self._service([
            {"rows": [["2024-01-01", 5]], "columnHeaders": self._HEADERS},
        ])

        with mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            rows = analytics_api._fetch_analytics_rows(service, {"startIndex": 1, "maxResults": 2})

        self.assertEqual(rows, [{"day": "2024-01-01", "views": 5}])
        self.assertEqual(service.reports.return_value.query.call_count, 1)
        sleep_mock.assert_not_called()

    def test_exactly_full_page_advances_start_index_and_continues(self) -> None:
        service = self._service([
            {
                "rows": [["2024-01-01", 5], ["2024-01-02", 6]],
                "columnHeaders": self._HEADERS,
            },
            {"rows": [], "columnHeaders": self._HEADERS},
        ])

        with mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            rows = analytics_api._fetch_analytics_rows(service, {"startIndex": 1, "maxResults": 2})

        self.assertEqual(len(rows), 2)
        start_indexes = [
            call.kwargs["startIndex"] for call in service.reports.return_value.query.call_args_list
        ]
        self.assertEqual(start_indexes, [1, 3])
        self.assertEqual(sleep_mock.call_count, 1)

    def test_full_pages_then_partial_page_returns_all_rows_in_order_and_stops(self) -> None:
        service = self._service([
            {
                "rows": [["2024-01-01", 5], ["2024-01-02", 6]],
                "columnHeaders": self._HEADERS,
            },
            {
                "rows": [["2024-01-03", 7], ["2024-01-04", 8]],
                "columnHeaders": self._HEADERS,
            },
            {"rows": [["2024-01-05", 9]], "columnHeaders": self._HEADERS},
        ])

        with mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            rows = analytics_api._fetch_analytics_rows(service, {"startIndex": 1, "maxResults": 2})

        self.assertEqual(
            rows,
            [
                {"day": "2024-01-01", "views": 5},
                {"day": "2024-01-02", "views": 6},
                {"day": "2024-01-03", "views": 7},
                {"day": "2024-01-04", "views": 8},
                {"day": "2024-01-05", "views": 9},
            ],
        )
        self.assertEqual(service.reports.return_value.query.call_count, 3)
        start_indexes = [
            call.kwargs["startIndex"] for call in service.reports.return_value.query.call_args_list
        ]
        self.assertEqual(start_indexes, [1, 3, 5])
        self.assertEqual(sleep_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
