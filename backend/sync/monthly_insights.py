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
