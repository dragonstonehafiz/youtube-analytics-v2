from __future__ import annotations

import unittest
from datetime import date

from sync.coverage import coalesce_missing_windows, missing_windows
from sync.monthly_insights import monthly_windows_for_range


class MissingWindowsTest(unittest.TestCase):
    def test_first_sync_has_no_covered_months(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 1), date(2024, 3, 31))
        result = missing_windows(windows, [])
        self.assertEqual([w.month for w in result], ["2024-01", "2024-02", "2024-03"])

    def test_fully_covered_history_leaves_nothing_missing(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 1), date(2024, 3, 31))
        result = missing_windows(windows, ["2024-01", "2024-02", "2024-03"])
        self.assertEqual(result, [])

    def test_internal_gap_is_found(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 1), date(2024, 3, 31))
        result = missing_windows(windows, ["2024-01", "2024-03"])
        self.assertEqual([w.month for w in result], ["2024-02"])

    def test_leading_and_trailing_gaps_are_found(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 1), date(2024, 3, 31))
        result = missing_windows(windows, ["2024-02"])
        self.assertEqual([w.month for w in result], ["2024-01", "2024-03"])

    def test_covered_months_outside_the_requested_range_have_no_effect(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 1), date(2024, 1, 31))
        result = missing_windows(windows, ["2023-12", "2024-02"])
        self.assertEqual([w.month for w in result], ["2024-01"])


class CoalesceMissingWindowsTest(unittest.TestCase):
    def test_empty_input_returns_no_ranges(self) -> None:
        self.assertEqual(coalesce_missing_windows([]), [])

    def test_single_window_becomes_one_range(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 1), date(2024, 1, 31))
        ranges = coalesce_missing_windows(windows)
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].months, ["2024-01"])
        self.assertEqual((ranges[0].start_date, ranges[0].end_date), ("2024-01-01", "2024-01-31"))

    def test_consecutive_months_coalesce_into_one_range(self) -> None:
        windows = monthly_windows_for_range(date(2023, 1, 1), date(2023, 6, 30))
        ranges = coalesce_missing_windows(windows)
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].months[0], "2023-01")
        self.assertEqual(ranges[0].months[-1], "2023-06")
        self.assertEqual((ranges[0].start_date, ranges[0].end_date), ("2023-01-01", "2023-06-30"))

    def test_a_run_longer_than_the_cap_splits_into_multiple_ranges(self) -> None:
        # A multi-year gap must never become one unbounded range: iter_video_analytics()
        # internally chunks a request into 12-month API calls, and coverage is only
        # written after the whole request succeeds — an uncapped range would bundle
        # several such chunks together, so a failure partway through would silently
        # discard the earlier chunks' already-successful progress too.
        windows = monthly_windows_for_range(date(2022, 1, 1), date(2024, 12, 31))
        ranges = coalesce_missing_windows(windows)
        self.assertEqual([len(r.months) for r in ranges], [12, 12, 12])
        self.assertEqual(ranges[0].months[0], "2022-01")
        self.assertEqual(ranges[0].months[-1], "2022-12")
        self.assertEqual(ranges[1].months[0], "2023-01")
        self.assertEqual(ranges[2].months[-1], "2024-12")
        # Each range's date bounds match exactly the months it covers, not the whole gap.
        self.assertEqual((ranges[0].start_date, ranges[0].end_date), ("2022-01-01", "2022-12-31"))
        self.assertEqual((ranges[1].start_date, ranges[1].end_date), ("2023-01-01", "2023-12-31"))

    def test_cap_boundary_is_exact(self) -> None:
        exactly_12 = monthly_windows_for_range(date(2024, 1, 1), date(2024, 12, 31))
        self.assertEqual(len(coalesce_missing_windows(exactly_12)), 1)

        exactly_13 = monthly_windows_for_range(date(2024, 1, 1), date(2025, 1, 31))
        ranges = coalesce_missing_windows(exactly_13)
        self.assertEqual([len(r.months) for r in ranges], [12, 1])

    def test_disjoint_gaps_produce_separate_ranges(self) -> None:
        all_windows = monthly_windows_for_range(date(2024, 1, 1), date(2024, 6, 30))
        missing = [w for w in all_windows if w.month != "2024-03"]
        ranges = coalesce_missing_windows(missing)
        self.assertEqual([r.months for r in ranges], [
            ["2024-01", "2024-02"],
            ["2024-04", "2024-05", "2024-06"],
        ])

    def test_year_boundary_is_treated_as_consecutive(self) -> None:
        windows = monthly_windows_for_range(date(2023, 11, 1), date(2024, 2, 29))
        ranges = coalesce_missing_windows(windows)
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0].months, ["2023-11", "2023-12", "2024-01", "2024-02"])

    def test_publish_date_clamp_is_preserved_on_the_first_range(self) -> None:
        windows = monthly_windows_for_range(date(2024, 1, 15), date(2024, 2, 29))
        ranges = coalesce_missing_windows(windows)
        self.assertEqual(ranges[0].start_date, "2024-01-15")


if __name__ == "__main__":
    unittest.main()
