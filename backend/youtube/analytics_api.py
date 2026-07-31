from __future__ import annotations

import calendar
import time
from datetime import date, timedelta
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from logging_config import get_logger

from .auth import get_credentials

_logger = get_logger("sync")

_VIDEO_DAILY_METRICS = [
    "views",
    "estimatedMinutesWatched",
    "estimatedRevenue",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "subscribersGained",
    "subscribersLost",
]

_TRAFFIC_SOURCE_METRICS = [
    "views",
    "estimatedMinutesWatched",
]


def _analytics_client() -> Any:
    """Return an authenticated YouTube Analytics API v2 client."""
    return build("youtubeAnalytics", "v2", credentials=get_credentials())


def _log_page(
    resource: str,
    page: int,
    item_count: int,
    start_index: int,
    owner: str | None = None,
    owner_name: str | None = None,
) -> None:
    """Log one fetched Analytics page.

    `owner`/`owner_name` identify the video the report is filtered to. The name is
    rendered last and `repr`-quoted so a title containing spaces or newlines cannot
    corrupt the fields before it.
    """
    owner_field = f" owner={owner}" if owner else ""
    name_field = f" owner_name={owner_name!r}" if owner_name else ""
    _logger.debug(
        "%s page=%d items=%d start_index=%d%s%s",
        resource, page, item_count, start_index, owner_field, name_field,
    )


def _analytics_query(service: Any, params: dict, max_attempts: int = 5) -> dict:
    """Execute a YouTube Analytics reports.query with exponential-backoff retry."""
    for attempt in range(1, max_attempts + 1):
        try:
            return service.reports().query(**params).execute()
        except HttpError as exc:
            status_code = int(exc.resp.status)
            error_text = exc.content.decode("utf-8") if exc.content else str(exc)
            is_quota = any(t in error_text for t in ("rateLimitExceeded", "quotaExceeded"))
            should_retry = status_code >= 500 or (status_code in {403, 429} and is_quota)
            if should_retry and attempt < max_attempts:
                delay = min(2 ** (attempt - 1), 30)
                reason = "server" if status_code >= 500 else "quota"
                _logger.warning(
                    "analytics_query retry attempt=%d status=%d reason=%s delay=%d",
                    attempt, status_code, reason, delay,
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"YouTube Analytics API error: {exc}") from exc
    return {}


def _chunk_date_range(start: str, end: str, months: int = 4) -> list[tuple[str, str]]:
    """Split a date range into chunks of N months."""
    chunks: list[tuple[str, str]] = []
    current = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    while current <= end_date:
        month = current.month - 1 + months
        year = current.year + month // 12
        month = month % 12 + 1
        last_day = calendar.monthrange(year, month)[1]
        chunk_end = min(date(year, month, last_day) - timedelta(days=1), end_date)
        chunks.append((current.isoformat(), chunk_end.isoformat()))
        current = chunk_end + timedelta(days=1)
    return chunks


def _fetch_analytics_rows(
    service: Any, params: dict, resource: str = "analytics_rows", owner_name: str | None = None
) -> list[dict[str, Any]]:
    """Fetch all paginated rows from an Analytics reports.query call.

    Pagination here is `startIndex`-based rather than token-based, and an empty page
    already terminates the loop, so a page record is routine DEBUG detail. `owner_name`
    names the video the report is filtered to; its id is read back from the filter.
    """
    results: list[dict[str, Any]] = []
    headers: list[str] | None = None
    max_results = params.get("maxResults", 200)
    owner = params.get("filters", "").removeprefix("video==") or None
    page = 0

    while True:
        response = _analytics_query(service, params)
        rows = response.get("rows") or []
        if headers is None:
            headers = [h["name"] for h in response.get("columnHeaders", [])]
        for row in rows:
            results.append({headers[i]: row[i] for i in range(len(headers))})
        page += 1
        _log_page(resource, page, len(rows), params.get("startIndex", 1), owner, owner_name)
        if not rows:
            break
        params = {**params, "startIndex": params.get("startIndex", 1) + max_results}
        time.sleep(0.2)

    return results


def iter_video_analytics(
    video_id: str,
    start_date: str,
    end_date: str,
    publish_date: str | None = None,
    title: str | None = None,
):
    """Yield daily analytics rows for a single video, one year-chunk at a time.

    Clamps start_date to publish_date if provided, skips entirely if the video
    hasn't been published yet within the requested range. maxResults is set high
    enough that a full year (365 rows) always fits in a single page - the API has
    no documented upper bound on maxResults, so this avoids pagination entirely
    in the common case (confirmed by a live full-year test returning all 365 days
    in one call with no gaps).
    """
    effective_start = start_date
    if publish_date:
        if publish_date > end_date:
            return
        if publish_date > start_date:
            effective_start = publish_date

    service = _analytics_client()

    for chunk_start, chunk_end in _chunk_date_range(effective_start, end_date, months=12):
        params = {
            "ids": "channel==MINE",
            "startDate": chunk_start,
            "endDate": chunk_end,
            "metrics": ",".join(_VIDEO_DAILY_METRICS),
            "dimensions": "day",
            "filters": f"video=={video_id}",
            "sort": "day",
            "maxResults": 2000,
            "startIndex": 1,
        }
        for row in _fetch_analytics_rows(service, params, "video_analytics_rows", title):
            yield {
                "video_id": video_id,
                "date": row.get("day"),
                "views": row.get("views"),
                "watch_time_minutes": row.get("estimatedMinutesWatched"),
                "estimated_revenue": row.get("estimatedRevenue"),
                "average_view_duration_seconds": row.get("averageViewDuration"),
                "average_view_percentage": row.get("averageViewPercentage"),
                "likes": row.get("likes"),
                "subscribers_gained": row.get("subscribersGained"),
                "subscribers_lost": row.get("subscribersLost"),
            }


def iter_video_traffic_sources(
    video_id: str,
    start_date: str,
    end_date: str,
    publish_date: str | None = None,
    title: str | None = None,
):
    """Yield daily traffic-source breakdown rows for a single video, one year-chunk at a time.

    Queries dimensions=day,insightTrafficSourceType per 1-year window so each API
    call returns one row per (day, traffic source type) pair. Clamps start_date to
    publish_date if provided. maxResults is set well above the theoretical ceiling
    of 365 days x 21 traffic source types (7665 rows) so a full year always fits in
    a single page - confirmed by a live full-year test (2883 rows, 365/365 days
    covered, no gaps) returned in one call with no pagination needed.
    """
    effective_start = start_date
    if publish_date:
        if publish_date > end_date:
            return
        if publish_date > start_date:
            effective_start = publish_date

    service = _analytics_client()

    for chunk_start, chunk_end in _chunk_date_range(effective_start, end_date, months=12):
        params = {
            "ids": "channel==MINE",
            "startDate": chunk_start,
            "endDate": chunk_end,
            "metrics": ",".join(_TRAFFIC_SOURCE_METRICS),
            "dimensions": "day,insightTrafficSourceType",
            "filters": f"video=={video_id}",
            "sort": "day,insightTrafficSourceType",
            "maxResults": 10000,
            "startIndex": 1,
        }
        for row in _fetch_analytics_rows(service, params, "video_traffic_sources_rows", title):
            yield {
                "video_id": video_id,
                "date": row.get("day"),
                "traffic_source_type": row.get("insightTrafficSourceType"),
                "views": row.get("views"),
                "watch_time_minutes": row.get("estimatedMinutesWatched"),
            }
