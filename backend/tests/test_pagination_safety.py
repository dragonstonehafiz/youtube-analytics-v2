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


class VideoCleanupGateTest(unittest.TestCase):
    """`sync_videos()` reconciles deletions against the uploads-playlist enumeration.
    A truncated enumeration is a partial view of the channel, and deleting against it
    would drop every video past the cut plus its analytics and traffic-source history
    via `ON DELETE CASCADE`, so the delete is skipped."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.youtube.fetch_uploads_playlist_id", return_value="UU123").start()
        mock.patch("sync.stages.youtube.fetch_shorts_video_ids", return_value=(set(), False)).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "v1", "title": "Kept"}],
        ).start()
        self.upsert = mock.patch("sync.stages.database.upsert_video").start()
        self.delete = mock.patch("sync.stages.database.delete_videos_not_in", return_value=7).start()

    def test_complete_pagination_still_reconciles_deletions(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=(["v1"], False)
        ).start()
        counts = SyncCounts()

        stages.sync_videos(counts)

        self.delete.assert_called_once_with(["v1"])
        self.assertEqual(counts.rows_deleted, 7)

    def test_truncated_pagination_skips_the_delete_but_still_upserts(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=(["v1"], True)
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_videos(counts)

        self.delete.assert_not_called()
        self.assertEqual(counts.rows_deleted, 0)
        # Forward progress is preserved: the rows that were fetched are still written.
        self.upsert.assert_called_once()
        self.assertEqual(counts.rows_written, 1)
        warnings = [r.getMessage() for r in captured.records if r.levelname == "WARNING"]
        self.assertEqual(warnings, ["videos cleanup skipped reason=pagination_truncated fetched=1"])


class VideoShortsClassificationGateTest(unittest.TestCase):
    """`sync_videos()` classifies each video as a Short via a separate Shorts-playlist
    enumeration. A truncated enumeration can't tell a real Short that was missed from a
    genuine long-form video, so guessing "video" would silently reclassify already-known
    Shorts. Classification is skipped in that case, leaving `content_type` untouched."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.youtube.fetch_uploads_playlist_id", return_value="UU123").start()
        mock.patch(
            "sync.stages.youtube.fetch_all_video_ids", return_value=(["v1"], False)
        ).start()
        mock.patch(
            "sync.stages.youtube.fetch_videos",
            return_value=[{"id": "v1", "title": "Kept", "content_type": None}],
        ).start()
        self.upsert = mock.patch("sync.stages.database.upsert_video").start()
        mock.patch("sync.stages.database.delete_videos_not_in", return_value=0).start()

    def test_complete_shorts_pagination_classifies_normally(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_shorts_video_ids", return_value=({"v1"}, False)
        ).start()
        counts = SyncCounts()

        stages.sync_videos(counts)

        written = self.upsert.call_args.args[0]
        self.assertEqual(written["content_type"], "short")

    def test_truncated_shorts_pagination_skips_classification_but_still_upserts(self) -> None:
        mock.patch(
            "sync.stages.youtube.fetch_shorts_video_ids", return_value=(set(), True)
        ).start()
        counts = SyncCounts()

        with self.assertLogs("youtube_analytics.sync", level="DEBUG") as captured:
            stages.sync_videos(counts)

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
            return_value=([{"id": "i1", "playlist_id": "PL1"}], False),
        ).start()
        counts = SyncCounts()

        stages.sync_playlists(counts)

        self.delete_items.assert_called_once_with("PL1")
        self.delete_playlists.assert_called_once_with(["PL1"])

    def test_truncated_items_leave_that_playlist_untouched(self) -> None:
        """The item replace is delete-then-reinsert, so a partial page set must not run
        it at all — otherwise the playlist silently shrinks to what was fetched."""
        mock.patch(
            "sync.stages.youtube.fetch_playlists",
            return_value=([{"id": "PL1", "title": "One"}], False),
        ).start()
        mock.patch(
            "sync.stages.youtube.fetch_playlist_items",
            return_value=([{"id": "i1", "playlist_id": "PL1"}], True),
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
            return_value=([{"id": "i1", "playlist_id": "PL1"}], False),
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


class AnalyticsEmptyRowTerminationTest(unittest.TestCase):
    """Locks in `_fetch_analytics_rows()`'s existing behavior: `startIndex` pagination
    stops on the first empty `rows` response. No production change was needed here — this
    is regression cover so the Data API fix cannot be mirrored onto it by mistake."""

    def _service(self, responses: list[dict]) -> mock.Mock:
        service = mock.Mock()
        service.reports.return_value.query.return_value.execute.side_effect = responses
        return service

    def test_empty_first_page_makes_exactly_one_query(self) -> None:
        service = self._service([{"rows": [], "columnHeaders": []}])

        with mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            rows = analytics_api._fetch_analytics_rows(service, {"startIndex": 1, "maxResults": 200})

        self.assertEqual(rows, [])
        self.assertEqual(service.reports.return_value.query.call_count, 1)
        sleep_mock.assert_not_called()

    def test_empty_page_after_populated_pages_returns_prior_rows_and_stops(self) -> None:
        headers = [{"name": "day"}, {"name": "views"}]
        service = self._service([
            {"rows": [["2024-01-01", 5]], "columnHeaders": headers},
            {"rows": [], "columnHeaders": headers},
        ])

        with mock.patch("youtube.analytics_api.time.sleep") as sleep_mock:
            rows = analytics_api._fetch_analytics_rows(service, {"startIndex": 1, "maxResults": 200})

        self.assertEqual(rows, [{"day": "2024-01-01", "views": 5}])
        self.assertEqual(service.reports.return_value.query.call_count, 2)
        self.assertEqual(sleep_mock.call_count, 1)

    def test_non_empty_rows_advance_start_index(self) -> None:
        headers = [{"name": "day"}, {"name": "views"}]
        service = self._service([
            {"rows": [["2024-01-01", 5]], "columnHeaders": headers},
            {"rows": [["2024-01-02", 6]], "columnHeaders": headers},
            {"rows": [], "columnHeaders": headers},
        ])

        with mock.patch("youtube.analytics_api.time.sleep"):
            rows = analytics_api._fetch_analytics_rows(service, {"startIndex": 1, "maxResults": 200})

        self.assertEqual(len(rows), 2)
        start_indexes = [
            call.kwargs["startIndex"] for call in service.reports.return_value.query.call_args_list
        ]
        self.assertEqual(start_indexes, [1, 201, 401])


if __name__ == "__main__":
    unittest.main()
