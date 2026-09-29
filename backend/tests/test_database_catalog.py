from __future__ import annotations

import sqlite3
import unittest
from typing import Any
from unittest import mock

from database import FxRate, Video, VideoAnalytics, connection, writer
from database.reports import catalog
from database.tables import field_names
from routes.playlists import router as playlists_router
from routes.videos import router as videos_router
from tests.support import (
    FIXED_NOW,
    IsolatedDatabaseTestCase,
    create_test_client,
    make_fx_rate,
    make_playlist,
    make_playlist_item,
    make_video,
    make_video_analytics,
)

_client = create_test_client(videos_router, playlists_router)


def _page(path: str, **params: str | int) -> tuple[list[dict], int]:
    """Return a paged endpoint's items and total."""
    body = _client.get(path, params=params).json()
    return body["items"], body["total"]


def _item(path: str) -> dict | None:
    """Return a detail endpoint's item, or None on 404."""
    response = _client.get(path)
    return None if response.status_code == 404 else response.json()["item"]


class VideoCatalogTestCase(IsolatedDatabaseTestCase):
    def _seed_sortable_videos(self) -> None:
        """Four videos with distinct, non-tied values on every sortable column."""
        writer.write(make_video(
            "v-1", "Alpha", published_at="2024-01-01T00:00:00Z",
            content_type="video", privacy_status="public", view_count=10, comment_count=1,
        ))
        writer.write(make_video(
            "v-2", "Beta", published_at="2024-01-02T00:00:00Z",
            content_type="video", privacy_status="private", view_count=40, comment_count=4,
        ))
        writer.write(make_video(
            "v-3", "Gamma", published_at="2024-01-03T00:00:00Z",
            content_type="short", privacy_status="public", view_count=20, comment_count=2,
        ))
        writer.write(make_video(
            "v-4", "Delta", published_at="2024-01-04T00:00:00Z",
            content_type="short", privacy_status="unlisted", view_count=30, comment_count=3,
        ))


class GetAllVideosPaginationTest(VideoCatalogTestCase):
    def test_empty_catalog_returns_empty_page_and_zero_total(self) -> None:
        items, total = _page("/videos")
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_first_page_returns_page_size_items(self) -> None:
        self._seed_sortable_videos()
        items, total = _page("/videos", page=1, page_size=2)
        self.assertEqual(len(items), 2)
        self.assertEqual(total, 4)

    def test_second_page_continues_without_overlap(self) -> None:
        self._seed_sortable_videos()
        first, _ = _page("/videos", page=1, page_size=2)
        second, _ = _page("/videos", page=2, page_size=2)
        self.assertFalse({i["id"] for i in first} & {i["id"] for i in second})

    def test_page_past_the_end_is_empty_but_total_is_stable(self) -> None:
        self._seed_sortable_videos()
        items, total = _page("/videos", page=5, page_size=2)
        self.assertEqual(items, [])
        self.assertEqual(total, 4)

    def test_total_is_independent_of_page_size(self) -> None:
        self._seed_sortable_videos()
        _, total_small = _page("/videos", page=1, page_size=1)
        _, total_large = _page("/videos", page=1, page_size=100)
        self.assertEqual(total_small, total_large)


class GetAllVideosSortTest(VideoCatalogTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed_sortable_videos()

    def test_every_allowed_sort_column_orders_ascending_and_descending(self) -> None:
        expectations = {
            "published_at": (["v-1", "v-2", "v-3", "v-4"], ["v-4", "v-3", "v-2", "v-1"]),
            "view_count": (["v-1", "v-3", "v-4", "v-2"], ["v-2", "v-4", "v-3", "v-1"]),
            "comment_count": (["v-1", "v-3", "v-4", "v-2"], ["v-2", "v-4", "v-3", "v-1"]),
        }
        for sort_by, (asc_order, desc_order) in expectations.items():
            with self.subTest(sort_by=sort_by):
                asc_items, _ = _page("/videos", page_size=10, sort_by=sort_by, sort_dir="asc")
                desc_items, _ = _page("/videos", page_size=10, sort_by=sort_by, sort_dir="desc")
                self.assertEqual([i["id"] for i in asc_items], asc_order)
                self.assertEqual([i["id"] for i in desc_items], desc_order)

    def test_total_revenue_sgd_sorts_both_directions(self) -> None:
        # Distinct, non-tied revenue on three of the four seeded videos; v-4 stays at
        # zero (no analytics row) so the sort must also place an unearning video correctly.
        writer.write(FxRate.from_dict({**{"date": "2024-02-01", "usd_to_sgd": 1.0}, "updated_at": FIXED_NOW}))
        for video_id, revenue in (("v-1", 5.0), ("v-2", 15.0), ("v-3", 10.0)):
            writer.write(VideoAnalytics.from_dict({**{
                "video_id": video_id, "date": "2024-02-01", "views": 1, "watch_time_minutes": 1,
                "estimated_revenue": revenue, "average_view_duration_seconds": 1, "average_view_percentage": 1.0,
                "likes": 0, "subscribers_gained": 0, "subscribers_lost": 0,
            }, "updated_at": FIXED_NOW}))
        asc_items, _ = _page("/videos", page_size=10, sort_by="total_revenue_sgd", sort_dir="asc")
        desc_items, _ = _page("/videos", page_size=10, sort_by="total_revenue_sgd", sort_dir="desc")
        self.assertEqual([i["id"] for i in asc_items], ["v-4", "v-1", "v-3", "v-2"])
        self.assertEqual([i["id"] for i in desc_items], ["v-2", "v-3", "v-1", "v-4"])

    def test_invalid_sort_falls_back_to_published_at(self) -> None:
        items, _ = _page("/videos", page_size=10, sort_by="not_a_column", sort_dir="asc")
        self.assertEqual([i["id"] for i in items], ["v-1", "v-2", "v-3", "v-4"])


class GetAllVideosFilterTest(VideoCatalogTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed_sortable_videos()

    def test_title_filter_is_case_insensitive_substring(self) -> None:
        items, total = _page("/videos", title="amm")
        self.assertEqual({i["id"] for i in items}, {"v-3"})
        self.assertEqual(total, 1)

    def test_publication_date_bounds_are_inclusive(self) -> None:
        items, _ = _page("/videos", start_date="2024-01-02", end_date="2024-01-03")
        self.assertEqual({i["id"] for i in items}, {"v-2", "v-3"})

    def test_content_type_filter(self) -> None:
        items, _ = _page("/videos", content_type="short")
        self.assertEqual({i["id"] for i in items}, {"v-3", "v-4"})

    def test_privacy_status_filter(self) -> None:
        items, _ = _page("/videos", privacy_status="public")
        self.assertEqual({i["id"] for i in items}, {"v-1", "v-3"})

    def test_combined_filters_and_pagination(self) -> None:
        items, total = _page(
            "/videos",
            content_type="short", privacy_status="unlisted", start_date="2024-01-01", end_date="2024-01-31",
            page=1, page_size=10,
        )
        self.assertEqual([i["id"] for i in items], ["v-4"])
        self.assertEqual(total, 1)

    def test_no_matches_returns_empty_page_with_zero_total(self) -> None:
        items, total = _page("/videos", title="does-not-exist")
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_title_filter_matches_video_id(self) -> None:
        items, total = _page("/videos", title="v-3")
        self.assertEqual({i["id"] for i in items}, {"v-3"})
        self.assertEqual(total, 1)

    def test_id_match_combines_with_other_filters_and_pagination(self) -> None:
        items, total = _page("/videos", title="v-3", content_type="short", page=1, page_size=10)
        self.assertEqual([i["id"] for i in items], ["v-3"])
        self.assertEqual(total, 1)
        items, total = _page("/videos", title="v-3", content_type="video", page=1, page_size=10)
        self.assertEqual(items, [])
        self.assertEqual(total, 0)


class GetVideoTest(VideoCatalogTestCase):
    def test_unknown_video_returns_none(self) -> None:
        self.assertIsNone(_item("/videos/nope"))

    def test_known_video_returns_a_dict(self) -> None:
        self._seed_sortable_videos()
        video = _item("/videos/v-1")
        assert video is not None
        self.assertEqual(video["id"], "v-1")


def _traced_listing(**kwargs: Any) -> tuple[dict, list[str]]:
    """Run video_listing and return its result with the SELECT statements it executed."""
    statements: list[str] = []
    open_connection = connection.get_connection

    def traced() -> sqlite3.Connection:
        conn = open_connection()
        conn.set_trace_callback(statements.append)
        return conn

    with mock.patch("database.reader.get_connection", traced):
        result = catalog.video_listing(**kwargs)
    return result, [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]


class VideoListingFieldsTest(VideoCatalogTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed_sortable_videos()
        # v-1: two analytics days, one without an FX rate; v-2: one day; v-3/v-4: no analytics.
        writer.write(make_fx_rate("2024-02-01", 2.0))
        writer.write(make_video_analytics("v-1", "2024-02-01", watch_time_minutes=60, estimated_revenue=5.0))
        writer.write(make_video_analytics("v-1", "2024-02-02", watch_time_minutes=30, estimated_revenue=7.0))
        writer.write(make_video_analytics("v-2", "2024-02-01", watch_time_minutes=120, estimated_revenue=1.0))

    def test_default_fields_are_every_column_plus_lifetime_totals(self) -> None:
        body = catalog.video_listing()
        expected = [*field_names(Video), "total_revenue_sgd", "total_watch_time_hours"]
        self.assertEqual(set(body), {"items", "total", "page", "page_size"})
        self.assertEqual([list(item) for item in body["items"]], [expected] * 4)

    def test_lifetime_totals_sum_every_day_and_skip_missing_fx(self) -> None:
        items = {i["id"]: i for i in catalog.video_listing()["items"]}
        self.assertEqual(items["v-1"]["total_revenue_sgd"], 10.0)
        self.assertEqual(items["v-1"]["total_watch_time_hours"], 1.5)
        self.assertEqual(items["v-2"]["total_revenue_sgd"], 2.0)
        self.assertEqual((items["v-3"]["total_revenue_sgd"], items["v-3"]["total_watch_time_hours"]), (0, 0))

    def test_base_fields_skip_analytics_joins(self) -> None:
        body, statements = _traced_listing(fields=("id", "own", "published_at"), sort_dir="asc")
        self.assertEqual(body["items"][0], {"id": "v-1", "own": True, "published_at": "2024-01-01T00:00:00Z"})
        self.assertEqual(len(statements), 2)
        self.assertFalse(any("video_analytics" in sql or "fx_rates" in sql for sql in statements))

    def test_watch_time_alone_joins_analytics_without_fx(self) -> None:
        body, statements = _traced_listing(fields=("total_watch_time_hours",), sort_dir="asc")
        self.assertEqual(body["items"][0], {"total_watch_time_hours": 1.5})
        self.assertIn("video_analytics", statements[-1])
        self.assertNotIn("fx_rates", statements[-1])

    def test_mixed_fields_keep_requested_order(self) -> None:
        items = catalog.video_listing(fields=("total_revenue_sgd", "id"), sort_dir="asc")["items"]
        self.assertEqual(items[0], {"total_revenue_sgd": 10.0, "id": "v-1"})

    def test_selected_null_stays_null(self) -> None:
        writer.write(make_video("v-5", "Epsilon", published_at=None))
        items = catalog.video_listing(fields=("id", "published_at"), video_ids=["v-5"])["items"]
        self.assertEqual(items, [{"id": "v-5", "published_at": None}])

    def test_sorting_by_an_unselected_total_computes_it_without_returning_it(self) -> None:
        body, statements = _traced_listing(
            fields=("id",), sort_by="total_revenue_sgd", sort_dir="desc", video_ids=["v-3", "v-2", "v-1"],
        )
        self.assertEqual([i["id"] for i in body["items"]], ["v-1", "v-2", "v-3"])
        self.assertEqual(set(body["items"][0]), {"id"})
        self.assertIn("fx_rates", statements[-1])

    def test_duplicate_fields_yield_one_key(self) -> None:
        items = catalog.video_listing(fields=("id", "id"), video_ids=["v-1"])["items"]
        self.assertEqual(items, [{"id": "v-1"}])

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            catalog.video_listing(fields=("titel",))

    def test_unpaginated_listing_returns_every_match_without_a_count(self) -> None:
        for index in range(60):
            writer.write(make_video(f"v-extra-{index:02d}", published_at="2025-01-01T00:00:00Z"))
        body, statements = _traced_listing(fields=("id",), page_size=None)
        self.assertEqual(set(body), {"items"})
        self.assertEqual(len(body["items"]), 64)
        self.assertEqual(len(statements), 1)
        self.assertNotIn("COUNT", statements[0].upper())

    def test_unpaginated_empty_listing_returns_empty_items(self) -> None:
        self.assertEqual(catalog.video_listing(fields=("id",), page_size=None, video_ids=[]), {"items": []})


class PublishedVideosRouteTest(VideoCatalogTestCase):
    def test_returns_every_match_as_five_fields_oldest_first(self) -> None:
        for index in range(60):
            writer.write(make_video(f"v-extra-{index:02d}", published_at=f"2025-01-01T00:{index:02d}:00Z"))
        writer.write(make_video("v-external", published_at="2025-06-01T00:00:00Z", own=False))
        body = _client.get("/videos/published").json()
        self.assertEqual(set(body), {"items"})
        self.assertEqual(len(body["items"]), 60)
        self.assertEqual(set(body["items"][0]), {"id", "title", "published_at", "thumbnail_url", "content_type"})
        published = [i["published_at"] for i in body["items"]]
        self.assertEqual(published, sorted(published))

    def test_publication_date_bounds_are_inclusive(self) -> None:
        self._seed_sortable_videos()
        body = _client.get("/videos/published", params={"start_date": "2024-01-02", "end_date": "2024-01-03"}).json()
        self.assertEqual([i["id"] for i in body["items"]], ["v-2", "v-3"])


class PlaylistCatalogTestCase(IsolatedDatabaseTestCase):
    def _seed_sortable_playlists(self) -> None:
        writer.write(make_playlist("p-1", "Alpha Playlist", published_at="2024-01-01T00:00:00Z", item_count=1))
        writer.write(make_playlist("p-2", "Beta Playlist", published_at="2024-01-02T00:00:00Z", item_count=3))
        writer.write(make_playlist("p-3", "Gamma Playlist", published_at="2024-01-03T00:00:00Z", item_count=2))


class GetAllPlaylistsTest(PlaylistCatalogTestCase):
    def test_empty_catalog_returns_empty_page_and_zero_total(self) -> None:
        items, total = _page("/playlists")
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_pagination_boundaries(self) -> None:
        self._seed_sortable_playlists()
        first, total = _page("/playlists", page=1, page_size=2, sort_by="published_at", sort_dir="asc")
        second, _ = _page("/playlists", page=2, page_size=2, sort_by="published_at", sort_dir="asc")
        self.assertEqual(total, 3)
        self.assertEqual([p["id"] for p in first], ["p-1", "p-2"])
        self.assertEqual([p["id"] for p in second], ["p-3"])

    def test_item_count_sort_both_directions(self) -> None:
        self._seed_sortable_playlists()
        asc, _ = _page("/playlists", sort_by="item_count", sort_dir="asc")
        desc, _ = _page("/playlists", sort_by="item_count", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-1", "p-3", "p-2"])
        self.assertEqual([p["id"] for p in desc], ["p-2", "p-3", "p-1"])

    def test_title_filter(self) -> None:
        self._seed_sortable_playlists()
        items, _ = _page("/playlists", title="beta")
        self.assertEqual({p["id"] for p in items}, {"p-2"})

    def test_title_filter_matches_playlist_id_when_title_does_not_contain_term(self) -> None:
        self._seed_sortable_playlists()
        items, total = _page("/playlists", title="p-2")
        self.assertEqual({p["id"] for p in items}, {"p-2"})
        self.assertEqual(total, 1)

    def test_publication_date_bounds_are_inclusive(self) -> None:
        self._seed_sortable_playlists()
        items, _ = _page("/playlists", start_date="2024-01-02", end_date="2024-01-02")
        self.assertEqual({p["id"] for p in items}, {"p-2"})


class PlaylistAggregateSortTest(IsolatedDatabaseTestCase):
    """Each playlist has exactly one member video, with the three aggregated sort
    columns deliberately given a different relative order so a test asserting one
    column can't pass by accident on a column that happens to be correlated with it."""

    def setUp(self) -> None:
        super().setUp()
        writer.write(make_playlist("p-1", "First"))
        writer.write(make_playlist("p-2", "Second"))
        writer.write(make_playlist("p-3", "Third"))

        writer.write(make_video("v-1", "Video One", published_at="2024-01-01T00:00:00Z", view_count=30))
        writer.write(make_video("v-2", "Video Two", published_at="2024-03-01T00:00:00Z", view_count=10))
        writer.write(make_video("v-3", "Video Three", published_at="2024-02-01T00:00:00Z", view_count=20))
        writer.write(make_playlist_item("pi-1", "p-1", "v-1", 0))
        writer.write(make_playlist_item("pi-2", "p-2", "v-2", 0))
        writer.write(make_playlist_item("pi-3", "p-3", "v-3", 0))

        writer.write(FxRate.from_dict({**{"date": "2024-06-01", "usd_to_sgd": 1.0}, "updated_at": FIXED_NOW}))
        for video_id, revenue in (("v-1", 5.0), ("v-2", 15.0), ("v-3", 10.0)):
            writer.write(VideoAnalytics.from_dict({**{
                "video_id": video_id, "date": "2024-06-01", "views": 1, "watch_time_minutes": 1,
                "estimated_revenue": revenue, "average_view_duration_seconds": 1, "average_view_percentage": 1.0,
                "likes": 0, "subscribers_gained": 0, "subscribers_lost": 0,
            }, "updated_at": FIXED_NOW}))

    def test_last_item_added_sorts_both_directions(self) -> None:
        asc, _ = _page("/playlists", sort_by="last_item_added", sort_dir="asc")
        desc, _ = _page("/playlists", sort_by="last_item_added", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-1", "p-3", "p-2"])
        self.assertEqual([p["id"] for p in desc], ["p-2", "p-3", "p-1"])

    def test_total_views_sorts_both_directions(self) -> None:
        asc, _ = _page("/playlists", sort_by="total_views", sort_dir="asc")
        desc, _ = _page("/playlists", sort_by="total_views", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-2", "p-3", "p-1"])
        self.assertEqual([p["id"] for p in desc], ["p-1", "p-3", "p-2"])

    def test_total_earnings_sgd_sorts_both_directions(self) -> None:
        asc, _ = _page("/playlists", sort_by="total_earnings_sgd", sort_dir="asc")
        desc, _ = _page("/playlists", sort_by="total_earnings_sgd", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-1", "p-3", "p-2"])
        self.assertEqual([p["id"] for p in desc], ["p-2", "p-3", "p-1"])


class GetPlaylistTest(PlaylistCatalogTestCase):
    def test_unknown_playlist_returns_none(self) -> None:
        self.assertIsNone(_item("/playlists/nope"))

    def test_known_playlist_returns_a_dict(self) -> None:
        self._seed_sortable_playlists()
        playlist = _item("/playlists/p-1")
        assert playlist is not None
        self.assertEqual(playlist["id"], "p-1")


class GetPlaylistVideosTest(PlaylistCatalogTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write(make_playlist("p-1", "Playlist", item_count=2))
        writer.write(make_video("v-1", "Alpha", published_at="2024-01-01T00:00:00Z", view_count=10))
        writer.write(make_video("v-2", "Beta", published_at="2024-01-02T00:00:00Z", view_count=20))
        writer.write(make_video("v-3", "Gamma", published_at="2024-01-03T00:00:00Z", view_count=30))
        writer.write(make_playlist_item("pi-1", "p-1", "v-1", 0))
        writer.write(make_playlist_item("pi-2", "p-1", "v-2", 1))

    def test_scoped_to_playlist_membership(self) -> None:
        items, total = _page("/playlists/p-1/videos")
        self.assertEqual({i["id"] for i in items}, {"v-1", "v-2"})
        self.assertEqual(total, 2)

    def test_empty_playlist_returns_empty_page(self) -> None:
        writer.write(make_playlist("p-empty", "Empty", item_count=0))
        items, total = _page("/playlists/p-empty/videos")
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_view_count_sort_within_playlist(self) -> None:
        items, _ = _page("/playlists/p-1/videos", sort_by="view_count", sort_dir="desc")
        self.assertEqual([i["id"] for i in items], ["v-2", "v-1"])

    def test_combined_filters_scoped_to_playlist(self) -> None:
        items, _ = _page("/playlists/p-1/videos", title="alpha")
        self.assertEqual([i["id"] for i in items], ["v-1"])

    def test_duplicate_membership_counts_once_and_does_not_inflate_totals(self) -> None:
        writer.write(make_playlist_item("pi-dup", "p-1", "v-1", 2))
        writer.write(make_fx_rate("2024-01-05", 1.5))
        writer.write(make_video_analytics("v-1", "2024-01-05", watch_time_minutes=60, estimated_revenue=2.0))
        items, total = _page("/playlists/p-1/videos")
        self.assertEqual(total, 2)
        self.assertEqual(sorted(i["id"] for i in items), ["v-1", "v-2"])
        playlist_v1 = next(i for i in items if i["id"] == "v-1")
        channel_v1 = _item("/videos/v-1")
        assert channel_v1 is not None
        self.assertEqual(playlist_v1["total_revenue_sgd"], 3.0)
        self.assertEqual(playlist_v1["total_watch_time_hours"], 1.0)
        self.assertEqual(playlist_v1, channel_v1)

    def test_unknown_playlist_is_404(self) -> None:
        self.assertEqual(_client.get("/playlists/nope/videos").status_code, 404)

    def test_published_videos_scope_to_the_playlist_and_404_when_it_is_missing(self) -> None:
        body = _client.get("/videos/published", params={"playlist_id": "p-1"}).json()
        self.assertEqual([v["id"] for v in body["items"]], ["v-1", "v-2"])
        self.assertEqual(_client.get("/videos/published", params={"playlist_id": "nope"}).status_code, 404)

    def test_title_filter_matches_video_id_scoped_to_playlist(self) -> None:
        items, total = _page("/playlists/p-1/videos", title="v-1")
        self.assertEqual([i["id"] for i in items], ["v-1"])
        self.assertEqual(total, 1)
        items, total = _page("/playlists/p-1/videos", title="v-3")
        self.assertEqual(items, [])
        self.assertEqual(total, 0)


if __name__ == "__main__":
    unittest.main()
