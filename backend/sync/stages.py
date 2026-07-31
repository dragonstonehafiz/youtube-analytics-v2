from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import database
import youtube
from logging_config import get_logger

from . import status

# Incremental syncs re-fetch this many days before the last stored date, since
# both analytics and traffic-source metrics for recent days are not fully
# settled by the API until some time after the day ends.
INCREMENTAL_LOOKBACK_DAYS = 7

_logger = get_logger("sync")


@dataclass
class SyncCounts:
    """Mutable running totals for a single sync stage, accumulated as work happens."""
    rows_fetched: int = 0
    rows_written: int = 0
    rows_deleted: int = 0


def _incremental_lookback_start(last_date: str | None, publish_date: str) -> str:
    """Return the incremental sync start date: publish_date if never synced,
    otherwise INCREMENTAL_LOOKBACK_DAYS before last_date, clamped to publish_date."""
    if not last_date:
        return publish_date
    start = (date.fromisoformat(last_date) - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).isoformat()
    return max(start, publish_date)


def sync_videos(counts: SyncCounts) -> None:
    """Fetch all channel videos, upsert, then delete any DB videos not returned by the API."""
    uploads_id = youtube.fetch_uploads_playlist_id()
    shorts_ids = youtube.fetch_shorts_video_ids(uploads_id)
    all_ids = youtube.fetch_all_video_ids(uploads_id)

    all_videos: list[dict] = []
    for i in range(0, len(all_ids), 50):
        batch = all_ids[i : i + 50]
        for video in youtube.fetch_videos(batch):
            video["content_type"] = "short" if video["id"] in shorts_ids else "video"
            all_videos.append(video)
            counts.rows_fetched += 1

    for video in all_videos:
        database.upsert_video(video)
        counts.rows_written += 1

    counts.rows_deleted += database.delete_videos_not_in([v["id"] for v in all_videos])


def sync_playlists(counts: SyncCounts) -> None:
    """Fetch all playlists and their items, upsert, then delete any DB playlists not returned by the API."""
    playlists = youtube.fetch_playlists()
    all_items: dict[str, list[dict]] = {}
    for playlist in playlists:
        items = youtube.fetch_playlist_items(playlist["id"], playlist_title=playlist.get("title"))
        all_items[playlist["id"]] = items
        counts.rows_fetched += 1 + len(items)

    for playlist in playlists:
        database.upsert_playlist(playlist)
        counts.rows_written += 1
        counts.rows_deleted += database.delete_playlist_items(playlist["id"])
        for item in all_items[playlist["id"]]:
            database.upsert_playlist_item(item)
            counts.rows_written += 1

    counts.rows_deleted += database.delete_playlists_not_in([p["id"] for p in playlists])


def sync_video_analytics(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Fetch daily analytics for every video.

    scope="incremental" re-fetches starting INCREMENTAL_LOOKBACK_DAYS before the last
    synced date (not right after it), since analytics metrics for recent days are not
    fully settled by the API until some time after that day ends — upserting re-pulled
    days is a no-op once the data has settled, and corrects any recent day that was
    stored before its data had fully arrived. scope="year" refetches the given year;
    scope="all" refetches each video's entire history.
    """
    today = date.today()
    end_date = (today - timedelta(days=1)).isoformat()

    video_ids = database.get_all_video_ids()
    total = len(video_ids)
    for i, video_id in enumerate(video_ids, start=1):
        status.set_message(f"Syncing video analytics ({i}/{total})...")
        video = database.get_video(video_id)
        if not video or not video.get("published_at"):
            _logger.debug(
                "video_analytics %d/%d video=%s skipped reason=no_publish_date title=%r",
                i, total, video_id, video.get("title") if video else None,
            )
            continue
        publish_date = video["published_at"][:10]
        title = video.get("title")

        if scope == "year":
            start = max(publish_date, f"{year}-01-01")
            range_end = min(end_date, f"{year}-12-31")
        elif scope == "all":
            start = publish_date
            range_end = end_date
        else:
            last_date = database.get_last_analytics_date(video_id)
            start = _incremental_lookback_start(last_date, publish_date)
            range_end = end_date

        if start > range_end:
            _logger.debug(
                "video_analytics %d/%d video=%s skipped reason=empty_range title=%r",
                i, total, video_id, title,
            )
            continue

        rows_before = counts.rows_fetched
        for row in youtube.iter_video_analytics(
            video_id, start, range_end, publish_date=publish_date, title=title
        ):
            counts.rows_fetched += 1
            database.upsert_video_analytics(row)
            counts.rows_written += 1
        _logger.debug(
            "video_analytics %d/%d video=%s rows=%d title=%r",
            i, total, video_id, counts.rows_fetched - rows_before, title,
        )


def sync_video_traffic_sources(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Fetch daily traffic-source breakdowns for every video.

    scope="incremental" re-fetches starting INCREMENTAL_LOOKBACK_DAYS before the last
    synced date (not right after it), since traffic-source data for a given day is not
    fully available from the API until some time after that day ends — upserting
    re-pulled days is a no-op once the data has settled, and corrects any recent day
    that was stored before its data had fully arrived. scope="year" refetches the
    given year; scope="all" refetches each video's entire history.
    """
    today = date.today()
    end_date = (today - timedelta(days=1)).isoformat()

    video_ids = database.get_all_video_ids()
    total = len(video_ids)
    for i, video_id in enumerate(video_ids, start=1):
        status.set_message(f"Syncing traffic sources ({i}/{total})...")
        video = database.get_video(video_id)
        if not video or not video.get("published_at"):
            _logger.debug(
                "video_traffic_sources %d/%d video=%s skipped reason=no_publish_date title=%r",
                i, total, video_id, video.get("title") if video else None,
            )
            continue
        publish_date = video["published_at"][:10]
        title = video.get("title")

        if scope == "year":
            start = max(publish_date, f"{year}-01-01")
            range_end = min(end_date, f"{year}-12-31")
        elif scope == "all":
            start = publish_date
            range_end = end_date
        else:
            last_date = database.get_last_traffic_source_date(video_id)
            start = _incremental_lookback_start(last_date, publish_date)
            range_end = end_date

        if start > range_end:
            _logger.debug(
                "video_traffic_sources %d/%d video=%s skipped reason=empty_range title=%r",
                i, total, video_id, title,
            )
            continue

        rows_before = counts.rows_fetched
        for row in youtube.iter_video_traffic_sources(
            video_id, start, range_end, publish_date=publish_date, title=title
        ):
            counts.rows_fetched += 1
            database.upsert_video_traffic_source(row)
            counts.rows_written += 1
        _logger.debug(
            "video_traffic_sources %d/%d video=%s rows=%d title=%r",
            i, total, video_id, counts.rows_fetched - rows_before, title,
        )


def sync_fx_rates(counts: SyncCounts) -> None:
    """Fetch daily USD/SGD rates from Yahoo Finance, filling weekends/holidays with last known rate."""
    import yfinance as yf
    import pandas as pd

    yesterday = date.today() - timedelta(days=1)
    last_row = database.get_last_fx_rate()
    carry: float | None = last_row["usd_to_sgd"] if last_row else None
    start = (
        date.fromisoformat(last_row["date"]) + timedelta(days=1)
        if last_row else date(2015, 1, 1)
    )

    if start > yesterday:
        _logger.debug("fx_rates start=%s end=%s no_work=true", start.isoformat(), yesterday.isoformat())
        return

    df = yf.download("USDSGD=X", start=start.isoformat(), end=date.today().isoformat(),
                     group_by="ticker", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(0)

    closes: dict[str, float] = {} if df.empty else {
        str(ts)[:10]: float(row["Close"]) for ts, row in df.iterrows()
    }

    current = start
    while current <= yesterday:
        day_str = current.isoformat()
        if day_str in closes:
            carry = closes[day_str]
        if carry is not None:
            counts.rows_fetched += 1
            database.upsert_fx_rate({"date": day_str, "usd_to_sgd": carry})
            counts.rows_written += 1
        current += timedelta(days=1)

    _logger.debug(
        "fx_rates start=%s end=%s days_written=%d", start.isoformat(), yesterday.isoformat(), counts.rows_written
    )
