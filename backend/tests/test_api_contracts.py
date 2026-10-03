from __future__ import annotations

import unittest
from unittest import mock

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute

import sync
from routes import router
from routes._shared import require_found
from tests.support import SeededDatabaseTestCase, create_test_client


class RequireFoundTest(unittest.TestCase):
    def test_only_none_raises_404(self) -> None:
        falsy: tuple[object, ...] = ({}, [], 0, "")
        for item in falsy:
            with self.subTest(item=item):
                self.assertIs(require_found(item, "Video"), item)
        with self.assertRaises(HTTPException) as raised:
            require_found(None, "Playlist")
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Playlist not found")


class SharedScopeRouteSchemaTest(unittest.TestCase):
    def test_channel_routes_have_no_playlist_id_parameter(self) -> None:
        app = FastAPI()
        app.include_router(router)
        paths = app.openapi()["paths"]
        endpoints: dict[object, list[str]] = {}
        for included in router.routes:
            for route in included.original_router.routes:  # type: ignore[attr-defined]
                if isinstance(route, APIRoute):
                    endpoints.setdefault(route.endpoint, []).append(route.path)
        shared = [path for route_paths in endpoints.values() if len(route_paths) > 1 for path in route_paths]
        self.assertEqual(len(shared), 20)
        for path in shared:
            if "{playlist_id}" in path:
                continue
            with self.subTest(path=path):
                params = [p["name"] for p in paths[path]["get"].get("parameters", [])]
                self.assertNotIn("playlist_id", params)


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

    def test_own_field_is_an_exact_json_boolean_not_an_integer(self) -> None:
        body = self.client.get("/videos/v-1").json()
        self.assertIs(body["item"]["own"], True)

        list_body = self.client.get("/videos").json()
        self.assertIs(list_body["items"][0]["own"], True)

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
    server.lifespan — so init_db, the stranded sync-run sweep, and the scheduler are never
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
