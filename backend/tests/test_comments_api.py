from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from database import connection
from routes.comments import router as comments_router


def _video(video_id: str, title: str, content_type: str = "video") -> dict:
    return {
        "id": video_id, "channel_id": "c1", "title": title, "description": "",
        "published_at": "2024-01-01T00:00:00Z", "duration_seconds": 100, "thumbnail_url": "",
        "content_type": content_type, "privacy_status": "public",
        "view_count": 10, "like_count": 1, "comment_count": 0,
    }


def _author(author_id: str, display_name: str, channel_id: str | None = None) -> dict:
    return {
        "id": author_id, "youtube_channel_id": channel_id, "display_name": display_name,
        "profile_image_url": None, "channel_url": None,
    }


def _comment(
    comment_id: str,
    video_id: str,
    author_id: str,
    text: str = "a comment",
    published_at: str = "2024-05-01T00:00:00Z",
    like_count: int = 0,
) -> dict:
    return {
        "id": comment_id, "thread_id": f"thread-{comment_id}", "video_id": video_id,
        "author_id": author_id, "text": text, "like_count": like_count,
        "total_reply_count": 0, "published_at": published_at,
        "youtube_updated_at": published_at,
    }


class CommentsTestCase(unittest.TestCase):
    """Runs against a throwaway SQLite file so the app database is never touched."""

    def setUp(self) -> None:
        tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmpdir.cleanup)

        patcher = mock.patch.object(connection, "_DB_PATH", Path(tmpdir.name) / "test.db")
        self.addCleanup(patcher.stop)
        patcher.start()

        database.init_db()

        app = FastAPI()
        app.include_router(comments_router)
        self.client = TestClient(app)


class SchemaTest(CommentsTestCase):
    def test_repeated_init_db_is_idempotent(self) -> None:
        database.init_db()
        database.upsert_video(_video("v1", "A"))
        database.upsert_comment_author(_author("channel:UC1", "Ann", "UC1"))
        database.upsert_comment(_comment("c1", "v1", "channel:UC1"))

        items, total = database.get_comments()
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["id"], "c1")

    def test_comment_requires_an_existing_video(self) -> None:
        database.upsert_comment_author(_author("channel:UC1", "Ann", "UC1"))

        with self.assertRaises(sqlite3.IntegrityError):
            database.upsert_comment(_comment("c1", "missing-video", "channel:UC1"))

    def test_comment_requires_an_existing_author(self) -> None:
        database.upsert_video(_video("v1", "A"))

        with self.assertRaises(sqlite3.IntegrityError):
            database.upsert_comment(_comment("c1", "v1", "channel:nobody"))

    def test_deleting_a_video_cascades_to_its_comments_only(self) -> None:
        database.upsert_video(_video("v1", "A"))
        database.upsert_video(_video("v2", "B"))
        database.upsert_comment_author(_author("channel:UC1", "Ann", "UC1"))
        database.upsert_comment(_comment("c1", "v1", "channel:UC1"))
        database.upsert_comment(_comment("c2", "v2", "channel:UC1"))

        database.delete_videos_not_in(["v2"])

        items, total = database.get_comments()
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["id"], "c2")

    def test_a_referenced_author_cannot_be_deleted(self) -> None:
        database.upsert_video(_video("v1", "A"))
        database.upsert_comment_author(_author("channel:UC1", "Ann", "UC1"))
        database.upsert_comment(_comment("c1", "v1", "channel:UC1"))

        with self.assertRaises(sqlite3.IntegrityError):
            with connection.get_connection() as conn:
                conn.execute("DELETE FROM comment_authors WHERE id = 'channel:UC1'")

    def test_negative_counts_are_rejected(self) -> None:
        database.upsert_video(_video("v1", "A"))
        database.upsert_comment_author(_author("channel:UC1", "Ann", "UC1"))

        with self.assertRaises(sqlite3.IntegrityError):
            database.upsert_comment({**_comment("c1", "v1", "channel:UC1"), "like_count": -1})
        with self.assertRaises(sqlite3.IntegrityError):
            database.upsert_comment(
                {**_comment("c2", "v1", "channel:UC1"), "total_reply_count": -1}
            )

    def test_youtube_channel_id_is_unique(self) -> None:
        database.upsert_comment_author(_author("channel:UC1", "Ann", "UC1"))

        with self.assertRaises(sqlite3.IntegrityError):
            database.upsert_comment_author(_author("channel:other", "Imposter", "UC1"))


class AuthorIdentityTest(CommentsTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_video(_video("v1", "A"))

    def test_one_author_is_reused_across_comments_and_refreshed(self) -> None:
        database.upsert_comment_author(_author("channel:UC1", "Old Name", "UC1"))
        database.upsert_comment(_comment("c1", "v1", "channel:UC1"))
        database.upsert_comment_author(_author("channel:UC1", "New Name", "UC1"))
        database.upsert_comment(_comment("c2", "v1", "channel:UC1"))

        items, total = database.get_comments()
        self.assertEqual(total, 2)
        self.assertEqual({item["author_display_name"] for item in items}, {"New Name"})
        with connection.get_connection() as conn:
            authors = conn.execute("SELECT COUNT(*) FROM comment_authors").fetchone()[0]
        self.assertEqual(authors, 1)

    def test_two_authorless_commenters_sharing_a_name_stay_separate(self) -> None:
        database.upsert_comment_author(_author("comment:c1", "Some Person"))
        database.upsert_comment(_comment("c1", "v1", "comment:c1"))
        database.upsert_comment_author(_author("comment:c2", "Some Person"))
        database.upsert_comment(_comment("c2", "v1", "comment:c2"))

        with connection.get_connection() as conn:
            authors = conn.execute("SELECT COUNT(*) FROM comment_authors").fetchone()[0]
        self.assertEqual(authors, 2)

    def test_orphan_cleanup_removes_only_unreferenced_authors(self) -> None:
        database.upsert_comment_author(_author("channel:UC1", "Kept", "UC1"))
        database.upsert_comment_author(_author("channel:UC2", "Orphan", "UC2"))
        database.upsert_comment(_comment("c1", "v1", "channel:UC1"))

        deleted = database.delete_orphan_comment_authors()

        self.assertEqual(deleted, 1)
        items, _total = database.get_comments()
        self.assertEqual(items[0]["author_display_name"], "Kept")

    def test_known_comment_ids_are_scoped_to_one_video(self) -> None:
        database.upsert_video(_video("v2", "B"))
        database.upsert_comment_author(_author("channel:UC1", "Ann", "UC1"))
        database.upsert_comment(_comment("c1", "v1", "channel:UC1"))
        database.upsert_comment(_comment("c2", "v2", "channel:UC1"))

        self.assertEqual(database.get_comment_ids_for_video("v1"), {"c1"})
        self.assertEqual(database.get_comment_ids_for_video("v-none"), set())


class SeededCommentsTestCase(CommentsTestCase):
    """Two videos in one playlist plus one outside it, with comments across both."""

    def setUp(self) -> None:
        super().setUp()
        database.upsert_video(_video("v-in", "Series Episode 1"))
        database.upsert_video(_video("v-also-in", "Series Episode 2", content_type="short"))
        database.upsert_video(_video("v-out", "Unrelated Vlog"))

        database.upsert_playlist({
            "id": "p1", "title": "Series", "description": "", "published_at": None,
            "thumbnail_url": None, "item_count": 2,
        })
        # v-in is listed twice on purpose: duplicate membership must not duplicate rows.
        for item_id, video_id in (("i1", "v-in"), ("i2", "v-also-in"), ("i3", "v-in")):
            database.upsert_playlist_item({
                "id": item_id, "playlist_id": "p1", "video_id": video_id, "position": 0,
            })

        database.upsert_comment_author(_author("channel:UC1", "Ann Author", "UC1"))
        database.upsert_comment_author(_author("channel:UC2", "Bob Bloggs", "UC2"))

        database.upsert_comment(_comment(
            "c-old", "v-in", "channel:UC1", text="first thoughts",
            published_at="2024-01-10T00:00:00Z", like_count=5,
        ))
        database.upsert_comment(_comment(
            "c-mid", "v-also-in", "channel:UC2", text="LOVED this one",
            published_at="2024-06-15T12:00:00Z", like_count=99,
        ))
        database.upsert_comment(_comment(
            "c-new", "v-out", "channel:UC1", text="unrelated thoughts",
            published_at="2024-12-31T00:00:00Z", like_count=1,
        ))

    def ids(self, response_json: dict) -> list[str]:
        return [item["id"] for item in response_json["items"]]


class ChannelCommentsRouteTest(SeededCommentsTestCase):
    def test_returns_the_standard_paginated_envelope_newest_first(self) -> None:
        body = self.client.get("/comments").json()

        self.assertEqual(self.ids(body), ["c-new", "c-mid", "c-old"])
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 50)

    def test_joins_author_and_video_metadata_onto_each_comment(self) -> None:
        item = self.client.get("/comments").json()["items"][0]

        self.assertEqual(item["author_display_name"], "Ann Author")
        self.assertEqual(item["author_youtube_channel_id"], "UC1")
        self.assertEqual(item["video_title"], "Unrelated Vlog")
        self.assertEqual(item["video_content_type"], "video")
        self.assertIn("video_thumbnail_url", item)

    def test_sorts_oldest_first(self) -> None:
        body = self.client.get("/comments", params={"sort_by": "oldest"}).json()

        self.assertEqual(self.ids(body), ["c-old", "c-mid", "c-new"])

    def test_sorts_by_likes(self) -> None:
        body = self.client.get("/comments", params={"sort_by": "likes"}).json()

        self.assertEqual(self.ids(body), ["c-mid", "c-old", "c-new"])

    def test_filters_by_comment_text_case_insensitively(self) -> None:
        body = self.client.get("/comments", params={"text": "loved"}).json()

        self.assertEqual(self.ids(body), ["c-mid"])

    def test_filters_by_video_title(self) -> None:
        body = self.client.get("/comments", params={"video_title": "series"}).json()

        self.assertEqual(sorted(self.ids(body)), ["c-mid", "c-old"])

    def test_filters_by_author_display_name(self) -> None:
        body = self.client.get("/comments", params={"author": "bloggs"}).json()

        self.assertEqual(self.ids(body), ["c-mid"])

    def test_filters_by_content_type(self) -> None:
        body = self.client.get("/comments", params={"content_type": "short"}).json()

        self.assertEqual(self.ids(body), ["c-mid"])

    def test_end_date_is_inclusive_of_the_whole_day(self) -> None:
        body = self.client.get(
            "/comments", params={"start_date": "2024-01-10", "end_date": "2024-06-15"}
        ).json()

        self.assertEqual(sorted(self.ids(body)), ["c-mid", "c-old"])

    def test_combines_filters(self) -> None:
        body = self.client.get(
            "/comments", params={"author": "ann", "video_title": "series"}
        ).json()

        self.assertEqual(self.ids(body), ["c-old"])

    def test_injection_looking_input_is_bound_not_interpreted(self) -> None:
        body = self.client.get("/comments", params={"text": "'; DROP TABLE comments;--"}).json()

        self.assertEqual(body["total"], 0)
        self.assertEqual(self.client.get("/comments").json()["total"], 3)

    def test_paginates_with_a_stable_total(self) -> None:
        first = self.client.get("/comments", params={"page": 1, "page_size": 2}).json()
        second = self.client.get("/comments", params={"page": 2, "page_size": 2}).json()

        self.assertEqual(self.ids(first), ["c-new", "c-mid"])
        self.assertEqual(self.ids(second), ["c-old"])
        self.assertEqual(first["total"], second["total"])

    def test_page_past_the_end_is_empty_not_an_error(self) -> None:
        body = self.client.get("/comments", params={"page": 9}).json()

        self.assertEqual(body["items"], [])
        self.assertEqual(body["total"], 3)


class ScopedCommentsRouteTest(SeededCommentsTestCase):
    def test_video_scope_excludes_other_videos_comments(self) -> None:
        body = self.client.get("/comments/videos/v-in").json()

        self.assertEqual(self.ids(body), ["c-old"])
        self.assertEqual(body["total"], 1)

    def test_playlist_scope_counts_a_duplicated_member_video_once(self) -> None:
        body = self.client.get("/comments/playlists/p1").json()

        self.assertEqual(self.ids(body), ["c-mid", "c-old"])
        self.assertEqual(body["total"], 2)

    def test_playlist_scope_excludes_comments_on_non_member_videos(self) -> None:
        body = self.client.get("/comments/playlists/p1").json()

        self.assertNotIn("c-new", self.ids(body))

    def test_scoped_filters_and_sorts_still_apply(self) -> None:
        body = self.client.get(
            "/comments/playlists/p1", params={"sort_by": "oldest", "author": "ann"}
        ).json()

        self.assertEqual(self.ids(body), ["c-old"])

    def test_unknown_video_is_not_found(self) -> None:
        response = self.client.get("/comments/videos/nope")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Video not found")

    def test_unknown_playlist_is_not_found(self) -> None:
        response = self.client.get("/comments/playlists/nope")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Playlist not found")


class RequestValidationTest(SeededCommentsTestCase):
    def test_invalid_sort_is_unprocessable(self) -> None:
        self.assertEqual(self.client.get("/comments", params={"sort_by": "funniest"}).status_code, 422)

    def test_page_below_one_is_unprocessable(self) -> None:
        self.assertEqual(self.client.get("/comments", params={"page": 0}).status_code, 422)

    def test_page_size_above_the_maximum_is_unprocessable(self) -> None:
        self.assertEqual(self.client.get("/comments", params={"page_size": 500}).status_code, 422)

    def test_comments_are_read_only(self) -> None:
        for path in ("/comments", "/comments/videos/v-in", "/comments/playlists/p1"):
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path)
                    self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
