from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from unittest import mock

from database import Playlist, Video, reader, writer
from database.reports import catalog
from sync import stages, status
from sync.stages import SyncCounts
from tests.support import (
    IsolatedDatabaseTestCase,
    make_fx_rate,
    make_playlist,
    make_playlist_item,
    make_video,
    make_video_analytics,
)


def _video_total(video_id: str) -> float | None:
    """Return a video's stored lifetime earnings."""
    stored = reader.select_one(Video, ("total_revenue_sgd",), where=[("id", "=", video_id)])
    assert stored is not None
    return stored.total_revenue_sgd


def _playlist_total(playlist_id: str) -> float | None:
    """Return a playlist's stored lifetime earnings."""
    stored = reader.select_one(Playlist, ("total_earnings_sgd",), where=[("id", "=", playlist_id)])
    assert stored is not None
    return stored.total_earnings_sgd


class LifetimeEarningsTest(IsolatedDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        writer.write_many([make_video("v-1"), make_video("v-2")])
        writer.write_many([make_fx_rate("2024-01-01", 2.0), make_fx_rate("2024-01-02", 1.5)])
        writer.write_many([
            make_video_analytics("v-1", "2024-01-01", estimated_revenue=5.0),
            make_video_analytics("v-1", "2024-01-02", estimated_revenue=2.0),
            make_video_analytics("v-1", "2024-01-03", estimated_revenue=100.0),  # no FX rate
            make_video_analytics("v-2", "2024-01-01", estimated_revenue=1.0),
        ])

    def test_sums_revenue_times_each_days_rate_and_skips_days_without_one(self) -> None:
        self.assertEqual(catalog.lifetime_earnings(["v-1"]), 13.0)

    def test_sums_distinct_videos_once_each(self) -> None:
        self.assertEqual(catalog.lifetime_earnings(["v-1", "v-2", "v-1"]), 15.0)

    def test_no_ids_or_no_analytics_is_zero(self) -> None:
        self.assertEqual(catalog.lifetime_earnings([]), 0.0)
        self.assertEqual(catalog.lifetime_earnings(["missing"]), 0.0)


class VideoAnalyticsEarningsTestCase(IsolatedDatabaseTestCase):
    """Two owned videos fetched for 2024-03-01 at a 2.0 rate, with 'today' frozen at 2024-03-15."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.update_sync_progress").start()
        mock_date = mock.patch("sync.stages.date").start()
        mock_date.today.return_value = date(2024, 3, 15)
        mock_date.fromisoformat = date.fromisoformat
        mock_date.side_effect = lambda *a, **k: date(*a, **k)

        writer.write_many([
            make_video("v-1", published_at="2024-03-01T00:00:00Z"),
            make_video("v-2", published_at="2024-03-01T00:00:00Z"),
            make_video("v-ext", own=False),
        ])
        writer.write(make_fx_rate("2024-03-01", 2.0))
        writer.write_many([make_playlist("p-1"), make_playlist("p-empty")])
        writer.write_many([
            make_playlist_item("pi-1", "p-1", "v-1", 0),
            make_playlist_item("pi-2", "p-1", "v-1", 1),
            make_playlist_item("pi-3", "p-1", "v-2", 2),
            make_playlist_item("pi-4", "p-1", "v-ext", 3),
            make_playlist_item("pi-5", "p-1", "missing", 4),
        ])
        self.revenue = {"v-1": 5.0, "v-2": 1.0}
        self.fail_on: dict[str, BaseException] = {}

    def _fetch(self, video_id: str, *args: object, **kwargs: object) -> Iterator[dict]:
        """Yield one 2024-03-01 analytics row per video, or raise the failure configured for it."""
        if video_id in self.fail_on:
            raise self.fail_on[video_id]
        yield make_video_analytics(video_id, "2024-03-01", estimated_revenue=self.revenue[video_id]).to_dict()

    def _sync(self) -> None:
        mock.patch("sync.stages.youtube.iter_video_analytics", side_effect=self._fetch).start()
        stages.sync_video_analytics("incremental", None, SyncCounts())


class VideoAnalyticsEarningsTest(VideoAnalyticsEarningsTestCase):
    def test_video_and_playlist_totals_are_stored(self) -> None:
        self._sync()

        self.assertEqual((_video_total("v-1"), _video_total("v-2")), (10.0, 2.0))
        # v-1 is listed twice but counts once; the external and missing members count nothing.
        self.assertEqual(_playlist_total("p-1"), 12.0)
        self.assertEqual(_playlist_total("p-empty"), 0.0)

    def test_a_revised_estimate_lowers_the_stored_total(self) -> None:
        writer.write(make_video_analytics("v-1", "2024-03-01", estimated_revenue=9.0))
        writer.update(Video(total_revenue_sgd=18.0), where=[("id", "=", "v-1")])

        self._sync()

        self.assertEqual(_video_total("v-1"), 10.0)

    def test_a_video_without_a_publish_date_keeps_its_total(self) -> None:
        writer.write(make_video("v-undated", published_at=None))
        writer.update(Video(total_revenue_sgd=7.0), where=[("id", "=", "v-undated")])

        self._sync()

        self.assertEqual(_video_total("v-undated"), 7.0)

    def test_traffic_sources_leave_totals_unchanged(self) -> None:
        writer.write(make_video_analytics("v-1", "2024-03-01", estimated_revenue=5.0))
        mock.patch("sync.stages.youtube.iter_video_traffic_sources", side_effect=lambda *a, **k: iter([])).start()

        stages.sync_video_traffic_sources("incremental", None, SyncCounts())

        self.assertEqual((_video_total("v-1"), _playlist_total("p-1")), (0.0, 0.0))


class InterruptedVideoAnalyticsEarningsTest(VideoAnalyticsEarningsTestCase):
    def test_a_failure_keeps_finished_video_totals_and_leaves_playlists_unchanged(self) -> None:
        writer.update(Playlist(total_earnings_sgd=99.0), where=[("id", "=", "p-1")])
        self.fail_on["v-2"] = RuntimeError("quota exceeded")

        with self.assertRaises(RuntimeError):
            self._sync()

        self.assertEqual((_video_total("v-1"), _video_total("v-2")), (10.0, 0.0))
        self.assertEqual(_playlist_total("p-1"), 99.0)

    def test_a_cancellation_leaves_playlists_unchanged(self) -> None:
        writer.update(Playlist(total_earnings_sgd=99.0), where=[("id", "=", "p-1")])
        self.fail_on["v-2"] = status.SyncCancelled()

        with self.assertRaises(status.SyncCancelled):
            self._sync()

        self.assertEqual(_video_total("v-1"), 10.0)
        self.assertEqual(_playlist_total("p-1"), 99.0)
