from __future__ import annotations

import sqlite3
import unittest

import database
from database import Comment, CommentAuthor, NotExists, Playlist, PlaylistItem, Video, writer
from database import Comment, connection, reader
from routes.comments import router as comments_router
from tests.support import FIXED_NOW, IsolatedDatabaseTestCase, create_test_client


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


class CommentsTestCase(IsolatedDatabaseTestCase):
    """Runs against a throwaway SQLite file so the app database is never touched."""

    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(comments_router)

    def _comments(self) -> tuple[list[dict], int]:
        """Return the channel-wide comment feed's items and total."""
        body = self.client.get("/comments").json()
        return body["items"], body["total"]


class SchemaTest(CommentsTestCase):
    def test_repeated_init_db_is_idempotent(self) -> None:
        database.init_db()
        writer.write(Video.from_dict({**_video("v1", "A"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c1", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))

        items, total = self._comments()
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["id"], "c1")

    def test_comment_requires_an_existing_video(self) -> None:
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann", "UC1"), "updated_at": FIXED_NOW}))

        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(Comment.from_dict({**_comment("c1", "missing-video", "channel:UC1"), "updated_at": FIXED_NOW}))

    def test_comment_requires_an_existing_author(self) -> None:
        writer.write(Video.from_dict({**_video("v1", "A"), "own": True, "updated_at": FIXED_NOW}))

        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(Comment.from_dict({**_comment("c1", "v1", "channel:nobody"), "updated_at": FIXED_NOW}))

    def test_deleting_a_video_cascades_to_its_comments_only(self) -> None:
        writer.write(Video.from_dict({**_video("v1", "A"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(Video.from_dict({**_video("v2", "B"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c1", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c2", "v2", "channel:UC1"), "updated_at": FIXED_NOW}))

        writer.delete(Video, where=[("own", "=", True), ("id", "NOT IN", ["v2"])])

        items, total = self._comments()
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["id"], "c2")

    def test_a_referenced_author_cannot_be_deleted(self) -> None:
        writer.write(Video.from_dict({**_video("v1", "A"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c1", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))

        with self.assertRaises(sqlite3.IntegrityError):
            with connection.get_connection() as conn:
                conn.execute("DELETE FROM comment_authors WHERE id = 'channel:UC1'")

    def test_negative_counts_are_rejected(self) -> None:
        writer.write(Video.from_dict({**_video("v1", "A"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann", "UC1"), "updated_at": FIXED_NOW}))

        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(Comment.from_dict({**{**_comment("c1", "v1", "channel:UC1"), "like_count": -1}, "updated_at": FIXED_NOW}))
        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(Comment.from_dict({**{**_comment("c2", "v1", "channel:UC1"), "total_reply_count": -1}, "updated_at": FIXED_NOW}))

    def test_youtube_channel_id_is_unique(self) -> None:
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann", "UC1"), "updated_at": FIXED_NOW}))

        with self.assertRaises(sqlite3.IntegrityError):
            writer.write(CommentAuthor.from_dict({**_author("channel:other", "Imposter", "UC1"), "updated_at": FIXED_NOW}))


class AuthorIdentityTest(CommentsTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write(Video.from_dict({**_video("v1", "A"), "own": True, "updated_at": FIXED_NOW}))

    def test_one_author_is_reused_across_comments_and_refreshed(self) -> None:
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Old Name", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c1", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "New Name", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c2", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))

        items, total = self._comments()
        self.assertEqual(total, 2)
        self.assertEqual({item["author_display_name"] for item in items}, {"New Name"})
        with connection.get_connection() as conn:
            authors = conn.execute("SELECT COUNT(*) FROM comment_authors").fetchone()[0]
        self.assertEqual(authors, 1)

    def test_two_authorless_commenters_sharing_a_name_stay_separate(self) -> None:
        writer.write(CommentAuthor.from_dict({**_author("comment:c1", "Some Person"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c1", "v1", "comment:c1"), "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("comment:c2", "Some Person"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c2", "v1", "comment:c2"), "updated_at": FIXED_NOW}))

        with connection.get_connection() as conn:
            authors = conn.execute("SELECT COUNT(*) FROM comment_authors").fetchone()[0]
        self.assertEqual(authors, 2)

    def test_orphan_cleanup_removes_only_unreferenced_authors(self) -> None:
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Kept", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC2", "Orphan", "UC2"), "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC3", "Also kept", "UC3"), "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("comment:c9", "Another orphan"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c1", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c2", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c3", "v1", "channel:UC3"), "updated_at": FIXED_NOW}))

        deleted = writer.delete(CommentAuthor, where=[NotExists(Comment, (("author_id", "id"),))])

        self.assertEqual(deleted, 2)
        items, _total = self._comments()
        self.assertEqual({item["author_display_name"] for item in items}, {"Kept", "Also kept"})
        remaining = {author.id for author in reader.select(CommentAuthor, ("id",))}
        self.assertEqual(remaining, {"channel:UC1", "channel:UC3"})

    def test_known_comment_ids_are_scoped_to_one_video(self) -> None:
        writer.write(Video.from_dict({**_video("v2", "B"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c1", "v1", "channel:UC1"), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment("c2", "v2", "channel:UC1"), "updated_at": FIXED_NOW}))

        def known_ids(video_id: str) -> set[str | None]:
            return {c.id for c in reader.select(Comment, ("id",), where=[("video_id", "=", video_id)])}

        self.assertEqual(known_ids("v1"), {"c1"})
        self.assertEqual(known_ids("v-none"), set())


class SeededCommentsTestCase(CommentsTestCase):
    """Two videos in one playlist plus one outside it, with comments across both."""

    def setUp(self) -> None:
        super().setUp()
        writer.write(Video.from_dict({**_video("v-in", "Series Episode 1"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(Video.from_dict({**_video("v-also-in", "Series Episode 2", content_type="short"), "own": True, "updated_at": FIXED_NOW}))
        writer.write(Video.from_dict({**_video("v-out", "Unrelated Vlog"), "own": True, "updated_at": FIXED_NOW}))

        writer.write(Playlist.from_dict({**{
            "id": "p1", "title": "Series", "description": "", "published_at": None,
            "thumbnail_url": None, "item_count": 2,
        }, "updated_at": FIXED_NOW}))
        # v-in is listed twice on purpose: duplicate membership must not duplicate rows.
        for item_id, video_id in (("i1", "v-in"), ("i2", "v-also-in"), ("i3", "v-in")):
            writer.write(PlaylistItem.from_dict({**{
                "id": item_id, "playlist_id": "p1", "video_id": video_id, "position": 0,
            }, "updated_at": FIXED_NOW}))

        writer.write(CommentAuthor.from_dict({**_author("channel:UC1", "Ann Author", "UC1"), "updated_at": FIXED_NOW}))
        writer.write(CommentAuthor.from_dict({**_author("channel:UC2", "Bob Bloggs", "UC2"), "updated_at": FIXED_NOW}))

        writer.write(Comment.from_dict({**_comment(
            "c-old", "v-in", "channel:UC1", text="first thoughts",
            published_at="2024-01-10T00:00:00Z", like_count=5,
        ), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment(
            "c-mid", "v-also-in", "channel:UC2", text="LOVED this one",
            published_at="2024-06-15T12:00:00Z", like_count=99,
        ), "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment(
            "c-new", "v-out", "channel:UC1", text="unrelated thoughts",
            published_at="2024-12-31T00:00:00Z", like_count=1,
        ), "updated_at": FIXED_NOW}))

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

    def test_filters_by_video_id(self) -> None:
        body = self.client.get("/comments", params={"video_title": "v-out"}).json()

        self.assertEqual(self.ids(body), ["c-new"])

    def test_video_id_filter_combines_with_other_filters_to_exclude_a_match(self) -> None:
        body = self.client.get(
            "/comments", params={"video_title": "v-out", "author": "bloggs"}
        ).json()

        self.assertEqual(body["items"], [])
        self.assertEqual(body["total"], 0)

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

    def test_playlist_scope_filters_by_video_id(self) -> None:
        body = self.client.get("/comments/playlists/p1", params={"video_title": "v-also-in"}).json()

        self.assertEqual(self.ids(body), ["c-mid"])
        self.assertEqual(body["total"], 1)

    def test_playlist_scope_video_id_of_non_member_video_matches_nothing(self) -> None:
        body = self.client.get("/comments/playlists/p1", params={"video_title": "v-out"}).json()

        self.assertEqual(body["items"], [])
        self.assertEqual(body["total"], 0)

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


class ExternalVideoExclusionRouteTest(SeededCommentsTestCase):
    """An external (own=0) video's comments must never surface through the live HTTP
    routes, reaffirming Step 2's database-layer exclusion end-to-end."""

    def setUp(self) -> None:
        super().setUp()
        writer.write(Video.from_dict({**_video("v-ext", "External Video"), "own": False, "updated_at": FIXED_NOW}))
        writer.write(Comment.from_dict({**_comment(
            "c-ext", "v-ext", "channel:UC1", text="external comment",
            published_at="2025-01-01T00:00:00Z", like_count=1000,
        ), "updated_at": FIXED_NOW}))

    def test_channel_comments_exclude_the_external_video(self) -> None:
        body = self.client.get("/comments").json()
        self.assertNotIn("c-ext", self.ids(body))
        self.assertEqual(body["total"], 3)

    def test_video_scoped_route_404s_for_the_external_video(self) -> None:
        response = self.client.get("/comments/videos/v-ext")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
