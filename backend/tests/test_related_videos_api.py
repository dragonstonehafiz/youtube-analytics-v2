from __future__ import annotations

import database
from routes.analytics import router as analytics_router
from tests.support import IsolatedDatabaseTestCase, create_test_client, make_video


class RelatedVideosApiTestCase(IsolatedDatabaseTestCase):
    """Runs the five Related Video reporting routes against a throwaway database with
    an owned target, a playlist, and referrers spanning owned/external/unresolved."""

    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(analytics_router)
        self._seed()

    def _seed(self) -> None:
        database.upsert_own_video(make_video("v-1", "Target One", content_type="video", privacy_status="public"))
        database.upsert_own_video(make_video("v-2", "Target Two", content_type="short", privacy_status="private"))
        database.upsert_own_video(make_video("ref-mine", "My Own Referrer"))
        database.upsert_related_video(make_video("ref-ext", "External Referrer"), own=False)

        database.upsert_playlist({
            "id": "p-1", "title": "Playlist", "description": "",
            "published_at": "2024-01-01T00:00:00Z", "thumbnail_url": "", "item_count": 1,
        })
        database.upsert_playlist_item({"id": "pi-1", "playlist_id": "p-1", "video_id": "v-1", "position": 0})

        database.upsert_related_videos("v-1", "2024-01", [
            {"referrer_video_id": "ref-mine", "views": 10},
            {"referrer_video_id": "ref-ext", "views": 7},
            {"referrer_video_id": "ref-unresolved", "views": 3},
        ])
        database.upsert_related_videos("v-2", "2024-01", [
            {"referrer_video_id": "ref-mine", "views": 4},
        ])


DATE_RANGE = {"start_date": "2024-01-15", "end_date": "2024-01-20"}


class ChannelReferrersRouteTest(RelatedVideosApiTestCase):
    def test_own_true_returns_only_confirmed_owned_referrers(self) -> None:
        body = self.client.get("/analytics/related-videos/referrers", params={**DATE_RANGE, "own": "true"}).json()
        self.assertEqual([i["referrer_video_id"] for i in body["items"]], ["ref-mine"])
        self.assertEqual(body["items"][0]["views"], 14)

    def test_own_false_includes_external_and_unresolved(self) -> None:
        body = self.client.get("/analytics/related-videos/referrers", params={**DATE_RANGE, "own": "false"}).json()
        ids = {i["referrer_video_id"] for i in body["items"]}
        self.assertEqual(ids, {"ref-ext", "ref-unresolved"})

    def test_total_named_views_is_independent_of_own_and_limit(self) -> None:
        own_true = self.client.get(
            "/analytics/related-videos/referrers", params={**DATE_RANGE, "own": "true", "limit": 1}
        ).json()
        own_false = self.client.get(
            "/analytics/related-videos/referrers", params={**DATE_RANGE, "own": "false"}
        ).json()
        self.assertEqual(own_true["total_named_views"], 24)
        self.assertEqual(own_false["total_named_views"], 24)

    def test_own_is_required(self) -> None:
        response = self.client.get("/analytics/related-videos/referrers", params=DATE_RANGE)
        self.assertEqual(response.status_code, 422)

    def test_envelope_has_no_extra_fields(self) -> None:
        body = self.client.get("/analytics/related-videos/referrers", params={**DATE_RANGE, "own": "true"}).json()
        self.assertEqual(set(body), {"items", "total_named_views"})
        self.assertEqual(set(body["items"][0]), {"referrer_video_id", "title", "thumbnail_url", "referrer_own", "views"})

    def test_unresolved_referrer_metadata_is_null_not_false(self) -> None:
        body = self.client.get("/analytics/related-videos/referrers", params={**DATE_RANGE, "own": "false"}).json()
        by_id = {i["referrer_video_id"]: i for i in body["items"]}
        self.assertIsNone(by_id["ref-unresolved"]["title"])
        self.assertIsNone(by_id["ref-unresolved"]["thumbnail_url"])
        self.assertIsNone(by_id["ref-unresolved"]["referrer_own"])

    def test_referrer_own_is_exact_json_boolean(self) -> None:
        body = self.client.get("/analytics/related-videos/referrers", params={**DATE_RANGE, "own": "false"}).json()
        by_id = {i["referrer_video_id"]: i for i in body["items"]}
        self.assertIs(by_id["ref-ext"]["referrer_own"], False)

    def test_content_type_and_privacy_filter_the_target_side(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/referrers",
            params={**DATE_RANGE, "own": "true", "content_type": "short", "privacy_status": "private"},
        ).json()
        self.assertEqual(body["items"][0]["views"], 4)

    def test_inclusive_month_mapping_for_boundary_dates(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/referrers",
            params={"start_date": "2024-01-18", "end_date": "2024-01-19", "own": "true"},
        ).json()
        self.assertEqual(body["items"][0]["views"], 14)

    def test_out_of_range_dates_return_no_rows(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/referrers",
            params={"start_date": "2024-02-01", "end_date": "2024-02-28", "own": "true"},
        ).json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["total_named_views"], 0)


class ChannelDestinationsRouteTest(RelatedVideosApiTestCase):
    def test_returns_destinations_for_a_referrer(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/destinations", params={**DATE_RANGE, "referrer_video_id": "ref-mine"}
        ).json()
        self.assertEqual({i["target_video_id"] for i in body["items"]}, {"v-1", "v-2"})

    def test_works_identically_for_an_external_referrer(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/destinations", params={**DATE_RANGE, "referrer_video_id": "ref-ext"}
        ).json()
        self.assertEqual([i["target_video_id"] for i in body["items"]], ["v-1"])

    def test_referrer_video_id_is_required(self) -> None:
        response = self.client.get("/analytics/related-videos/destinations", params=DATE_RANGE)
        self.assertEqual(response.status_code, 422)

    def test_limit_caps_results(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/destinations",
            params={**DATE_RANGE, "referrer_video_id": "ref-mine", "limit": 1},
        ).json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["target_video_id"], "v-1")

    def test_envelope_has_no_extra_fields(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/destinations", params={**DATE_RANGE, "referrer_video_id": "ref-mine"}
        ).json()
        self.assertEqual(set(body), {"items"})
        self.assertEqual(set(body["items"][0]), {"target_video_id", "title", "thumbnail_url", "content_type", "views"})

    def test_unknown_referrer_returns_empty_items(self) -> None:
        body = self.client.get(
            "/analytics/related-videos/destinations", params={**DATE_RANGE, "referrer_video_id": "does-not-exist"}
        ).json()
        self.assertEqual(body["items"], [])


class PlaylistReferrersRouteTest(RelatedVideosApiTestCase):
    def test_scopes_to_playlist_members(self) -> None:
        body = self.client.get(
            "/analytics/playlists/p-1/related-videos/referrers", params={**DATE_RANGE, "own": "true"}
        ).json()
        self.assertEqual(body["items"][0]["views"], 10)

    def test_unknown_playlist_is_404(self) -> None:
        response = self.client.get(
            "/analytics/playlists/does-not-exist/related-videos/referrers", params={**DATE_RANGE, "own": "true"}
        )
        self.assertEqual(response.status_code, 404)

    def test_own_is_required(self) -> None:
        response = self.client.get("/analytics/playlists/p-1/related-videos/referrers", params=DATE_RANGE)
        self.assertEqual(response.status_code, 422)


class PlaylistDestinationsRouteTest(RelatedVideosApiTestCase):
    def test_scopes_to_playlist_members(self) -> None:
        body = self.client.get(
            "/analytics/playlists/p-1/related-videos/destinations",
            params={**DATE_RANGE, "referrer_video_id": "ref-mine"},
        ).json()
        self.assertEqual([i["target_video_id"] for i in body["items"]], ["v-1"])

    def test_unknown_playlist_is_404(self) -> None:
        response = self.client.get(
            "/analytics/playlists/does-not-exist/related-videos/destinations",
            params={**DATE_RANGE, "referrer_video_id": "ref-mine"},
        )
        self.assertEqual(response.status_code, 404)

    def test_empty_playlist_returns_no_destinations(self) -> None:
        database.upsert_playlist({
            "id": "p-empty", "title": "Empty", "description": "",
            "published_at": "2024-01-01T00:00:00Z", "thumbnail_url": "", "item_count": 0,
        })
        body = self.client.get(
            "/analytics/playlists/p-empty/related-videos/destinations",
            params={**DATE_RANGE, "referrer_video_id": "ref-mine"},
        ).json()
        self.assertEqual(body["items"], [])


class VideoReferrersRouteTest(RelatedVideosApiTestCase):
    def test_scopes_to_a_single_video(self) -> None:
        body = self.client.get(
            "/analytics/videos/v-1/related-videos/referrers", params={**DATE_RANGE, "own": "true"}
        ).json()
        self.assertEqual(body["items"][0]["views"], 10)

    def test_unknown_video_is_404(self) -> None:
        response = self.client.get(
            "/analytics/videos/does-not-exist/related-videos/referrers", params={**DATE_RANGE, "own": "true"}
        )
        self.assertEqual(response.status_code, 404)

    def test_external_video_is_404(self) -> None:
        response = self.client.get(
            "/analytics/videos/ref-ext/related-videos/referrers", params={**DATE_RANGE, "own": "true"}
        )
        self.assertEqual(response.status_code, 404)

    def test_own_is_required(self) -> None:
        response = self.client.get("/analytics/videos/v-1/related-videos/referrers", params=DATE_RANGE)
        self.assertEqual(response.status_code, 422)

    def test_there_is_no_destinations_route_for_a_single_video(self) -> None:
        response = self.client.get(
            "/analytics/videos/v-1/related-videos/destinations", params={**DATE_RANGE, "referrer_video_id": "v-1"}
        )
        self.assertEqual(response.status_code, 404)
