from __future__ import annotations

import unittest

import database
from database import Video, reader
from routes.playlists import router as playlists_router
from routes.videos import router as videos_router
from tests.support import (
    IsolatedDatabaseTestCase,
    create_test_client,
    make_fx_rate,
    make_playlist,
    make_playlist_item,
    make_video,
    make_video_analytics,
)

EMPTY_STATS = {
    "legacy_video_count": 0, "legacy_video_views": 0, "legacy_video_earnings_sgd": 0.0,
    "legacy_short_count": 0, "legacy_short_views": 0, "legacy_short_earnings_sgd": 0.0,
    "new_video_count": 0, "new_video_views": 0, "new_video_earnings_sgd": 0.0,
    "new_short_count": 0, "new_short_views": 0, "new_short_earnings_sgd": 0.0,
    "total_comments": 0, "video_comments": 0, "short_comments": 0,
    "total_public": 0, "total_private": 0, "total_unlisted": 0,
}

# Catalog totals for every owned p-mix member, regardless of dates or publication buckets.
PLAYLIST_CATALOG = {
    "total_comments": 22, "video_comments": 16, "short_comments": 6,
    "total_public": 3, "total_private": 2, "total_unlisted": 1,
}
CHANNEL_CATALOG = {
    "total_comments": 33, "video_comments": 27, "short_comments": 6,
    "total_public": 4, "total_private": 2, "total_unlisted": 1,
}


def _stats(**overrides: object) -> dict:
    """Return the empty statistics response with the given fields replaced."""
    return {**EMPTY_STATS, **overrides}


class VideoStatisticsTestCase(IsolatedDatabaseTestCase):
    """Seeds a playlist whose analytics range differs from the channel's.

    p-mix analytics span 2023-12-20..2024-02-10; v-nonmember extends the channel range back to
    2022-06-01. p-mix also holds a duplicate, a dangling, a null, and an external membership.
    """

    def setUp(self) -> None:
        super().setUp()
        self.client = create_test_client(videos_router, playlists_router)
        self._seed()

    def _seed(self) -> None:
        """Seed videos, analytics, exchange rates, and playlists."""
        videos = (
            ("v-old", "Old Video", "video", "public", "2023-06-01T00:00:00Z", 5),
            ("v-new", "New Video", "video", "private", "2024-01-05T00:00:00Z", 3),
            ("v-short", "Quick Short", "short", "public", "2024-01-20T12:00:00Z", 2),
            ("v-hidden", "Hidden Clip", "video", "unlisted", "2024-01-15T00:00:00Z", 7),
            ("v-undated", "Undated Video", "video", "public", None, 1),
            ("v-silent", "Silent Short", "short", "private", "2024-01-18T00:00:00Z", 4),
            ("v-nonmember", "Other Video", "video", "public", "2023-01-01T00:00:00Z", 11),
            ("v-external", "External Video", "video", "public", "2024-01-06T00:00:00Z", 13),
        )
        for video_id, title, content_type, privacy_status, published_at, comments in videos:
            database.upsert_own_video(make_video(
                video_id, title, content_type=content_type, privacy_status=privacy_status,
                published_at=published_at or "2024-01-01T00:00:00Z", comment_count=comments,
            ))
        with database.get_connection() as conn:
            conn.execute("UPDATE videos SET published_at = NULL WHERE id = 'v-undated'")
            conn.execute("UPDATE videos SET own = 0 WHERE id = 'v-external'")

        analytics = (
            ("v-old", "2023-12-20", 10, 1.0),
            ("v-old", "2024-01-10", 20, 2.0),
            ("v-new", "2024-01-10", 40, 4.0),
            ("v-undated", "2024-01-12", 8, 1.0),
            ("v-short", "2024-01-25", 60, 1.0),
            ("v-hidden", "2024-02-10", 100, 10.0),
            ("v-nonmember", "2022-06-01", 500, 50.0),
            ("v-nonmember", "2024-01-10", 1000, 0.0),
            ("v-external", "2021-01-01", 9999, 99.0),
        )
        for video_id, day, views, revenue in analytics:
            database.upsert_video_analytics(make_video_analytics(video_id, day, views=views, estimated_revenue=revenue))
        for day, rate in (
            ("2022-06-01", 1.0), ("2023-12-20", 1.0), ("2024-01-10", 1.5),
            ("2024-01-12", 1.0), ("2024-01-25", 2.0), ("2024-02-10", 1.0),
        ):
            database.upsert_fx_rate(make_fx_rate(day, rate))

        for playlist_id in ("p-mix", "p-empty", "p-fallback"):
            database.upsert_playlist(make_playlist(playlist_id))
        members: tuple[tuple[str, str | None], ...] = (
            ("p-mix", "v-old"), ("p-mix", "v-old"), ("p-mix", "v-new"), ("p-mix", "v-short"),
            ("p-mix", "v-hidden"), ("p-mix", "v-undated"), ("p-mix", "v-silent"),
            ("p-mix", "v-external"), ("p-mix", "missing-video"), ("p-mix", None),
            ("p-fallback", "v-silent"),
        )
        for position, (playlist_id, member_id) in enumerate(members):
            database.upsert_playlist_item(make_playlist_item(f"pi-{position}", playlist_id, member_id, position))

    def _get(self, path: str, **params: str) -> dict:
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _playlist(self, playlist_id: str = "p-mix", **params: str) -> dict:
        return self._get(f"/playlists/{playlist_id}/videos/stats", **params)

    def _channel(self, **params: str) -> dict:
        return self._get("/videos/stats", **params)


class PlaylistStatisticsRouteTest(VideoStatisticsTestCase):
    def test_default_dates_use_playlist_analytics_range(self) -> None:
        self.assertEqual(self._playlist(), _stats(
            legacy_video_count=1, legacy_video_views=30, legacy_video_earnings_sgd=4.0,
            new_video_count=2, new_video_views=140, new_video_earnings_sgd=16.0,
            new_short_count=2, new_short_views=60, new_short_earnings_sgd=2.0,
            **PLAYLIST_CATALOG,
        ))

    def test_explicit_dates_bucket_by_publication_and_keep_catalog_totals(self) -> None:
        """v-short is published at noon on the end date and still counts as New."""
        self.assertEqual(self._playlist(start_date="2024-01-10", end_date="2024-01-20"), _stats(
            legacy_video_count=2, legacy_video_views=60, legacy_video_earnings_sgd=9.0,
            new_video_count=1, new_short_count=2,
            **PLAYLIST_CATALOG,
        ))

    def test_video_published_on_start_date_is_new(self) -> None:
        self.assertEqual(self._playlist(start_date="2024-01-05", end_date="2024-01-20"), _stats(
            legacy_video_count=1, legacy_video_views=20, legacy_video_earnings_sgd=3.0,
            new_video_count=2, new_video_views=40, new_video_earnings_sgd=6.0,
            new_short_count=2,
            **PLAYLIST_CATALOG,
        ))

    def test_omitted_start_uses_playlist_analytics_minimum(self) -> None:
        self.assertEqual(self._playlist(end_date="2024-01-20"), _stats(
            legacy_video_count=1, legacy_video_views=30, legacy_video_earnings_sgd=4.0,
            new_video_count=2, new_video_views=40, new_video_earnings_sgd=6.0,
            new_short_count=2,
            **PLAYLIST_CATALOG,
        ))

    def test_omitted_end_uses_playlist_analytics_maximum(self) -> None:
        self.assertEqual(self._playlist(start_date="2024-01-10"), _stats(
            legacy_video_count=2, legacy_video_views=60, legacy_video_earnings_sgd=9.0,
            new_video_count=1, new_video_views=100, new_video_earnings_sgd=10.0,
            new_short_count=2, new_short_views=60, new_short_earnings_sgd=2.0,
            **PLAYLIST_CATALOG,
        ))

    def test_title_filter_keeps_unfiltered_analytics_date_defaults(self) -> None:
        """Filtered bounds would start at 2024-02-10 and move v-hidden into Legacy."""
        self.assertEqual(self._playlist(title="Hidden"), _stats(
            new_video_count=1, new_video_views=100, new_video_earnings_sgd=10.0,
            total_comments=7, video_comments=7, total_unlisted=1,
        ))

    def test_title_filter_matches_video_id(self) -> None:
        self.assertEqual(self._playlist(title="v-short"), _stats(
            new_short_count=1, new_short_views=60, new_short_earnings_sgd=2.0,
            total_comments=2, short_comments=2, total_public=1,
        ))

    def test_content_type_filter(self) -> None:
        self.assertEqual(self._playlist(content_type="video"), _stats(
            legacy_video_count=1, legacy_video_views=30, legacy_video_earnings_sgd=4.0,
            new_video_count=2, new_video_views=140, new_video_earnings_sgd=16.0,
            total_comments=16, video_comments=16,
            total_public=2, total_private=1, total_unlisted=1,
        ))

    def test_privacy_filter(self) -> None:
        self.assertEqual(self._playlist(privacy_status="private"), _stats(
            new_video_count=1, new_video_views=40, new_video_earnings_sgd=6.0,
            new_short_count=1,
            total_comments=7, video_comments=3, short_comments=4, total_private=2,
        ))

    def test_combined_filters(self) -> None:
        self.assertEqual(self._playlist(content_type="short", privacy_status="public", title="Short"), _stats(
            new_short_count=1, new_short_views=60, new_short_earnings_sgd=2.0,
            total_comments=2, short_comments=2, total_public=1,
        ))

    def test_filters_matching_only_a_nonmember_return_zeroes(self) -> None:
        self.assertEqual(self._playlist(title="Other"), EMPTY_STATS)

    def test_publication_dates_are_used_without_analytics(self) -> None:
        self.assertEqual(self._playlist("p-fallback"), _stats(
            new_short_count=1, total_comments=4, short_comments=4, total_private=1,
        ))

    def test_empty_playlist_returns_zeroed_statistics(self) -> None:
        self.assertEqual(self._playlist("p-empty"), EMPTY_STATS)

    def test_missing_playlist_returns_404(self) -> None:
        response = self.client.get("/playlists/nope/videos/stats")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Playlist not found"})


class ChannelStatisticsRouteTest(VideoStatisticsTestCase):
    def test_default_dates_use_channel_analytics_range(self) -> None:
        self.assertEqual(self._channel(), _stats(
            new_video_count=4, new_video_views=1670, new_video_earnings_sgd=70.0,
            new_short_count=2, new_short_views=60, new_short_earnings_sgd=2.0,
            **CHANNEL_CATALOG,
        ))

    def test_explicit_dates(self) -> None:
        self.assertEqual(self._channel(start_date="2024-01-10", end_date="2024-01-20"), _stats(
            legacy_video_count=3, legacy_video_views=1060, legacy_video_earnings_sgd=9.0,
            new_video_count=1, new_short_count=2,
            **CHANNEL_CATALOG,
        ))

    def test_title_filter_keeps_unfiltered_analytics_date_defaults(self) -> None:
        self.assertEqual(self._channel(title="Hidden"), _stats(
            new_video_count=1, new_video_views=100, new_video_earnings_sgd=10.0,
            total_comments=7, video_comments=7, total_unlisted=1,
        ))

    def test_playlist_of_every_owned_video_matches_channel(self) -> None:
        owned = reader.select(Video, ("id",), where=[("own", "=", True)], order_by=("id",))
        for position, video_id in enumerate(video.id for video in owned):
            database.upsert_playlist_item(make_playlist_item(f"all-{position}", "p-empty", video_id, position))
        for params in ({}, {"start_date": "2024-01-10", "end_date": "2024-01-20"}, {"content_type": "short"}):
            with self.subTest(params=params):
                self.assertEqual(self._playlist("p-empty", **params), self._channel(**params))


class VideoStatisticsScopeTest(VideoStatisticsTestCase):
    PLAYLIST_MEMBERS = ["v-old", "v-new", "v-short", "v-hidden", "v-undated", "v-silent"]

    def test_omitted_scope_matches_channel(self) -> None:
        self.assertEqual(database.get_video_stats(), self._channel())

    def test_empty_scope_returns_zeroed_statistics(self) -> None:
        self.assertEqual(database.get_video_stats(video_ids=[]), EMPTY_STATS)

    def test_member_scope_matches_playlist_route(self) -> None:
        self.assertEqual(database.get_video_stats(video_ids=self.PLAYLIST_MEMBERS), self._playlist())

    def test_duplicate_ids_do_not_multiply_results(self) -> None:
        self.assertEqual(
            database.get_video_stats(video_ids=[*self.PLAYLIST_MEMBERS, "v-old", "v-hidden"]),
            database.get_video_stats(video_ids=self.PLAYLIST_MEMBERS),
        )

    def test_external_and_nonexistent_ids_are_ignored(self) -> None:
        self.assertEqual(
            database.get_video_stats(video_ids=[*self.PLAYLIST_MEMBERS, "v-external", "missing-video"]),
            database.get_video_stats(video_ids=self.PLAYLIST_MEMBERS),
        )

    def test_scope_of_only_external_and_nonexistent_ids_returns_zeroes(self) -> None:
        self.assertEqual(database.get_video_stats(video_ids=["v-external", "missing-video"]), EMPTY_STATS)

    def test_restricted_scope_uses_its_own_analytics_range(self) -> None:
        """The scope's analytics start (2024-01-25) follows both publication dates, so both are Legacy."""
        self.assertEqual(database.get_video_stats(video_ids=["v-short", "v-hidden"]), _stats(
            legacy_video_count=1, legacy_video_views=100, legacy_video_earnings_sgd=10.0,
            legacy_short_count=1, legacy_short_views=60, legacy_short_earnings_sgd=2.0,
            total_comments=9, video_comments=7, short_comments=2, total_public=1, total_unlisted=1,
        ))

    def test_scope_accepts_a_set(self) -> None:
        self.assertEqual(
            database.get_video_stats(video_ids=set(self.PLAYLIST_MEMBERS)),
            database.get_video_stats(video_ids=self.PLAYLIST_MEMBERS),
        )


if __name__ == "__main__":
    unittest.main()
