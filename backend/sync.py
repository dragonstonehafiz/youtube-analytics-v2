from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import database
import youtube

# ---------------------------------------------------------------------------
# Shared state (read by routes.py via get_status())
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_is_syncing: bool = False
_last_synced_at: str | None = None
_message: str = ""


def get_status() -> dict:
    """Return current sync status. Safe to call from any thread."""
    with _lock:
        return {"is_syncing": _is_syncing, "last_synced_at": _last_synced_at, "message": _message}


def is_syncing() -> bool:
    """Return True if a sync is currently running."""
    with _lock:
        return _is_syncing


def _set_message(msg: str) -> None:
    """Update the current sync message."""
    global _message
    with _lock:
        _message = msg


# ---------------------------------------------------------------------------
# Sync run tracking
# ---------------------------------------------------------------------------

@dataclass
class SyncCounts:
    """Mutable running totals for a single sync stage, accumulated as work happens."""
    rows_fetched: int = 0
    rows_written: int = 0
    rows_deleted: int = 0


def _run_stage(
    batch_id: str,
    sync_type: str,
    scope: str | None,
    year: int | None,
    fn,
) -> None:
    """Run one sync stage, recording a sync_runs row that reflects partial progress on failure."""
    counts = SyncCounts()
    sync_run_id = database.create_sync_run(batch_id, sync_type, scope, year)
    try:
        fn(counts)
    except Exception as exc:
        database.fail_sync_run(
            sync_run_id, str(exc), counts.rows_fetched, counts.rows_written, counts.rows_deleted
        )
        raise
    else:
        database.complete_sync_run(
            sync_run_id, counts.rows_fetched, counts.rows_written, counts.rows_deleted
        )


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def run_sync(scope: str = "incremental", year: int | None = None) -> None:
    """Run a full sync: videos → playlists → video analytics → traffic sources → fx rates.

    `scope` controls the date range used for video analytics and traffic sources only
    (videos, playlists, and fx rates are always synced incrementally):
      - "incremental" (default): resume from each video's last synced date, as before.
      - "year": refetch the given `year` (Jan 1 - Dec 31, clamped to publish date / yesterday)
        for every video, ignoring any existing resume checkpoint.
      - "all": refetch each video's entire history (publish date - yesterday), ignoring
        any existing resume checkpoint.

    Each of the five stages is recorded as its own sync_runs row, all sharing one
    batch_id, tracking status/timing/row counts/errors.

    Safe to call from a background thread. Sets is_syncing for the duration.
    """
    global _is_syncing, _last_synced_at

    if scope == "year" and year is None:
        raise ValueError("year is required when scope='year'")

    with _lock:
        if _is_syncing:
            return
        _is_syncing = True

    batch_id = str(uuid.uuid4())

    try:
        _set_message("Syncing videos...")
        _run_stage(batch_id, "videos", "incremental", None, _sync_videos)

        _set_message("Syncing playlists...")
        _run_stage(batch_id, "playlists", "incremental", None, _sync_playlists)

        _run_stage(
            batch_id, "video_analytics", scope, year,
            lambda counts: _sync_video_analytics(scope, year, counts),
        )

        _run_stage(
            batch_id, "video_traffic_sources", scope, year,
            lambda counts: _sync_video_traffic_sources(scope, year, counts),
        )

        _set_message("Syncing FX rates...")
        _run_stage(batch_id, "fx_rates", "incremental", None, _sync_fx_rates)

        now = date.today().isoformat()
        with _lock:
            _last_synced_at = now
            _message = "Sync complete."
        database.set_sync_state("last_synced_at", now)

    finally:
        with _lock:
            _is_syncing = False


def _sync_videos(counts: SyncCounts) -> None:
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


def _sync_playlists(counts: SyncCounts) -> None:
    """Fetch all playlists and their items, upsert, then delete any DB playlists not returned by the API."""
    playlists = youtube.fetch_playlists()
    all_items: dict[str, list[dict]] = {}
    for playlist in playlists:
        items = youtube.fetch_playlist_items(playlist["id"])
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


def _sync_video_analytics(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Fetch daily analytics for every video.

    scope="incremental" resumes from each video's last synced date; scope="year"
    refetches the given year; scope="all" refetches each video's entire history.
    """
    today = date.today()
    end_date = (today - timedelta(days=1)).isoformat()

    video_ids = database.get_all_video_ids()
    total = len(video_ids)
    for i, video_id in enumerate(video_ids, start=1):
        _set_message(f"Syncing video analytics ({i}/{total})...")
        video = database.get_video(video_id)
        if not video or not video.get("published_at"):
            continue
        publish_date = video["published_at"][:10]

        if scope == "year":
            start = max(publish_date, f"{year}-01-01")
            range_end = min(end_date, f"{year}-12-31")
        elif scope == "all":
            start = publish_date
            range_end = end_date
        else:
            last_date = database.get_last_analytics_date(video_id)
            start = (date.fromisoformat(last_date) + timedelta(days=1)).isoformat() if last_date else publish_date
            range_end = end_date

        if start > range_end:
            continue

        for row in youtube.iter_video_analytics(video_id, start, range_end, publish_date=publish_date):
            counts.rows_fetched += 1
            database.upsert_video_analytics(row)
            counts.rows_written += 1


def _sync_video_traffic_sources(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Fetch daily traffic-source breakdowns for every video.

    scope="incremental" re-fetches starting a week before the last synced date (not
    right after it), since traffic-source data for a given day is not fully available
    from the API until some time after that day ends — upserting re-pulled days is a
    no-op once the data has settled, and corrects any recent day that was stored
    before its data had fully arrived. scope="year" refetches the given year;
    scope="all" refetches each video's entire history.
    """
    today = date.today()
    end_date = (today - timedelta(days=1)).isoformat()

    video_ids = database.get_all_video_ids()
    total = len(video_ids)
    for i, video_id in enumerate(video_ids, start=1):
        _set_message(f"Syncing traffic sources ({i}/{total})...")
        video = database.get_video(video_id)
        if not video or not video.get("published_at"):
            continue
        publish_date = video["published_at"][:10]

        if scope == "year":
            start = max(publish_date, f"{year}-01-01")
            range_end = min(end_date, f"{year}-12-31")
        elif scope == "all":
            start = publish_date
            range_end = end_date
        else:
            last_date = database.get_last_traffic_source_date(video_id)
            if last_date:
                start = (date.fromisoformat(last_date) - timedelta(days=7)).isoformat()
                if start < publish_date:
                    start = publish_date
            else:
                start = publish_date
            range_end = end_date

        if start > range_end:
            continue

        for row in youtube.iter_video_traffic_sources(video_id, start, range_end, publish_date=publish_date):
            counts.rows_fetched += 1
            database.upsert_video_traffic_source(row)
            counts.rows_written += 1


def _sync_fx_rates(counts: SyncCounts) -> None:
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


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------

def _scheduler_loop() -> None:
    """Run sync immediately, then repeat every 24 hours."""
    run_sync()
    timer = threading.Timer(86400, _scheduler_loop)
    timer.daemon = True
    timer.start()


def start_background_scheduler() -> None:
    """Start the background sync scheduler. Call once on app startup.

    If last sync was within 24 hours, skip the immediate sync and schedule
    the next one for the remaining time in the 24h window.
    """
    global _last_synced_at
    stored = database.get_sync_state("last_synced_at")
    if stored:
        with _lock:
            _last_synced_at = stored

    delay = 0.0
    if stored:
        try:
            last = datetime.fromisoformat(stored)
            elapsed = (datetime.now() - last).total_seconds()
            if elapsed < 86400:
                delay = 86400 - elapsed
        except ValueError:
            pass

    def _start(d: float) -> None:
        if d > 0:
            timer = threading.Timer(d, _scheduler_loop)
            timer.daemon = True
            timer.start()
        else:
            thread = threading.Thread(target=_scheduler_loop, daemon=True)
            thread.start()

    _start(delay)
