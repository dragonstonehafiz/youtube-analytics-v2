from __future__ import annotations

import unittest

import database
from routes.analytics import router as analytics_router
from tests.support import IsolatedDatabaseTestCase, create_test_client

START_DATE = "2024-01-01"
END_DATE = "2024-01-31"
DATE_RANGE = {"start_date": START_DATE, "end_date": END_DATE}


class VideoScopeTestCase(IsolatedDatabaseTestCase):
    """Runs against a throwaway SQLite file so the app database is never touched.

    The fixture covers duplicate playlist membership, a dangling membership row, a null membership
    row, and an empty playlist, so scoping defects surface as inflated totals or leaked videos.
    """

    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(analytics_router)
        self._seed()

    def _seed(self) -> None:
        """Seed three videos with differing metrics, a populated playlist with anomalous membership,
        and an empty playlist."""
        # v-d is deliberately indistinguishable from v-a under every filter but membership, so a
        # filtered playlist result that leaked channel-wide data would include it.
        videos = (
            ("v-a", "Alpha Episode", "video", "public", "2024-01-01T00:00:00Z"),
            ("v-b", "Beta Episode", "video", "private", "2024-01-02T00:00:00Z"),
            ("v-c", "Gamma Vlog", "short", "public", "2024-01-03T00:00:00Z"),
            ("v-d", "Delta Episode", "video", "public", "2024-01-04T00:00:00Z"),
        )
        for video_id, title, content_type, privacy_status, published_at in videos:
            database.upsert_video({
                "id": video_id, "channel_id": "c1", "title": title,
                "description": "", "published_at": published_at, "duration_seconds": 100,
                "thumbnail_url": "", "content_type": content_type, "privacy_status": privacy_status,
                "view_count": 10, "like_count": 1, "comment_count": 0,
            })

        # v-a ranks first by views, v-b first by watch time, so sort_by is observable under scoping.
        metrics = (
            ("v-a", "2024-01-05", 300, 10),
            ("v-b", "2024-01-05", 200, 600),
            ("v-c", "2024-01-06", 100, 20),
            ("v-d", "2024-01-06", 50, 5),
        )
        for video_id, day, views, watch_time in metrics:
            database.upsert_video_analytics({
                "video_id": video_id, "date": day, "views": views,
                "watch_time_minutes": watch_time, "estimated_revenue": 1.0,
                "average_view_duration_seconds": 5, "average_view_percentage": 50.0,
                "likes": 1, "subscribers_gained": 0, "subscribers_lost": 0,
            })
            for source_type in ("SEARCH", "SUGGESTED"):
                database.upsert_video_traffic_source({
                    "video_id": video_id, "date": day, "traffic_source_type": source_type,
                    "views": views, "watch_time_minutes": watch_time,
                })

        database.upsert_playlist({
            "id": "p-full", "title": "Full", "description": "",
            "published_at": "2024-01-01T00:00:00Z", "thumbnail_url": "", "item_count": 2,
        })
        database.upsert_playlist({
            "id": "p-empty", "title": "Empty", "description": "",
            "published_at": "2024-01-01T00:00:00Z", "thumbnail_url": "", "item_count": 0,
        })
        items: tuple[tuple[str, str, str | None, int], ...] = (
            ("pi-1", "p-full", "v-a", 0),
            ("pi-2", "p-full", "v-a", 1),  # duplicate membership for the same video
            ("pi-3", "p-full", "v-b", 2),
            ("pi-4", "p-full", "missing-video", 3),  # dangling membership
            ("pi-5", "p-full", None, 4),  # null membership
        )
        for item_id, playlist_id, member_id, position in items:
            database.upsert_playlist_item({
                "id": item_id, "playlist_id": playlist_id, "video_id": member_id, "position": position,
            })

    def _get(self, path: str, **params: str) -> dict:
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200)
        return response.json()


class PlaylistVideoIdsTest(VideoScopeTestCase):
    def test_returns_each_valid_member_once(self) -> None:
        self.assertEqual(sorted(database.get_playlist_video_ids("p-full")), ["v-a", "v-b"])

    def test_excludes_dangling_and_null_membership(self) -> None:
        ids = database.get_playlist_video_ids("p-full")
        self.assertNotIn("missing-video", ids)
        self.assertNotIn(None, ids)

    def test_empty_playlist_returns_empty_list(self) -> None:
        self.assertEqual(database.get_playlist_video_ids("p-empty"), [])

    def test_unknown_playlist_returns_empty_list(self) -> None:
        self.assertEqual(database.get_playlist_video_ids("nope"), [])


class AggregatedAnalyticsScopeTest(VideoScopeTestCase):
    def test_omitted_scope_covers_every_video(self) -> None:
        rows = database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE)
        self.assertEqual(sum(row["views"] for row in rows), 650)

    def test_populated_scope_limits_aggregation(self) -> None:
        rows = database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE, video_ids=["v-a", "v-b"])
        self.assertEqual(sum(row["views"] for row in rows), 500)

    def test_single_id_scope_matches_that_video_only(self) -> None:
        rows = database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE, video_ids=["v-c"])
        self.assertEqual(sum(row["views"] for row in rows), 100)

    def test_empty_scope_returns_empty_list(self) -> None:
        self.assertEqual(database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE, video_ids=[]), [])

    def test_scope_accepts_a_set(self) -> None:
        rows = database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE, video_ids={"v-a", "v-b"})
        self.assertEqual(sum(row["views"] for row in rows), 500)

    def test_scope_composes_with_content_type_and_privacy_filters(self) -> None:
        rows = database.get_aggregated_analytics(
            start_date=START_DATE, end_date=END_DATE, content_type="video", privacy_status="public", video_ids=["v-a", "v-b"],
        )
        self.assertEqual(sum(row["views"] for row in rows), 300)

    def test_scope_composes_with_title_filter(self) -> None:
        rows = database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE, title="Episode", video_ids=["v-a", "v-c"])
        self.assertEqual(sum(row["views"] for row in rows), 300)

    def test_zero_fill_shape_is_preserved_under_scope(self) -> None:
        rows = database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE, video_ids=["v-a", "v-b"])
        self.assertEqual([row["date"] for row in rows[:2]], ["2024-01-01", "2024-01-01"])
        self.assertEqual({row["content_type"] for row in rows}, {"video", "short"})
        self.assertEqual(rows[-1]["date"], "2024-01-05")


class TopVideosByViewsScopeTest(VideoScopeTestCase):
    def test_omitted_scope_ranks_every_video(self) -> None:
        rows = database.get_top_videos_by_views(start_date=START_DATE, end_date=END_DATE)
        self.assertEqual([row["id"] for row in rows], ["v-a", "v-b", "v-c", "v-d"])

    def test_populated_scope_limits_ranking(self) -> None:
        rows = database.get_top_videos_by_views(start_date=START_DATE, end_date=END_DATE, video_ids=["v-b", "v-c"])
        self.assertEqual([row["id"] for row in rows], ["v-b", "v-c"])

    def test_empty_scope_returns_empty_list(self) -> None:
        self.assertEqual(database.get_top_videos_by_views(start_date=START_DATE, end_date=END_DATE, video_ids=[]), [])

    def test_watch_time_sort_applies_within_scope(self) -> None:
        rows = database.get_top_videos_by_views(start_date=START_DATE, end_date=END_DATE, sort_by="watch_time", video_ids=["v-a", "v-b"])
        self.assertEqual([row["id"] for row in rows], ["v-b", "v-a"])

    def test_limit_applies_within_scope(self) -> None:
        rows = database.get_top_videos_by_views(start_date=START_DATE, end_date=END_DATE, limit=1, video_ids=["v-a", "v-b"])
        self.assertEqual([row["id"] for row in rows], ["v-a"])

    def test_scope_composes_with_filters(self) -> None:
        rows = database.get_top_videos_by_views(
            start_date=START_DATE, end_date=END_DATE, content_type="video", privacy_status="private",
            title="Episode", video_ids=["v-a", "v-b"],
        )
        self.assertEqual([row["id"] for row in rows], ["v-b"])


class AggregatedTrafficSourcesScopeTest(VideoScopeTestCase):
    def test_omitted_scope_covers_every_video(self) -> None:
        rows = database.get_aggregated_traffic_sources(start_date=START_DATE, end_date=END_DATE)
        self.assertEqual(sum(row["views"] for row in rows), 1300)

    def test_populated_scope_limits_aggregation(self) -> None:
        rows = database.get_aggregated_traffic_sources(start_date=START_DATE, end_date=END_DATE, video_ids=["v-a", "v-b"])
        self.assertEqual(sum(row["views"] for row in rows), 1000)

    def test_empty_scope_returns_empty_list(self) -> None:
        self.assertEqual(database.get_aggregated_traffic_sources(start_date=START_DATE, end_date=END_DATE, video_ids=[]), [])

    def test_scope_composes_with_filters(self) -> None:
        rows = database.get_aggregated_traffic_sources(
            start_date=START_DATE, end_date=END_DATE, content_type="video", privacy_status="public",
            title="Alpha", video_ids=["v-a", "v-b"],
        )
        self.assertEqual(sum(row["views"] for row in rows), 600)

    def test_source_types_are_preserved_under_scope(self) -> None:
        rows = database.get_aggregated_traffic_sources(start_date=START_DATE, end_date=END_DATE, video_ids=["v-a"])
        self.assertEqual({row["traffic_source_type"] for row in rows}, {"SEARCH", "SUGGESTED"})


class TopVideosByTrafficSourceScopeTest(VideoScopeTestCase):
    def test_omitted_scope_covers_every_video(self) -> None:
        grouped = database.get_top_videos_by_traffic_source(start_date=START_DATE, end_date=END_DATE)
        # The helper's own default limit is 3, so v-d (lowest views) is truncated here.
        self.assertEqual([row["id"] for row in grouped["SEARCH"]], ["v-a", "v-b", "v-c"])

    def test_populated_scope_limits_every_source_bucket(self) -> None:
        grouped = database.get_top_videos_by_traffic_source(start_date=START_DATE, end_date=END_DATE, video_ids=["v-b", "v-c"])
        for source_type in ("SEARCH", "SUGGESTED"):
            self.assertEqual([row["id"] for row in grouped[source_type]], ["v-b", "v-c"])

    def test_empty_scope_returns_empty_dict(self) -> None:
        self.assertEqual(database.get_top_videos_by_traffic_source(start_date=START_DATE, end_date=END_DATE, video_ids=[]), {})

    def test_limit_applies_per_source_within_scope(self) -> None:
        grouped = database.get_top_videos_by_traffic_source(start_date=START_DATE, end_date=END_DATE, limit=1, video_ids=["v-a", "v-b"])
        self.assertEqual(set(grouped), {"SEARCH", "SUGGESTED"})
        for bucket in grouped.values():
            self.assertEqual([row["id"] for row in bucket], ["v-a"])

    def test_scope_composes_with_filters(self) -> None:
        grouped = database.get_top_videos_by_traffic_source(
            start_date=START_DATE, end_date=END_DATE, content_type="video", privacy_status="private",
            title="Episode", video_ids=["v-a", "v-b"],
        )
        self.assertEqual([row["id"] for row in grouped["SEARCH"]], ["v-b"])


class PlaylistRouteScopeTest(VideoScopeTestCase):
    def test_aggregated_analytics_matches_scoped_helper(self) -> None:
        body = self._get("/analytics/playlists/p-full", **DATE_RANGE)
        self.assertEqual(body["items"], database.get_aggregated_analytics(start_date=START_DATE, end_date=END_DATE, video_ids=["v-a", "v-b"]))

    def test_duplicate_membership_does_not_inflate_totals(self) -> None:
        """v-a appears twice in p-full; its 300 views must be counted once."""
        body = self._get("/analytics/playlists/p-full", **DATE_RANGE)
        self.assertEqual(sum(row["views"] for row in body["items"]), 500)

    def test_top_videos_matches_scoped_helper(self) -> None:
        body = self._get("/analytics/playlists/p-full/top", **DATE_RANGE)
        expected = database.get_top_videos_by_views(start_date=START_DATE, end_date=END_DATE, video_ids=["v-a", "v-b"])
        self.assertEqual(body["items"], expected)
        self.assertEqual([row["id"] for row in body["items"]], ["v-a", "v-b"])

    def test_top_videos_honours_sort_by(self) -> None:
        body = self._get("/analytics/playlists/p-full/top", **DATE_RANGE, sort_by="watch_time")
        self.assertEqual([row["id"] for row in body["items"]], ["v-b", "v-a"])

    def test_traffic_sources_matches_scoped_helper(self) -> None:
        body = self._get("/analytics/playlists/p-full/traffic-sources", **DATE_RANGE)
        expected = database.get_aggregated_traffic_sources(start_date=START_DATE, end_date=END_DATE, video_ids=["v-a", "v-b"])
        self.assertEqual(body["items"], expected)
        self.assertEqual(sum(row["views"] for row in body["items"]), 1000)

    def test_traffic_source_top_videos_matches_scoped_helper(self) -> None:
        body = self._get("/analytics/playlists/p-full/traffic-sources/top", **DATE_RANGE)
        expected = database.get_top_videos_by_traffic_source(start_date=START_DATE, end_date=END_DATE, limit=10, video_ids=["v-a", "v-b"])
        self.assertEqual(body["items"], expected)
        self.assertEqual([row["id"] for row in body["items"]["SEARCH"]], ["v-a", "v-b"])

    def test_playlist_results_exclude_non_member_videos(self) -> None:
        body = self._get("/analytics/playlists/p-full/top", **DATE_RANGE)
        self.assertNotIn("v-c", {row["id"] for row in body["items"]})


class FilteredPlaylistParityTest(VideoScopeTestCase):
    """Playlist routes must agree with the shared helpers when scope and every other filter apply together.

    The filters below (video + public + "Episode") match exactly two videos channel-wide, v-a and v-d,
    of which only v-a is a member of p-full. Any route that dropped the scope, or bound the scope IDs
    to the wrong filter, would surface v-d here.
    """

    CONTENT_TYPE = "video"
    PRIVACY_STATUS = "public"
    TITLE = "Episode"
    FILTERS = {"content_type": CONTENT_TYPE, "privacy_status": PRIVACY_STATUS, "title": TITLE}
    MEMBERS = ["v-a", "v-b"]

    def test_aggregated_analytics_matches_scoped_helper_under_all_filters(self) -> None:
        body = self._get("/analytics/playlists/p-full", **DATE_RANGE, **self.FILTERS)
        expected = database.get_aggregated_analytics(
            start_date=START_DATE, end_date=END_DATE, content_type=self.CONTENT_TYPE,
            privacy_status=self.PRIVACY_STATUS, title=self.TITLE, video_ids=self.MEMBERS,
        )
        self.assertEqual(body["items"], expected)
        self.assertEqual(sum(row["views"] for row in body["items"]), 300)

    def test_aggregated_analytics_diverges_from_channel_under_all_filters(self) -> None:
        playlist = self._get("/analytics/playlists/p-full", **DATE_RANGE, **self.FILTERS)
        channel = self._get("/analytics/videos", **DATE_RANGE, **self.FILTERS)
        self.assertEqual(sum(row["views"] for row in channel["items"]), 350)
        self.assertNotEqual(playlist["items"], channel["items"])

    def test_top_videos_matches_scoped_helper_under_all_filters(self) -> None:
        body = self._get("/analytics/playlists/p-full/top", **DATE_RANGE, **self.FILTERS)
        expected = database.get_top_videos_by_views(
            start_date=START_DATE, end_date=END_DATE, content_type=self.CONTENT_TYPE,
            privacy_status=self.PRIVACY_STATUS, title=self.TITLE, video_ids=self.MEMBERS,
        )
        self.assertEqual(body["items"], expected)
        self.assertEqual([row["id"] for row in body["items"]], ["v-a"])

    def test_top_videos_excludes_nonmember_the_channel_route_returns(self) -> None:
        playlist = self._get("/analytics/playlists/p-full/top", **DATE_RANGE, **self.FILTERS)
        channel = self._get("/analytics/videos/top", **DATE_RANGE, **self.FILTERS)
        self.assertEqual([row["id"] for row in channel["items"]], ["v-a", "v-d"])
        self.assertNotIn("v-d", {row["id"] for row in playlist["items"]})

    def test_traffic_sources_matches_scoped_helper_under_all_filters(self) -> None:
        body = self._get("/analytics/playlists/p-full/traffic-sources", **DATE_RANGE, **self.FILTERS)
        expected = database.get_aggregated_traffic_sources(
            start_date=START_DATE, end_date=END_DATE, content_type=self.CONTENT_TYPE,
            privacy_status=self.PRIVACY_STATUS, title=self.TITLE, video_ids=self.MEMBERS,
        )
        self.assertEqual(body["items"], expected)
        self.assertEqual(sum(row["views"] for row in body["items"]), 600)

    def test_traffic_sources_diverges_from_channel_under_all_filters(self) -> None:
        channel = self._get("/analytics/traffic-sources", **DATE_RANGE, **self.FILTERS)
        self.assertEqual(sum(row["views"] for row in channel["items"]), 700)

    def test_traffic_source_top_videos_matches_scoped_helper_under_all_filters(self) -> None:
        body = self._get("/analytics/playlists/p-full/traffic-sources/top", **DATE_RANGE, **self.FILTERS)
        expected = database.get_top_videos_by_traffic_source(
            start_date=START_DATE, end_date=END_DATE, content_type=self.CONTENT_TYPE,
            privacy_status=self.PRIVACY_STATUS, limit=10, title=self.TITLE, video_ids=self.MEMBERS,
        )
        self.assertEqual(body["items"], expected)
        for bucket in body["items"].values():
            self.assertEqual([row["id"] for row in bucket], ["v-a"])

    def test_traffic_source_top_videos_excludes_nonmember_the_channel_route_returns(self) -> None:
        playlist = self._get("/analytics/playlists/p-full/traffic-sources/top", **DATE_RANGE, **self.FILTERS)
        channel = self._get("/analytics/traffic-sources/top", **DATE_RANGE, **self.FILTERS)
        self.assertEqual([row["id"] for row in channel["items"]["SEARCH"]], ["v-a", "v-d"])
        self.assertNotIn("v-d", {row["id"] for row in playlist["items"]["SEARCH"]})

    def test_filters_that_match_only_a_nonmember_return_empty(self) -> None:
        """v-c matches these filters channel-wide but is not in p-full, so the playlist result is empty
        while the channel result is not — the scope, not the filters, is what removes it."""
        filters = {"content_type": "short", "privacy_status": "public", "title": "Vlog"}
        playlist = self._get("/analytics/playlists/p-full/top", **DATE_RANGE, **filters)
        channel = self._get("/analytics/videos/top", **DATE_RANGE, **filters)
        self.assertEqual([row["id"] for row in channel["items"]], ["v-c"])
        self.assertEqual(playlist["items"], [])


class EmptyPlaylistRouteTest(VideoScopeTestCase):
    def test_aggregated_analytics_returns_empty_items(self) -> None:
        self.assertEqual(self._get("/analytics/playlists/p-empty", **DATE_RANGE)["items"], [])

    def test_top_videos_returns_empty_items(self) -> None:
        self.assertEqual(self._get("/analytics/playlists/p-empty/top", **DATE_RANGE)["items"], [])

    def test_traffic_sources_returns_empty_items(self) -> None:
        self.assertEqual(self._get("/analytics/playlists/p-empty/traffic-sources", **DATE_RANGE)["items"], [])

    def test_traffic_source_top_videos_returns_empty_mapping(self) -> None:
        body = self._get("/analytics/playlists/p-empty/traffic-sources/top", **DATE_RANGE)
        self.assertEqual(body["items"], {})


class UnknownPlaylistRouteTest(VideoScopeTestCase):
    def test_every_playlist_route_returns_the_same_404(self) -> None:
        paths = (
            "/analytics/playlists/nope",
            "/analytics/playlists/nope/top",
            "/analytics/playlists/nope/traffic-sources",
            "/analytics/playlists/nope/traffic-sources/top",
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path, params=DATE_RANGE)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["detail"], "Playlist not found")


class ChannelRouteRegressionTest(VideoScopeTestCase):
    def test_channel_routes_stay_channel_wide(self) -> None:
        body = self._get("/analytics/videos", **DATE_RANGE)
        self.assertEqual(sum(row["views"] for row in body["items"]), 650)

    def test_channel_top_videos_stay_channel_wide(self) -> None:
        body = self._get("/analytics/videos/top", **DATE_RANGE)
        self.assertEqual([row["id"] for row in body["items"]], ["v-a", "v-b", "v-c", "v-d"])

    def test_channel_traffic_sources_stay_channel_wide(self) -> None:
        body = self._get("/analytics/traffic-sources", **DATE_RANGE)
        self.assertEqual(sum(row["views"] for row in body["items"]), 1300)

    def test_channel_traffic_source_top_videos_stay_channel_wide(self) -> None:
        body = self._get("/analytics/traffic-sources/top", **DATE_RANGE)
        self.assertEqual([row["id"] for row in body["items"]["SEARCH"]], ["v-a", "v-b", "v-c", "v-d"])


if __name__ == "__main__":
    unittest.main()
