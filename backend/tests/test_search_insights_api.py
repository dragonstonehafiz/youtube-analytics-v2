from __future__ import annotations

import unittest

import database
from routes.analytics import router as analytics_router
from tests.support import IsolatedDatabaseTestCase, create_test_client, make_video


class SearchInsightsApiTestCase(IsolatedDatabaseTestCase):
    """Runs against a throwaway SQLite file so the app database is never touched."""

    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(analytics_router)
        self._seed()

    def _seed(self) -> None:
        """Two videos in a playlist (one duplicate, one dangling member) plus a third,
        unrelated video, each with search-term rows across two months."""
        database.upsert_video(make_video("v-in", "My SERIES Episode 1", content_type="video", privacy_status="public"))
        database.upsert_video(make_video("v-out", "Unrelated Vlog", content_type="short", privacy_status="private"))

        database.upsert_search_terms("v-in", "2024-01", [
            {"search_term": "cats", "views": 10},
            {"search_term": "dogs", "views": 5},
        ])
        database.upsert_search_terms("v-out", "2024-01", [{"search_term": "cats", "views": 3}])

        database.upsert_playlist({
            "id": "p1", "title": "Playlist", "description": "",
            "published_at": "2024-01-01T00:00:00Z", "thumbnail_url": "", "item_count": 1,
        })
        database.upsert_playlist_item({"id": "pi1", "playlist_id": "p1", "video_id": "v-in", "position": 0})
        database.upsert_playlist_item({"id": "pi2", "playlist_id": "p1", "video_id": "v-in", "position": 1})
        database.upsert_playlist_item({"id": "pi3", "playlist_id": "p1", "video_id": "missing-video", "position": 2})

    def _get(self, path: str, **params: str) -> dict:
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    DATE_RANGE = {"start_date": "2024-01-01", "end_date": "2024-01-31"}


class ChannelSearchInsightsTest(SearchInsightsApiTestCase):
    def test_terms_sum_across_channel(self) -> None:
        body = self._get("/analytics/search-insights", **self.DATE_RANGE)
        by_term = {item["search_term"]: item["views"] for item in body["items"]}
        self.assertEqual(by_term["cats"], 13)
        self.assertEqual(by_term["dogs"], 5)

    def test_top_endpoint_caps_at_ten(self) -> None:
        body = self._get("/analytics/search-insights/top", **self.DATE_RANGE)
        self.assertLessEqual(len(body["items"]), 10)

    def test_videos_by_search_term_returns_only_matching_videos(self) -> None:
        body = self._get("/analytics/search-insights/videos", **self.DATE_RANGE, search_term="cats")
        self.assertEqual({v["id"] for v in body["items"]}, {"v-in", "v-out"})

    def test_videos_by_search_term_requires_the_query_param(self) -> None:
        response = self.client.get("/analytics/search-insights/videos", params=self.DATE_RANGE)
        self.assertEqual(response.status_code, 422)

    def test_content_type_filter_narrows_results(self) -> None:
        body = self._get("/analytics/search-insights", **self.DATE_RANGE, content_type="short")
        self.assertEqual([(i["search_term"], i["views"]) for i in body["items"]], [("cats", 3)])

    def test_missing_dates_returns_all_time_items(self) -> None:
        body = self._get("/analytics/search-insights")
        by_term = {item["search_term"]: item["views"] for item in body["items"]}
        self.assertEqual(by_term["cats"], 13)
        self.assertEqual(by_term["dogs"], 5)


class PlaylistSearchInsightsTest(SearchInsightsApiTestCase):
    def test_scopes_to_deduplicated_playlist_members(self) -> None:
        body = self._get("/analytics/playlists/p1/search-insights", **self.DATE_RANGE)
        by_term = {item["search_term"]: item["views"] for item in body["items"]}
        self.assertEqual(by_term, {"cats": 10, "dogs": 5})

    def test_videos_by_search_term_scoped_to_playlist(self) -> None:
        body = self._get("/analytics/playlists/p1/search-insights/videos", **self.DATE_RANGE, search_term="cats")
        self.assertEqual({v["id"] for v in body["items"]}, {"v-in"})

    def test_unknown_playlist_is_404(self) -> None:
        response = self.client.get("/analytics/playlists/missing/search-insights", params=self.DATE_RANGE)
        self.assertEqual(response.status_code, 404)

    def test_empty_playlist_returns_no_items(self) -> None:
        database.upsert_playlist({
            "id": "p-empty", "title": "Empty", "description": "",
            "published_at": "2024-01-01T00:00:00Z", "thumbnail_url": "", "item_count": 0,
        })
        body = self._get("/analytics/playlists/p-empty/search-insights", **self.DATE_RANGE)
        self.assertEqual(body["items"], [])


class VideoSearchInsightsTest(SearchInsightsApiTestCase):
    def test_scopes_to_the_single_video(self) -> None:
        body = self._get("/analytics/videos/v-in/search-insights", **self.DATE_RANGE)
        by_term = {item["search_term"]: item["views"] for item in body["items"]}
        self.assertEqual(by_term, {"cats": 10, "dogs": 5})

    def test_unknown_video_is_404(self) -> None:
        response = self.client.get("/analytics/videos/missing/search-insights", params=self.DATE_RANGE)
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
