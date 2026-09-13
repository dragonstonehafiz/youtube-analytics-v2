from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from .monthly_insights import MonthlyWindow


@dataclass(frozen=True)
class CoverageRange:
    """One coalesced historical-backfill request: the date bounds to fetch, and the
    calendar months that request will fully cover once it succeeds."""
    start_date: str
    end_date: str
    months: list[str]


def missing_windows(windows: list[MonthlyWindow], covered_months: Collection[str]) -> list[MonthlyWindow]:
    """Return the windows whose month is not already in covered_months, preserving order."""
    covered = set(covered_months)
    return [window for window in windows if window.month not in covered]


def _month_after(month: str) -> str:
    """Return the YYYY-MM immediately following month."""
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year + 1:04d}-01" if mon == 12 else f"{year:04d}-{mon + 1:02d}"


# Matches the `months=12` chunk size both `iter_video_analytics()` and
# `iter_video_traffic_sources()` pass to `_chunk_date_range()` (youtube/analytics_api.py).
# Capping a coalesced range at this size means the generator services it as exactly one
# internal chunk, so one coverage write always corresponds to one exhausted API request —
# a failure partway through a multi-year gap only loses that one chunk's progress, never
# the earlier chunks a bigger, uncapped range would have silently re-bundled with it.
MAX_RANGE_MONTHS = 12


def coalesce_missing_windows(windows: list[MonthlyWindow]) -> list[CoverageRange]:
    """Group consecutive-calendar-month windows (oldest first, as returned by
    monthly_windows_for_range()) into the fewest contiguous date ranges of at most
    MAX_RANGE_MONTHS months each, so a multi-year historical gap costs one request per
    contiguous run of missing months (up to the cap) instead of one per month. A gap in
    the input (a month that's already covered) or reaching the cap both start a new range.
    """
    ranges: list[CoverageRange] = []
    for window in windows:
        if (
            ranges
            and len(ranges[-1].months) < MAX_RANGE_MONTHS
            and _month_after(ranges[-1].months[-1]) == window.month
        ):
            last = ranges[-1]
            ranges[-1] = CoverageRange(last.start_date, window.end_date, [*last.months, window.month])
        else:
            ranges.append(CoverageRange(window.start_date, window.end_date, [window.month]))
    return ranges
