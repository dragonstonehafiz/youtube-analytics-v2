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


def sync_videos(counts: SyncCounts, playlist_video_ids: set[str]) -> set[str]:
    """Fetch and upsert details for every channel-owned video; never deletes.

    Fetches details for the union of the uploads-playlist IDs and `playlist_video_ids`
    (candidates discovered by `sync_playlists()`, empty when that stage didn't run).
    Uploads-playlist membership is treated as proof of ownership on its own; a
    playlist-only candidate is upserted only when its returned `snippet.channelId`
    matches the authenticated channel, so a video from someone else's playlist is never
    imported as if it were this channel's.

    Returns every ID confirmed to belong to the channel — every uploads ID (even one
    `videos.list` didn't return details for) plus every ownership-confirmed
    playlist-only ID — for the pruning stage to retain.

    Classification is skipped when the Shorts playlist enumeration is truncated: an
    incomplete `shorts_ids` set can't tell a real Short that was missed from a genuine
    long-form video, so guessing "video" would silently reclassify already-known
    Shorts. `upsert_video` leaves `content_type` untouched on conflict when it's None.

    `fetch_videos()` silently omits any id the videos().list detail call doesn't return
    an item for (e.g. region-restricted or transiently unavailable). That gap is logged
    here rather than left to show up only as an unexplained DB shortfall.
    """
    channel_id, uploads_id = youtube.fetch_channel_identity()
    shorts_ids, shorts_truncated = youtube.fetch_shorts_video_ids(uploads_id)
    uploads_ids, _ = youtube.fetch_all_video_ids(uploads_id)

    if shorts_truncated:
        _logger.warning("videos classification skipped reason=shorts_pagination_truncated")

    uploads_id_set = set(uploads_ids)
    playlist_only_ids = playlist_video_ids - uploads_id_set
    candidate_ids = uploads_ids + sorted(playlist_only_ids)

    fetched_videos: list[dict] = []
    for i in range(0, len(candidate_ids), 50):
        batch = candidate_ids[i : i + 50]
        for video in youtube.fetch_videos(batch):
            if not shorts_truncated:
                video["content_type"] = "short" if video["id"] in shorts_ids else "video"
            fetched_videos.append(video)
            counts.rows_fetched += 1

    fetched_by_id = {v["id"]: v for v in fetched_videos}

    missing_ids = set(candidate_ids) - fetched_by_id.keys()
    if missing_ids:
        _logger.warning(
            "videos missing from detail fetch count=%d ids=%s", len(missing_ids), sorted(missing_ids)
        )

    owned_playlist_only_ids = {
        video_id for video_id in playlist_only_ids
        if video_id in fetched_by_id and fetched_by_id[video_id].get("channel_id") == channel_id
    }

    for video_id, video in fetched_by_id.items():
        if video_id in uploads_id_set or video_id in owned_playlist_only_ids:
            database.upsert_video(video)
            counts.rows_written += 1

    return uploads_id_set | owned_playlist_only_ids


def sync_playlists(counts: SyncCounts) -> set[str]:
    """Fetch all playlists and their items, upsert, then delete any DB playlists not returned by the API.

    Both deletes are gated on complete pagination. A playlist whose items were truncated
    keeps its stored items untouched — the replace is delete-then-reinsert, so running it
    against a partial page set would silently shrink that playlist. A truncated playlist
    listing likewise suppresses the listing-level reconcile.

    Returns every non-null playlist-item video ID seen, for `sync_videos()` to combine
    with the uploads-playlist IDs.
    """
    playlists, playlists_truncated = youtube.fetch_playlists()
    all_items: dict[str, list[dict]] = {}
    truncated_playlists: set[str] = set()
    for playlist in playlists:
        items, items_truncated = youtube.fetch_playlist_items(
            playlist["id"], playlist_title=playlist.get("title")
        )
        all_items[playlist["id"]] = items
        if items_truncated:
            truncated_playlists.add(playlist["id"])
        counts.rows_fetched += 1 + len(items)

    playlist_video_ids = {
        item["video_id"]
        for items in all_items.values()
        for item in items
        if item.get("video_id")
    }

    for playlist in playlists:
        database.upsert_playlist(playlist)
        counts.rows_written += 1
        if playlist["id"] in truncated_playlists:
            _logger.warning(
                "playlist_items replace skipped reason=pagination_truncated playlist=%s fetched=%d title=%r",
                playlist["id"], len(all_items[playlist["id"]]), playlist.get("title"),
            )
            continue
        counts.rows_deleted += database.delete_playlist_items(playlist["id"])
        for item in all_items[playlist["id"]]:
            database.upsert_playlist_item(item)
            counts.rows_written += 1

    if playlists_truncated:
        _logger.warning(
            "playlists cleanup skipped reason=pagination_truncated fetched=%d", len(playlists)
        )
        return playlist_video_ids

    counts.rows_deleted += database.delete_playlists_not_in([p["id"] for p in playlists])
    return playlist_video_ids


def sync_pruning(counts: SyncCounts, channel_owned_ids: set[str]) -> None:
    """Delete every DB video not in `channel_owned_ids`, the channel-owned set built by
    `sync_playlists()` and `sync_videos()` in this same plan."""
    counts.rows_deleted += database.delete_videos_not_in(sorted(channel_owned_ids))


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
