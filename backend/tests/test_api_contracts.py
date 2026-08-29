from __future__ import annotations

import unittest
from unittest import mock

import sync
from routes import router
from tests.support import SeededDatabaseTestCase, create_test_client


class ApiContractTestCase(SeededDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(router)


class VideoContractTest(ApiContractTestCase):
    def test_list_videos_envelope(self) -> None:
        body = self.client.get("/videos").json()
        self.assertEqual(set(body), {"items", "total", "page", "page_size"})
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 50)
        self.assertGreater(body["total"], 0)

    def test_get_video_envelope(self) -> None:
        body = self.client.get("/videos/v-1").json()
        self.assertEqual(set(body), {"item"})
        self.assertEqual(body["item"]["id"], "v-1")

    def test_unknown_video_returns_documented_404(self) -> None:
        response = self.client.get("/videos/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Video not found")

    def test_page_below_one_is_422(self) -> None:
        self.assertEqual(self.client.get("/videos", params={"page": 0}).status_code, 422)

    def test_page_size_above_max_is_422(self) -> None:
        self.assertEqual(self.client.get("/videos", params={"page_size": 500}).status_code, 422)

    def test_filtered_list_with_no_matches_is_an_empty_list_not_an_error(self) -> None:
        body = self.client.get("/videos", params={"title": "does-not-exist"}).json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["total"], 0)


class PlaylistContractTest(ApiContractTestCase):
    def test_list_playlists_envelope(self) -> None:
        body = self.client.get("/playlists").json()
        self.assertEqual(set(body), {"items", "total", "page", "page_size"})

    def test_get_playlist_envelope(self) -> None:
        body = self.client.get("/playlists/p-full").json()
        self.assertEqual(set(body), {"item"})
        self.assertEqual(body["item"]["id"], "p-full")

    def test_unknown_playlist_returns_documented_404(self) -> None:
        response = self.client.get("/playlists/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Playlist not found")


class AnalyticsContractTest(ApiContractTestCase):
    DATE_RANGE = {"start_date": "2024-01-01", "end_date": "2024-01-31"}

    def test_aggregated_analytics_envelope(self) -> None:
        body = self.client.get("/analytics/videos", params=self.DATE_RANGE).json()
        self.assertEqual(set(body), {"items"})

    def test_top_videos_envelope(self) -> None:
        body = self.client.get("/analytics/videos/top", params=self.DATE_RANGE).json()
        self.assertEqual(set(body), {"items"})

    def test_traffic_sources_envelope(self) -> None:
        body = self.client.get("/analytics/traffic-sources", params=self.DATE_RANGE).json()
        self.assertEqual(set(body), {"items"})

    def test_top_sort_rejects_an_unsupported_value_with_422(self) -> None:
        response = self.client.get("/analytics/videos/top", params={**self.DATE_RANGE, "sort_by": "bogus"})
        self.assertEqual(response.status_code, 422)


class MetadataContractTest(ApiContractTestCase):
    def test_date_range_envelope(self) -> None:
        body = self.client.get("/meta/date-range").json()
        self.assertEqual(set(body), {"earliest_year"})
        self.assertEqual(body["earliest_year"], 2024)


class NoLifespanTest(ApiContractTestCase):
    """The app under test is built with create_test_client(), which never runs
    server.lifespan — so init_db, mark_incomplete_sync_runs, and the scheduler are never
    invoked by the app itself; the isolated database is populated only by SeededDatabaseTestCase."""

    def test_scheduler_start_is_never_called(self) -> None:
        with mock.patch.object(sync, "start_background_scheduler") as sentinel:
            self.client.get("/videos")
            self.client.get("/playlists")
            sentinel.assert_not_called()

    def test_a_normal_request_succeeds_without_touching_the_scheduler_or_oauth(self) -> None:
        response = self.client.get("/videos")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
