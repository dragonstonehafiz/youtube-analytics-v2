from __future__ import annotations

import unittest

import database
from routes.analytics import router as analytics_router
from routes.videos import router as videos_router
from tests.support import IsolatedDatabaseTestCase, create_test_client


class TitleFilterTestCase(IsolatedDatabaseTestCase):
    """Runs against a throwaway SQLite file so the app database is never touched."""

    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(analytics_router, videos_router)
        self._seed()

    def _seed(self) -> None:
        """Seed two matching-title videos (in and out of the playlist) plus a third,
        differently-titled video, each with analytics and traffic-source rows."""
        database.upsert_video({
            "id": "v-in", "channel_id": "c1", "title": "My SERIES Episode 1",
            "description": "", "published_at": "2024-01-01T00:00:00Z", "duration_seconds": 100,
            "thumbnail_url": "", "content_type": "video", "privacy_status": "public",
            "view_count": 10, "like_count": 1, "comment_count": 0,
        })
        database.upsert_video({
            "id": "v-out", "channel_id": "c1", "title": "My series Episode 2",
            "description": "", "published_at": "2024-01-02T00:00:00Z", "duration_seconds": 100,
            "thumbnail_url": "", "content_type": "video", "privacy_status": "public",
            "view_count": 20, "like_count": 1, "comment_count": 0,
        })
        database.upsert_video({
            "id": "v-other", "channel_id": "c1", "title": "Unrelated Vlog",
            "description": "", "published_at": "2024-01-03T00:00:00Z", "duration_seconds": 100,
            "thumbnail_url": "", "content_type": "short", "privacy_status": "private",
            "view_count": 30, "like_count": 1, "comment_count": 0,
        })

        for video_id, views in (("v-in", 100), ("v-out", 200), ("v-other", 300)):
            database.upsert_video_analytics({
                "video_id": video_id, "date": "2024-01-05", "views": views,
                "watch_time_minutes": 10, "estimated_revenue": 1.0,
                "average_view_duration_seconds": 5, "average_view_percentage": 50.0,
                "likes": 1, "subscribers_gained": 0, "subscribers_lost": 0,
            })
            database.upsert_video_traffic_source({
                "video_id": video_id, "date": "2024-01-05", "traffic_source_type": "SEARCH",
                "views": views, "watch_time_minutes": 10,
            })

        database.upsert_playlist({
            "id": "p1", "title": "Playlist", "description": "",
            "published_at": "2024-01-01T00:00:00Z", "thumbnail_url": "", "item_count": 1,
        })
        database.upsert_playlist_item({"id": "pi1", "playlist_id": "p1", "video_id": "v-in", "position": 0})

    def _get(self, path: str, **params: str) -> dict:
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200)
        return response.json()


class ChannelRouteTitleFilterTest(TitleFilterTestCase):
    def test_aggregated_analytics_matches_case_insensitive_substring(self) -> None:
        body = self._get("/analytics/videos", title="series", start_date="2024-01-01", end_date="2024-01-31")
        total_views = sum(row["views"] for row in body["items"])
        self.assertEqual(total_views, 300)

    def test_aggregated_analytics_excludes_nonmatching_title(self) -> None:
        body = self._get("/analytics/videos", title="vlog", start_date="2024-01-01", end_date="2024-01-31")
        video_ids_by_type = {row["content_type"] for row in body["items"] if row["views"]}
        self.assertIn("short", video_ids_by_type)

    def test_top_videos_by_views_filters_by_title(self) -> None:
        body = self._get("/analytics/videos/top", title="series", start_date="2024-01-01", end_date="2024-01-31")
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {"v-in", "v-out"})

    def test_top_videos_composes_title_with_content_type_and_privacy(self) -> None:
        body = self._get(
            "/analytics/videos/top", title="series", content_type="video", privacy_status="public",
            start_date="2024-01-01", end_date="2024-01-31",
        )
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {"v-in", "v-out"})

    def test_top_videos_no_match_returns_empty(self) -> None:
        body = self._get("/analytics/videos/top", title="nonexistent", start_date="2024-01-01", end_date="2024-01-31")
        self.assertEqual(body["items"], [])

    def test_published_videos_filters_by_title(self) -> None:
        body = self._get("/videos/published", title="series")
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {"v-in", "v-out"})

    def test_traffic_sources_filters_by_title(self) -> None:
        body = self._get("/analytics/traffic-sources", title="series", start_date="2024-01-01", end_date="2024-01-31")
        total_views = sum(row["views"] for row in body["items"])
        self.assertEqual(total_views, 300)

    def test_top_videos_by_traffic_source_filters_by_title(self) -> None:
        body = self._get("/analytics/traffic-sources/top", title="series", start_date="2024-01-01", end_date="2024-01-31")
        ids = {row["id"] for row in body["items"].get("SEARCH", [])}
        self.assertEqual(ids, {"v-in", "v-out"})

    def test_omitted_title_returns_all_videos(self) -> None:
        body = self._get("/analytics/videos/top", start_date="2024-01-01", end_date="2024-01-31")
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {"v-in", "v-out", "v-other"})

    def test_sql_injection_looking_input_is_bound_not_interpolated(self) -> None:
        """A value crafted to look like SQL must be treated as an ordinary substring with no
        matches, and must not break the query or delete data — proving it is bound, not
        string-concatenated into the query."""
        body = self._get(
            "/analytics/videos/top", title="'; DROP TABLE videos; --",
            start_date="2024-01-01", end_date="2024-01-31",
        )
        self.assertEqual(body["items"], [])
        survivors = self._get("/videos/published")
        self.assertEqual({row["id"] for row in survivors["items"]}, {"v-in", "v-out", "v-other"})

    def test_invalid_sort_by_still_returns_422(self) -> None:
        response = self.client.get("/analytics/videos/top", params={"sort_by": "bogus"})
        self.assertEqual(response.status_code, 422)


class PlaylistRouteTitleFilterTest(TitleFilterTestCase):
    def test_playlist_top_videos_matches_in_playlist_video(self) -> None:
        body = self._get("/analytics/playlists/p1/top", title="series", start_date="2024-01-01", end_date="2024-01-31")
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {"v-in"})

    def test_playlist_top_videos_excludes_out_of_playlist_match(self) -> None:
        """v-out's title matches, but it is not a member of playlist p1."""
        body = self._get("/analytics/playlists/p1/top", title="series", start_date="2024-01-01", end_date="2024-01-31")
        ids = {row["id"] for row in body["items"]}
        self.assertNotIn("v-out", ids)

    def test_playlist_aggregated_analytics_stays_scoped_to_playlist(self) -> None:
        body = self._get("/analytics/playlists/p1", title="series", start_date="2024-01-01", end_date="2024-01-31")
        total_views = sum(row["views"] for row in body["items"])
        self.assertEqual(total_views, 100)

    def test_playlist_traffic_sources_stays_scoped_to_playlist(self) -> None:
        body = self._get("/analytics/playlists/p1/traffic-sources", title="series", start_date="2024-01-01", end_date="2024-01-31")
        total_views = sum(row["views"] for row in body["items"])
        self.assertEqual(total_views, 100)

    def test_playlist_top_videos_by_traffic_source_stays_scoped(self) -> None:
        body = self._get(
            "/analytics/playlists/p1/traffic-sources/top", title="series",
            start_date="2024-01-01", end_date="2024-01-31",
        )
        ids = {row["id"] for row in body["items"].get("SEARCH", [])}
        self.assertEqual(ids, {"v-in"})

    def test_published_videos_playlist_scoped_by_title(self) -> None:
        body = self._get("/videos/published", title="series", playlist_id="p1")
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {"v-in"})

    def test_unknown_playlist_still_returns_404(self) -> None:
        response = self.client.get("/analytics/playlists/does-not-exist", params={"title": "series"})
        self.assertEqual(response.status_code, 404)

    def test_omitted_title_backward_compatible(self) -> None:
        body = self._get("/analytics/playlists/p1/top", start_date="2024-01-01", end_date="2024-01-31")
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {"v-in"})


if __name__ == "__main__":
    unittest.main()
