from __future__ import annotations

from datetime import date
from unittest import mock

import database
from sync import stages
from sync.stages import SyncCounts
from tests.support import IsolatedDatabaseTestCase, make_video


class VideoAnalyticsCoverageTestCase(IsolatedDatabaseTestCase):
    """Freezes 'today' at 2024-03-15 so previous month is 2024-02 (full) and current
    month is 2024-03 (partial, through 2024-03-14). A video published 2023-10-01 makes
    2023-10 through 2024-01 the historical-backfill months, ahead of that pair."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(mock.patch.stopall)
        mock.patch("sync.stages.status.update_sync_progress").start()
        mock_date = mock.patch("sync.stages.date").start()
        mock_date.today.return_value = date(2024, 3, 15)
        mock_date.fromisoformat = date.fromisoformat
        mock_date.side_effect = lambda *a, **k: date(*a, **k)
        database.upsert_own_video(make_video("v1", "Alpha", published_at="2023-10-01T00:00:00Z"))

    def _iter_mock(self, results: list) -> mock.Mock:
        return mock.patch("sync.stages.youtube.iter_video_analytics", side_effect=results).start()


class FirstSyncTest(VideoAnalyticsCoverageTestCase):
    def test_historical_range_and_forced_pair_are_all_requested_and_covered(self) -> None:
        # Nothing covered yet, so publish-through-yesterday is one contiguous gap: the
        # historical sweep and the forced previous/current pair merge into one range.
        fetch = self._iter_mock([iter([])])
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        stages.sync_video_analytics("incremental", None, SyncCounts())

        calls = [(c.args[1], c.args[2]) for c in fetch.call_args_list]
        self.assertEqual(calls, [("2023-10-01", "2024-03-14")])
        covered = database.get_covered_periods("video_analytics", "v1", "2023-01", "2024-12")
        self.assertEqual(covered, {"2023-10", "2023-11", "2023-12", "2024-01", "2024-02", "2024-03"})


class SteadyStateTest(VideoAnalyticsCoverageTestCase):
    def test_covered_history_is_skipped_but_the_forced_pair_still_runs(self) -> None:
        database.upsert_coverage("video_analytics", "v1", ["2023-10", "2023-11", "2023-12", "2024-01"])
        # Feb and Mar are adjacent months, so the forced pair coalesces into one range.
        fetch = self._iter_mock([iter([])])
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        stages.sync_video_analytics("incremental", None, SyncCounts())

        calls = [(c.args[1], c.args[2]) for c in fetch.call_args_list]
        self.assertEqual(calls, [("2024-02-01", "2024-03-14")])

    def test_forced_pair_refreshes_coverage_timestamps_even_when_already_covered(self) -> None:
        # Feb (already covered) sorts chronologically before Mar (the only genuine
        # gap) — a regression test that appending Feb after Mar doesn't break
        # coalescing into one adjacent range.
        database.upsert_coverage("video_analytics", "v1", ["2023-10", "2023-11", "2023-12", "2024-01", "2024-02"])
        fetch = self._iter_mock([iter([])])
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        stages.sync_video_analytics("incremental", None, SyncCounts())

        calls = [(c.args[1], c.args[2]) for c in fetch.call_args_list]
        self.assertEqual(calls, [("2024-02-01", "2024-03-14")])
        covered = database.get_covered_periods("video_analytics", "v1", "2024-02", "2024-03")
        self.assertEqual(covered, {"2024-02", "2024-03"})


class InternalGapTest(VideoAnalyticsCoverageTestCase):
    def test_a_disjoint_internal_gap_is_requested_as_two_ranges(self) -> None:
        # Oct and Dec covered, Nov not: Nov is an isolated single-month range. Jan
        # through Mar are all uncovered/forced and mutually adjacent, so they coalesce
        # into one range.
        database.upsert_coverage("video_analytics", "v1", ["2023-10", "2023-12"])
        fetch = self._iter_mock([iter([]), iter([])])
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        stages.sync_video_analytics("incremental", None, SyncCounts())

        calls = [(c.args[1], c.args[2]) for c in fetch.call_args_list]
        self.assertEqual(calls, [
            ("2023-11-01", "2023-11-30"),
            ("2024-01-01", "2024-03-14"),
        ])
        covered = database.get_covered_periods("video_analytics", "v1", "2023-01", "2024-12")
        self.assertEqual(covered, {"2023-10", "2023-11", "2023-12", "2024-01", "2024-02", "2024-03"})


class FailureLeavesRangeUncoveredTest(VideoAnalyticsCoverageTestCase):
    def test_a_later_range_failing_does_not_uncover_an_earlier_successful_one(self) -> None:
        database.upsert_coverage("video_analytics", "v1", ["2023-10", "2023-12"])
        self._iter_mock([iter([]), RuntimeError("quota exceeded")])
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        with self.assertRaises(RuntimeError):
            stages.sync_video_analytics("incremental", None, SyncCounts())

        covered = database.get_covered_periods("video_analytics", "v1", "2023-01", "2024-12")
        self.assertEqual(covered, {"2023-10", "2023-11", "2023-12"})
        self.assertNotIn("2024-01", covered)
        self.assertNotIn("2024-02", covered)
        self.assertNotIn("2024-03", covered)


class MultiYearBacklogTest(VideoAnalyticsCoverageTestCase):
    def test_a_persistent_failure_does_not_erase_earlier_chunks_progress_on_retry(self) -> None:
        # Published 2015-01-01: from-scratch backfill through 2024-03-14 spans over
        # 12 years, so it must split into multiple <=12-month chunks (see
        # sync.coverage.MAX_RANGE_MONTHS) rather than one unbounded range — otherwise a
        # persistent failure on a later chunk would silently discard already-succeeded
        # earlier chunks' progress every retry, and backfill would never advance.
        # Remove the base class's "v1" fixture so this test's mock only has to reason
        # about one video's request shape.
        with database.get_connection() as conn:
            conn.execute("DELETE FROM videos WHERE id = 'v1'")
        database.upsert_own_video(make_video("v-old", "Old Video", published_at="2015-01-01T00:00:00Z"))

        def always_fails_after_first_chunk(video_id, start, range_end, **kwargs):
            if start == "2015-01-01":
                return iter([])
            raise RuntimeError("quota exceeded")

        fetch = mock.patch(
            "sync.stages.youtube.iter_video_analytics", side_effect=always_fails_after_first_chunk
        ).start()
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        with self.assertRaises(RuntimeError):
            stages.sync_video_analytics("incremental", None, SyncCounts())
        first_attempt = database.get_covered_periods("video_analytics", "v-old", "2015-01", "2015-12")
        self.assertEqual(first_attempt, {f"2015-{m:02d}" for m in range(1, 13)})

        # Retrying (e.g. next Incremental run) must not re-request 2015 at all, since
        # it's already covered — only the still-uncovered later chunk is retried.
        fetch.reset_mock()
        with self.assertRaises(RuntimeError):
            stages.sync_video_analytics("incremental", None, SyncCounts())
        requested_starts = {call.args[1] for call in fetch.call_args_list}
        self.assertNotIn("2015-01-01", requested_starts)


class YearScopeTest(VideoAnalyticsCoverageTestCase):
    def test_year_scope_marks_every_month_it_spans_including_the_current_one(self) -> None:
        database.upsert_own_video(make_video("v2", "Beta", published_at="2018-01-01T00:00:00Z"))
        self._iter_mock([iter([])])
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        stages.sync_video_analytics("year", 2019, SyncCounts())

        covered = database.get_covered_periods("video_analytics", "v2", "2019-01", "2019-12")
        self.assertEqual(len(covered), 12)

    def test_all_scope_marks_the_still_open_current_month_too(self) -> None:
        self._iter_mock([iter([])])
        mock.patch("sync.stages.database.upsert_video_analytics").start()

        stages.sync_video_analytics("all", None, SyncCounts())

        covered = database.get_covered_periods("video_analytics", "v1", "2023-01", "2024-12")
        self.assertEqual(covered, {"2023-10", "2023-11", "2023-12", "2024-01", "2024-02", "2024-03"})


class TrafficSourcesParityTest(VideoAnalyticsCoverageTestCase):
    def test_traffic_sources_shares_the_same_selection_and_writes_its_own_collector(self) -> None:
        fetch = mock.patch(
            "sync.stages.youtube.iter_video_traffic_sources", side_effect=[iter([])]
        ).start()
        mock.patch("sync.stages.database.upsert_video_traffic_source").start()

        stages.sync_video_traffic_sources("incremental", None, SyncCounts())

        self.assertEqual(fetch.call_count, 1)
        covered = database.get_covered_periods("video_traffic_sources", "v1", "2023-01", "2024-12")
        self.assertEqual(covered, {"2023-10", "2023-11", "2023-12", "2024-01", "2024-02", "2024-03"})
        # video_analytics coverage is untouched by the traffic-sources sync.
        self.assertEqual(database.get_covered_periods("video_analytics", "v1", "2023-01", "2024-12"), set())
