from __future__ import annotations

import unittest

import database
from tests.support import IsolatedDatabaseTestCase, make_playlist, make_playlist_item, make_video


class VideoCatalogTestCase(IsolatedDatabaseTestCase):
    def _seed_sortable_videos(self) -> None:
        """Four videos with distinct, non-tied values on every sortable column."""
        database.upsert_video(make_video(
            "v-1", "Alpha", published_at="2024-01-01T00:00:00Z",
            content_type="video", privacy_status="public", view_count=10, comment_count=1,
        ))
        database.upsert_video(make_video(
            "v-2", "Beta", published_at="2024-01-02T00:00:00Z",
            content_type="video", privacy_status="private", view_count=40, comment_count=4,
        ))
        database.upsert_video(make_video(
            "v-3", "Gamma", published_at="2024-01-03T00:00:00Z",
            content_type="short", privacy_status="public", view_count=20, comment_count=2,
        ))
        database.upsert_video(make_video(
            "v-4", "Delta", published_at="2024-01-04T00:00:00Z",
            content_type="short", privacy_status="unlisted", view_count=30, comment_count=3,
        ))


class GetAllVideosPaginationTest(VideoCatalogTestCase):
    def test_empty_catalog_returns_empty_page_and_zero_total(self) -> None:
        items, total = database.get_all_videos()
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_first_page_returns_page_size_items(self) -> None:
        self._seed_sortable_videos()
        items, total = database.get_all_videos(page=1, page_size=2)
        self.assertEqual(len(items), 2)
        self.assertEqual(total, 4)

    def test_second_page_continues_without_overlap(self) -> None:
        self._seed_sortable_videos()
        first, _ = database.get_all_videos(page=1, page_size=2)
        second, _ = database.get_all_videos(page=2, page_size=2)
        self.assertFalse({i["id"] for i in first} & {i["id"] for i in second})

    def test_page_past_the_end_is_empty_but_total_is_stable(self) -> None:
        self._seed_sortable_videos()
        items, total = database.get_all_videos(page=5, page_size=2)
        self.assertEqual(items, [])
        self.assertEqual(total, 4)

    def test_total_is_independent_of_page_size(self) -> None:
        self._seed_sortable_videos()
        _, total_small = database.get_all_videos(page=1, page_size=1)
        _, total_large = database.get_all_videos(page=1, page_size=100)
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
                asc_items, _ = database.get_all_videos(page_size=10, sort_by=sort_by, sort_dir="asc")
                desc_items, _ = database.get_all_videos(page_size=10, sort_by=sort_by, sort_dir="desc")
                self.assertEqual([i["id"] for i in asc_items], asc_order)
                self.assertEqual([i["id"] for i in desc_items], desc_order)

    def test_total_revenue_sgd_sorts_both_directions(self) -> None:
        # Distinct, non-tied revenue on three of the four seeded videos; v-4 stays at
        # zero (no analytics row) so the sort must also place an unearning video correctly.
        database.upsert_fx_rate({"date": "2024-02-01", "usd_to_sgd": 1.0})
        for video_id, revenue in (("v-1", 5.0), ("v-2", 15.0), ("v-3", 10.0)):
            database.upsert_video_analytics({
                "video_id": video_id, "date": "2024-02-01", "views": 1, "watch_time_minutes": 1,
                "estimated_revenue": revenue, "average_view_duration_seconds": 1, "average_view_percentage": 1.0,
                "likes": 0, "subscribers_gained": 0, "subscribers_lost": 0,
            })
        asc_items, _ = database.get_all_videos(page_size=10, sort_by="total_revenue_sgd", sort_dir="asc")
        desc_items, _ = database.get_all_videos(page_size=10, sort_by="total_revenue_sgd", sort_dir="desc")
        self.assertEqual([i["id"] for i in asc_items], ["v-4", "v-1", "v-3", "v-2"])
        self.assertEqual([i["id"] for i in desc_items], ["v-2", "v-3", "v-1", "v-4"])

    def test_invalid_sort_falls_back_to_published_at(self) -> None:
        items, _ = database.get_all_videos(page_size=10, sort_by="not_a_column", sort_dir="asc")
        self.assertEqual([i["id"] for i in items], ["v-1", "v-2", "v-3", "v-4"])


class GetAllVideosFilterTest(VideoCatalogTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._seed_sortable_videos()

    def test_title_filter_is_case_insensitive_substring(self) -> None:
        items, total = database.get_all_videos(title="amm")
        self.assertEqual({i["id"] for i in items}, {"v-3"})
        self.assertEqual(total, 1)

    def test_publication_date_bounds_are_inclusive(self) -> None:
        items, _ = database.get_all_videos(start_date="2024-01-02", end_date="2024-01-03")
        self.assertEqual({i["id"] for i in items}, {"v-2", "v-3"})

    def test_content_type_filter(self) -> None:
        items, _ = database.get_all_videos(content_type="short")
        self.assertEqual({i["id"] for i in items}, {"v-3", "v-4"})

    def test_privacy_status_filter(self) -> None:
        items, _ = database.get_all_videos(privacy_status="public")
        self.assertEqual({i["id"] for i in items}, {"v-1", "v-3"})

    def test_combined_filters_and_pagination(self) -> None:
        items, total = database.get_all_videos(
            content_type="short", privacy_status="unlisted", start_date="2024-01-01", end_date="2024-01-31",
            page=1, page_size=10,
        )
        self.assertEqual([i["id"] for i in items], ["v-4"])
        self.assertEqual(total, 1)

    def test_no_matches_returns_empty_page_with_zero_total(self) -> None:
        items, total = database.get_all_videos(title="does-not-exist")
        self.assertEqual(items, [])
        self.assertEqual(total, 0)


class GetVideoTest(VideoCatalogTestCase):
    def test_unknown_video_returns_none(self) -> None:
        self.assertIsNone(database.get_video("nope"))

    def test_known_video_returns_a_dict(self) -> None:
        self._seed_sortable_videos()
        video = database.get_video("v-1")
        assert video is not None
        self.assertEqual(video["id"], "v-1")


class PlaylistCatalogTestCase(IsolatedDatabaseTestCase):
    def _seed_sortable_playlists(self) -> None:
        database.upsert_playlist(make_playlist("p-1", "Alpha Playlist", published_at="2024-01-01T00:00:00Z", item_count=1))
        database.upsert_playlist(make_playlist("p-2", "Beta Playlist", published_at="2024-01-02T00:00:00Z", item_count=3))
        database.upsert_playlist(make_playlist("p-3", "Gamma Playlist", published_at="2024-01-03T00:00:00Z", item_count=2))


class GetAllPlaylistsTest(PlaylistCatalogTestCase):
    def test_empty_catalog_returns_empty_page_and_zero_total(self) -> None:
        items, total = database.get_all_playlists()
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_pagination_boundaries(self) -> None:
        self._seed_sortable_playlists()
        first, total = database.get_all_playlists(page=1, page_size=2, sort_by="published_at", sort_dir="asc")
        second, _ = database.get_all_playlists(page=2, page_size=2, sort_by="published_at", sort_dir="asc")
        self.assertEqual(total, 3)
        self.assertEqual([p["id"] for p in first], ["p-1", "p-2"])
        self.assertEqual([p["id"] for p in second], ["p-3"])

    def test_item_count_sort_both_directions(self) -> None:
        self._seed_sortable_playlists()
        asc, _ = database.get_all_playlists(sort_by="item_count", sort_dir="asc")
        desc, _ = database.get_all_playlists(sort_by="item_count", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-1", "p-3", "p-2"])
        self.assertEqual([p["id"] for p in desc], ["p-2", "p-3", "p-1"])

    def test_title_filter(self) -> None:
        self._seed_sortable_playlists()
        items, _ = database.get_all_playlists(title="beta")
        self.assertEqual({p["id"] for p in items}, {"p-2"})

    def test_publication_date_bounds_are_inclusive(self) -> None:
        self._seed_sortable_playlists()
        items, _ = database.get_all_playlists(start_date="2024-01-02", end_date="2024-01-02")
        self.assertEqual({p["id"] for p in items}, {"p-2"})


class PlaylistAggregateSortTest(IsolatedDatabaseTestCase):
    """Each playlist has exactly one member video, with the three aggregated sort
    columns deliberately given a different relative order so a test asserting one
    column can't pass by accident on a column that happens to be correlated with it."""

    def setUp(self) -> None:
        super().setUp()
        database.upsert_playlist(make_playlist("p-1", "First"))
        database.upsert_playlist(make_playlist("p-2", "Second"))
        database.upsert_playlist(make_playlist("p-3", "Third"))

        database.upsert_video(make_video("v-1", "Video One", published_at="2024-01-01T00:00:00Z", view_count=30))
        database.upsert_video(make_video("v-2", "Video Two", published_at="2024-03-01T00:00:00Z", view_count=10))
        database.upsert_video(make_video("v-3", "Video Three", published_at="2024-02-01T00:00:00Z", view_count=20))
        database.upsert_playlist_item(make_playlist_item("pi-1", "p-1", "v-1", 0))
        database.upsert_playlist_item(make_playlist_item("pi-2", "p-2", "v-2", 0))
        database.upsert_playlist_item(make_playlist_item("pi-3", "p-3", "v-3", 0))

        database.upsert_fx_rate({"date": "2024-06-01", "usd_to_sgd": 1.0})
        for video_id, revenue in (("v-1", 5.0), ("v-2", 15.0), ("v-3", 10.0)):
            database.upsert_video_analytics({
                "video_id": video_id, "date": "2024-06-01", "views": 1, "watch_time_minutes": 1,
                "estimated_revenue": revenue, "average_view_duration_seconds": 1, "average_view_percentage": 1.0,
                "likes": 0, "subscribers_gained": 0, "subscribers_lost": 0,
            })

    def test_last_item_added_sorts_both_directions(self) -> None:
        asc, _ = database.get_all_playlists(sort_by="last_item_added", sort_dir="asc")
        desc, _ = database.get_all_playlists(sort_by="last_item_added", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-1", "p-3", "p-2"])
        self.assertEqual([p["id"] for p in desc], ["p-2", "p-3", "p-1"])

    def test_total_views_sorts_both_directions(self) -> None:
        asc, _ = database.get_all_playlists(sort_by="total_views", sort_dir="asc")
        desc, _ = database.get_all_playlists(sort_by="total_views", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-2", "p-3", "p-1"])
        self.assertEqual([p["id"] for p in desc], ["p-1", "p-3", "p-2"])

    def test_total_earnings_sgd_sorts_both_directions(self) -> None:
        asc, _ = database.get_all_playlists(sort_by="total_earnings_sgd", sort_dir="asc")
        desc, _ = database.get_all_playlists(sort_by="total_earnings_sgd", sort_dir="desc")
        self.assertEqual([p["id"] for p in asc], ["p-1", "p-3", "p-2"])
        self.assertEqual([p["id"] for p in desc], ["p-2", "p-3", "p-1"])


class GetPlaylistTest(PlaylistCatalogTestCase):
    def test_unknown_playlist_returns_none(self) -> None:
        self.assertIsNone(database.get_playlist("nope"))

    def test_known_playlist_returns_a_dict(self) -> None:
        self._seed_sortable_playlists()
        playlist = database.get_playlist("p-1")
        assert playlist is not None
        self.assertEqual(playlist["id"], "p-1")


class GetPlaylistVideosTest(PlaylistCatalogTestCase):
    def setUp(self) -> None:
        super().setUp()
        database.upsert_playlist(make_playlist("p-1", "Playlist", item_count=2))
        database.upsert_video(make_video("v-1", "Alpha", published_at="2024-01-01T00:00:00Z", view_count=10))
        database.upsert_video(make_video("v-2", "Beta", published_at="2024-01-02T00:00:00Z", view_count=20))
        database.upsert_video(make_video("v-3", "Gamma", published_at="2024-01-03T00:00:00Z", view_count=30))
        database.upsert_playlist_item(make_playlist_item("pi-1", "p-1", "v-1", 0))
        database.upsert_playlist_item(make_playlist_item("pi-2", "p-1", "v-2", 1))

    def test_scoped_to_playlist_membership(self) -> None:
        items, total = database.get_playlist_videos("p-1")
        self.assertEqual({i["id"] for i in items}, {"v-1", "v-2"})
        self.assertEqual(total, 2)

    def test_empty_playlist_returns_empty_page(self) -> None:
        database.upsert_playlist(make_playlist("p-empty", "Empty", item_count=0))
        items, total = database.get_playlist_videos("p-empty")
        self.assertEqual(items, [])
        self.assertEqual(total, 0)

    def test_view_count_sort_within_playlist(self) -> None:
        items, _ = database.get_playlist_videos("p-1", sort_by="view_count", sort_dir="desc")
        self.assertEqual([i["id"] for i in items], ["v-2", "v-1"])

    def test_combined_filters_scoped_to_playlist(self) -> None:
        items, _ = database.get_playlist_videos("p-1", title="alpha")
        self.assertEqual([i["id"] for i in items], ["v-1"])


if __name__ == "__main__":
    unittest.main()
