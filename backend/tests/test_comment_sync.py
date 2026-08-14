from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from unittest import mock

from googleapiclient.errors import HttpError
from logging_config import configure_logging, reset_logging
from sync import stages
from sync.stages import COMMENT_INCREMENTAL_OVERLAP, SyncCounts
from youtube import data_api

# These tests drive the comments stage and fetcher, both of which log through the real
# `youtube_analytics.sync` logger. Redirect it to a disposable directory for the whole
# module so the suite never appends to a developer's real `backend/data/*.log`.
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


def _normalized(comment_id: str, published_at: str = "2026-07-01T00:00:00Z") -> dict:
    """Build one already-normalized thread as `iter_comment_threads()` would yield it."""
    return {
        "author": {
            "id": "channel:UCauthor",
            "youtube_channel_id": "UCauthor",
            "display_name": "Commenter",
            "profile_image_url": None,
            "channel_url": None,
        },
        "comment": {
            "id": comment_id,
            "thread_id": f"thread-{comment_id}",
            "video_id": "v1",
            "author_id": "channel:UCauthor",
            "text": "nice",
            "like_count": 0,
            "total_reply_count": 0,
            "published_at": published_at,
            "youtube_updated_at": published_at,
        },
    }


class BootstrapCutoffTest(unittest.TestCase):
    """A video with no stored comments is read back to December 1 of the previous year,
    recomputed per run so the window rolls forward with the calendar."""

    def test_cutoff_is_january_first_minus_one_month(self) -> None:
        self.assertEqual(stages._comment_bootstrap_cutoff(date(2026, 8, 9)), "2025-12-01")

    def test_cutoff_rolls_over_with_the_year(self) -> None:
        self.assertEqual(stages._comment_bootstrap_cutoff(date(2026, 1, 1)), "2025-12-01")
        self.assertEqual(stages._comment_bootstrap_cutoff(date(2027, 3, 1)), "2026-12-01")


class CommentStageTestCase(unittest.TestCase):
    """Base case stubbing the comments stage's database and YouTube dependencies."""

    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.database.get_all_video_ids", return_value=["v1"]).start()
        mock.patch("sync.stages.database.get_video", return_value={"title": "A video"}).start()
        self.known = mock.patch(
            "sync.stages.database.get_comment_ids_for_video", return_value=set()
        ).start()
        self.upsert_author = mock.patch("sync.stages.database.upsert_comment_author").start()
        self.upsert_comment = mock.patch("sync.stages.database.upsert_comment").start()
        self.cleanup = mock.patch(
            "sync.stages.database.delete_orphan_comment_authors", return_value=0
        ).start()
        self.iter_threads = mock.patch("sync.stages.youtube.iter_comment_threads").start()

    @property
    def written_ids(self) -> list[str]:
        return [call.args[0]["id"] for call in self.upsert_comment.call_args_list]


class IncrementalBoundaryTest(CommentStageTestCase):
    def test_stops_one_overlap_past_the_first_known_comment(self) -> None:
        self.known.return_value = {"c50"}
        self.iter_threads.return_value = iter(
            [_normalized(f"c{n}") for n in range(1, 301)]
        )
        counts = SyncCounts()

        stages.sync_comments("incremental", counts)

        # c50 is the boundary and is still refreshed, then COMMENT_INCREMENTAL_OVERLAP
        # further comments are read before the walk stops.
        self.assertEqual(len(self.written_ids), 50 + COMMENT_INCREMENTAL_OVERLAP)
        self.assertEqual(self.written_ids[-1], f"c{50 + COMMENT_INCREMENTAL_OVERLAP}")

    def test_counts_the_boundary_item_it_stopped_on_as_fetched(self) -> None:
        self.known.return_value = {"c1"}
        self.iter_threads.return_value = iter(
            [_normalized(f"c{n}") for n in range(1, 301)]
        )
        counts = SyncCounts()

        stages.sync_comments("incremental", counts)

        # Every inspected item counts as fetched, including the one whose inspection
        # ended the walk, which is one past the last item written.
        self.assertEqual(counts.rows_fetched, COMMENT_INCREMENTAL_OVERLAP + 2)
        self.assertEqual(counts.rows_written, 2 * (COMMENT_INCREMENTAL_OVERLAP + 1))

    def test_empty_video_stops_at_the_bootstrap_cutoff(self) -> None:
        cutoff = stages._comment_bootstrap_cutoff(date.today())
        older = "2000-01-01T00:00:00Z"
        self.iter_threads.return_value = iter([
            _normalized("recent-1"),
            _normalized("recent-2", published_at=cutoff),
            _normalized("too-old", published_at=older),
            _normalized("also-too-old", published_at=older),
        ])
        counts = SyncCounts()

        stages.sync_comments("incremental", counts)

        # The cutoff itself is inclusive; the first comment before it ends the walk.
        self.assertEqual(self.written_ids, ["recent-1", "recent-2"])

    def test_never_deletes_comments(self) -> None:
        self.known.return_value = {"c1"}
        self.iter_threads.return_value = iter([_normalized("c1")])
        counts = SyncCounts()

        stages.sync_comments("incremental", counts)

        self.assertEqual(counts.rows_deleted, 0)


class FullDataScanTest(CommentStageTestCase):
    def test_reads_past_known_comments_and_the_cutoff(self) -> None:
        self.known.return_value = {"c1"}
        self.iter_threads.return_value = iter([
            _normalized("c1"),
            _normalized("c2"),
            _normalized("c3", published_at="1999-01-01T00:00:00Z"),
        ])
        counts = SyncCounts()

        stages.sync_comments("all", counts)

        self.assertEqual(self.written_ids, ["c1", "c2", "c3"])

    def test_still_deletes_no_comments(self) -> None:
        self.iter_threads.return_value = iter([_normalized("c1")])
        counts = SyncCounts()

        stages.sync_comments("all", counts)

        self.assertEqual(counts.rows_deleted, 0)


class CommentStageBehaviourTest(CommentStageTestCase):
    def test_writes_the_author_before_its_comment(self) -> None:
        order: list[str] = []
        self.upsert_author.side_effect = lambda author: order.append("author")
        self.upsert_comment.side_effect = lambda comment: order.append("comment")
        self.iter_threads.return_value = iter([_normalized("c1")])

        stages.sync_comments("incremental", SyncCounts())

        self.assertEqual(order, ["author", "comment"])

    def test_one_failed_item_does_not_stop_the_others(self) -> None:
        self.upsert_comment.side_effect = [RuntimeError("constraint"), None]
        self.iter_threads.return_value = iter([_normalized("bad"), _normalized("good")])
        counts = SyncCounts()

        stages.sync_comments("incremental", counts)

        self.assertEqual(self.written_ids, ["bad", "good"])
        # The failed comment's author write still counted; its comment write did not.
        self.assertEqual(counts.rows_written, 3)

    def test_orphan_author_cleanup_counts_as_deletions(self) -> None:
        self.cleanup.return_value = 4
        self.iter_threads.return_value = iter([])
        counts = SyncCounts()

        stages.sync_comments("incremental", counts)

        self.assertEqual(counts.rows_deleted, 4)

    def test_takes_its_worklist_from_the_database_only(self) -> None:
        discovery = {
            name: mock.patch(f"sync.stages.youtube.{name}").start()
            for name in (
                "fetch_channel_identity", "fetch_all_video_ids",
                "fetch_shorts_video_ids", "fetch_videos", "fetch_playlists",
            )
        }
        self.iter_threads.return_value = iter([])

        stages.sync_comments("incremental", SyncCounts())

        for name, patched in discovery.items():
            with self.subTest(call=name):
                patched.assert_not_called()
        self.iter_threads.assert_called_once_with("v1", title="A video")


def _raw_thread(
    thread_id: str = "t1",
    comment_id: str = "c1",
    channel_id: str | None = "UCauthor",
) -> dict:
    """Build one commentThreads item as the Data API returns it."""
    snippet: dict = {
        "textDisplay": "plain text body",
        "authorDisplayName": "Commenter",
        "authorProfileImageUrl": "https://example.test/a.jpg",
        "authorChannelUrl": "http://www.youtube.com/@commenter",
        "likeCount": 3,
        "publishedAt": "2026-07-01T00:00:00Z",
        "updatedAt": "2026-07-02T00:00:00Z",
    }
    if channel_id is not None:
        snippet["authorChannelId"] = {"value": channel_id}
    return {
        "id": thread_id,
        "snippet": {
            "totalReplyCount": 7,
            "topLevelComment": {"id": comment_id, "snippet": snippet},
        },
    }


def _http_error(status: int, reason: str) -> HttpError:
    """Build an HttpError carrying the Data API's machine-readable reason."""
    content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode("utf-8")
    return HttpError(mock.Mock(status=status), content)


class CommentThreadFetchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(mock.patch.stopall)
        self.client = mock.Mock()
        mock.patch("youtube.data_api._data_client", return_value=self.client).start()
        self.list_call = self.client.commentThreads.return_value.list

    def _returns(self, *responses: dict) -> None:
        self.list_call.return_value.execute.side_effect = list(responses)

    def test_requests_snippet_only_at_maximum_page_size_newest_first(self) -> None:
        self._returns({"items": [_raw_thread()]})

        list(data_api.iter_comment_threads("v1"))

        kwargs = self.list_call.call_args.kwargs
        self.assertEqual(kwargs["part"], "snippet")
        self.assertEqual(kwargs["videoId"], "v1")
        self.assertEqual(kwargs["maxResults"], data_api.COMMENT_THREADS_PAGE_SIZE)
        self.assertEqual(kwargs["order"], "time")
        self.assertEqual(kwargs["textFormat"], "plainText")

    def test_never_requests_reply_bodies(self) -> None:
        self._returns({"items": [_raw_thread()]})

        list(data_api.iter_comment_threads("v1"))

        self.assertNotIn("replies", self.list_call.call_args.kwargs["part"])
        self.client.comments.assert_not_called()

    def test_normalizes_author_and_comment_including_reply_count(self) -> None:
        self._returns({"items": [_raw_thread()]})

        item = next(iter(data_api.iter_comment_threads("v1")))

        self.assertEqual(item["author"]["id"], "channel:UCauthor")
        self.assertEqual(item["author"]["youtube_channel_id"], "UCauthor")
        self.assertEqual(item["author"]["channel_url"], "http://www.youtube.com/@commenter")
        self.assertEqual(item["comment"]["thread_id"], "t1")
        self.assertEqual(item["comment"]["video_id"], "v1")
        self.assertEqual(item["comment"]["total_reply_count"], 7)
        self.assertEqual(item["comment"]["like_count"], 3)
        self.assertEqual(item["comment"]["youtube_updated_at"], "2026-07-02T00:00:00Z")

    def test_missing_author_channel_id_falls_back_to_a_comment_scoped_key(self) -> None:
        self._returns({"items": [_raw_thread(channel_id=None)]})

        item = next(iter(data_api.iter_comment_threads("v1")))

        self.assertEqual(item["author"]["id"], "comment:c1")
        self.assertIsNone(item["author"]["youtube_channel_id"])

    def test_two_authorless_commenters_stay_distinct(self) -> None:
        self._returns({"items": [
            _raw_thread(thread_id="t1", comment_id="c1", channel_id=None),
            _raw_thread(thread_id="t2", comment_id="c2", channel_id=None),
        ]})

        items = list(data_api.iter_comment_threads("v1"))

        self.assertEqual({item["author"]["id"] for item in items}, {"comment:c1", "comment:c2"})

    def test_malformed_item_is_skipped_without_losing_the_page(self) -> None:
        self._returns({"items": [{"id": "t0", "snippet": {}}, _raw_thread()]})

        items = list(data_api.iter_comment_threads("v1"))

        self.assertEqual([item["comment"]["id"] for item in items], ["c1"])

    def test_follows_the_next_page_token(self) -> None:
        self._returns(
            {"items": [_raw_thread(thread_id="t1", comment_id="c1")], "nextPageToken": "tok"},
            {"items": [_raw_thread(thread_id="t2", comment_id="c2")]},
        )

        items = list(data_api.iter_comment_threads("v1"))

        self.assertEqual([item["comment"]["id"] for item in items], ["c1", "c2"])
        self.assertEqual(self.list_call.call_args_list[1].kwargs["pageToken"], "tok")

    def test_stops_on_a_repeated_page_token(self) -> None:
        self._returns(
            {"items": [_raw_thread(thread_id="t1", comment_id="c1")], "nextPageToken": "tok"},
            {"items": [_raw_thread(thread_id="t2", comment_id="c2")], "nextPageToken": "tok"},
        )

        items = list(data_api.iter_comment_threads("v1"))

        self.assertEqual(len(items), 2)
        self.assertEqual(len(self.list_call.call_args_list), 2)

    def test_requests_no_further_pages_when_the_caller_stops_early(self) -> None:
        self._returns(
            {"items": [_raw_thread(thread_id="t1", comment_id="c1")], "nextPageToken": "tok"},
            {"items": [_raw_thread(thread_id="t2", comment_id="c2")]},
        )

        for _item in data_api.iter_comment_threads("v1"):
            break

        self.assertEqual(len(self.list_call.call_args_list), 1)

    def test_comments_disabled_video_yields_nothing_instead_of_raising(self) -> None:
        self.list_call.return_value.execute.side_effect = _http_error(403, "commentsDisabled")

        self.assertEqual(list(data_api.iter_comment_threads("v1")), [])

    def test_missing_video_yields_nothing_instead_of_raising(self) -> None:
        self.list_call.return_value.execute.side_effect = _http_error(404, "videoNotFound")

        self.assertEqual(list(data_api.iter_comment_threads("v1")), [])

    def test_quota_exhaustion_propagates(self) -> None:
        self.list_call.return_value.execute.side_effect = _http_error(403, "quotaExceeded")

        with self.assertRaises(HttpError):
            list(data_api.iter_comment_threads("v1"))


if __name__ == "__main__":
    unittest.main()
