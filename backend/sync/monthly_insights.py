from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class MonthlyWindow:
    """One calendar-month Search & Related Insights window.

    `month` is the canonical `YYYY-MM` storage identity; `start_date`/`end_date` are the
    exact ISO dates to request from the Analytics API for that month.
    """
    month: str
    start_date: str
    end_date: str


def monthly_search_windows(today: date) -> list[MonthlyWindow]:
    """Return the previous-month and current-month windows for Search & Related Insights,
    as of `today`. Pure calendar arithmetic — no clock reads, no I/O.

    The previous-month window always spans that month's full run (1st through last day).
    The current-month window runs from its 1st through yesterday, and is omitted
    entirely when `today` is the first day of the month (that window would otherwise be
    empty). Previous month is always returned first.
    """
    first_of_current = today.replace(day=1)
    last_of_previous = first_of_current - timedelta(days=1)
    first_of_previous = last_of_previous.replace(day=1)

    windows = [
        MonthlyWindow(
            month=first_of_previous.strftime("%Y-%m"),
            start_date=first_of_previous.isoformat(),
            end_date=last_of_previous.isoformat(),
        )
    ]

    yesterday = today - timedelta(days=1)
    if yesterday >= first_of_current:
        windows.append(
            MonthlyWindow(
                month=first_of_current.strftime("%Y-%m"),
                start_date=first_of_current.isoformat(),
                end_date=yesterday.isoformat(),
            )
        )

    return windows


def weekly_sub_windows(month_window: MonthlyWindow) -> list[tuple[str, str]]:
    """Split one MonthlyWindow's start/end into consecutive 7-day (start_date, end_date)
    chunks, oldest first, clamped to the window's own bounds — the last chunk may be
    shorter than 7 days. Pure date arithmetic; makes no API calls itself.

    Each Search Analytics detail request is hard-capped at 25 result rows total, with
    no pagination past that (verified live: a second page returns HTTP 500, not more
    data — see search-insights-api-findings.md). Narrowing each request to a week
    instead of a whole month raises how many distinct terms a video can have named
    before hitting that cap, since the cap applies per request, not per month. The
    caller fetches one API request per returned chunk and combines their results
    in memory before a single upsert for the month, so this does not change what
    gets stored (still one row per video/month/term) — only how much of a month's
    real search traffic gets captured before the per-request cap discards the rest.
    """
    start = date.fromisoformat(month_window.start_date)
    end = date.fromisoformat(month_window.end_date)
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=6), end)
        chunks.append((current.isoformat(), chunk_end.isoformat()))
        current = chunk_end + timedelta(days=1)
    return chunks


def monthly_windows_for_range(start: date, end: date) -> list[MonthlyWindow]:
    """Return one MonthlyWindow per calendar month from `start` through `end`, inclusive,
    oldest first. Each window's dates are clamped to `start`/`end` within its month, so
    the first and last months may be partial. Empty when `start` is after `end`.

    Pure date arithmetic; makes no API calls itself. The caller fetches one API request
    per returned window, exactly like `monthly_search_windows`'s two windows already do.
    """
    if start > end:
        return []

    windows = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        first_of_month = date(year, month, 1)
        last_of_month = (
            date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        ) - timedelta(days=1)
        windows.append(
            MonthlyWindow(
                month=f"{year:04d}-{month:02d}",
                start_date=max(start, first_of_month).isoformat(),
                end_date=min(end, last_of_month).isoformat(),
            )
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return windows
