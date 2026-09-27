from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import database
import youtube
from database import (
    Comment,
    CommentAuthor,
    FxRate,
    Playlist,
    PlaylistItem,
    SyncCoverage,
    Video,
    VideoAnalytics,
    VideoTrafficSource,
    now,
    queries,
    reader,
    writer,
)
from logging_config import exception_context, get_logger

from . import coverage, monthly_insights, status, write_preparation

# How many further comments an incremental scan keeps reading after it recognises the
# first one it already stores. One maximum-size page, so the overlap costs no extra
# request while still catching edits and late arrivals just behind the boundary.
COMMENT_INCREMENTAL_OVERLAP = youtube.COMMENT_THREADS_PAGE_SIZE

_logger = get_logger("sync")


@dataclass
class SyncCounts:
    """Mutable running totals for a single sync stage, accumulated as work happens."""
    rows_fetched: int = 0
    rows_written: int = 0
    rows_deleted: int = 0


def _coverage_rows(collector: str, video_id: str, months: list[str]) -> list[SyncCoverage]:
    """Return completed-month coverage rows for one video and collector, stamped now."""
    completed_at = now()
    return [
        SyncCoverage(collector=collector, video_id=video_id, period_key=month, completed_at=completed_at)
        for month in months
    ]


def _incremental_monthly_windows(
    collector: str, video_id: str, publish_date: date, yesterday: date, forced: list[monthly_insights.MonthlyWindow],
) -> list[monthly_insights.MonthlyWindow]:
    """Return uncovered months plus eligible forced refresh windows for one video."""
    windows_all = monthly_insights.monthly_windows_for_range(publish_date, yesterday)
    if not windows_all:
        return []
    rows = reader.select(SyncCoverage, ("period_key",), where=[
        ("collector", "=", collector),
        ("video_id", "=", video_id),
        ("period_key", ">=", windows_all[0].month),
        ("period_key", "<=", windows_all[-1].month),
    ])
    covered = {row.period_key for row in rows if row.period_key is not None}
    missing_months = {window.month for window in coverage.missing_windows(windows_all, covered)}
    forced_months = {window.month for window in forced}
    # Rebuild from windows_all (rather than concatenating missing + forced) so the
    # result stays chronologically ordered even when a forced month (e.g. previous
    # month, if already covered) sorts earlier than a genuinely missing later month —
    # order matters for coalesce_missing_windows() to merge adjacent months correctly.
    include_months = missing_months | forced_months
    return [window for window in windows_all if window.month in include_months]


def _video_period_requests(
    collector: str, video_id: str, scope: str, year: int | None, today: date, end_date: str, publish_date: str,
) -> list[tuple[str, str, list[str]]]:
    """Return request ranges and coverage months for one video and collector."""
    if scope in ("year", "all"):
        if scope == "year":
            assert year is not None, "scope=year requires a year"
            start = max(publish_date, f"{year}-01-01")
            range_end = min(end_date, f"{year}-12-31")
        else:
            start = publish_date
            range_end = end_date
        if start > range_end:
            return []
        months = [
            window.month
            for window in monthly_insights.monthly_windows_for_range(date.fromisoformat(start), date.fromisoformat(range_end))
        ]
        return [(start, range_end, months)]

    windows = _incremental_monthly_windows(
        collector, video_id, date.fromisoformat(publish_date), today - timedelta(days=1),
        monthly_insights.monthly_search_windows(today),
    )
    return [(r.start_date, r.end_date, r.months) for r in coverage.coalesce_missing_windows(windows)]


def _effective_range_end(scope: str, year: int | None, yesterday: date) -> date:
    """Return the inclusive request end date for a scoped analytics stage."""
    if scope == "year":
        assert year is not None, "scope=year requires a year"
        return min(yesterday, date(year, 12, 31))
    return yesterday


def sync_videos(counts: SyncCounts, playlist_video_ids: set[str]) -> set[str]:
    """Sync channel-owned video details and return confirmed owned IDs."""
    channel_id, uploads_id = youtube.fetch_channel_identity()
    shorts_ids, shorts_truncated = youtube.fetch_shorts_video_ids(
        uploads_id, checkpoint=status.raise_if_stopping
    )
    uploads_ids, _ = youtube.fetch_all_video_ids(uploads_id, checkpoint=status.raise_if_stopping)

    if shorts_truncated:
        _logger.warning("videos classification skipped reason=shorts_pagination_truncated")

    uploads_id_set = set(uploads_ids)
    playlist_only_ids = playlist_video_ids - uploads_id_set
    candidate_ids = uploads_ids + sorted(playlist_only_ids)

    fetched_videos: list[dict] = []
    for i in range(0, len(candidate_ids), 50):
        if i > 0:
            status.raise_if_stopping()
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

    for i, (video_id, video) in enumerate(fetched_by_id.items()):
        if i > 0:
            status.raise_if_stopping()
        if video_id in uploads_id_set or video_id in owned_playlist_only_ids:
            writer.write(Video.from_dict({**video, "own": True, "updated_at": now()}))
            counts.rows_written += 1

    return uploads_id_set | owned_playlist_only_ids


def sync_playlists(counts: SyncCounts) -> set[str]:
    """Sync playlists and complete item sets, then reconcile deleted playlists."""
    playlists, playlists_truncated = youtube.fetch_playlists(checkpoint=status.raise_if_stopping)
    all_items: dict[str, list[dict]] = {}
    truncated_playlists: set[str] = set()
    for i, playlist in enumerate(playlists):
        if i > 0:
            status.raise_if_stopping()
        items, items_truncated = youtube.fetch_playlist_items(
            playlist["id"], playlist_title=playlist.get("title"), checkpoint=status.raise_if_stopping
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

    for i, playlist in enumerate(playlists):
        if i > 0:
            status.raise_if_stopping()
        writer.write(Playlist.from_dict({**playlist, "updated_at": now()}))
        counts.rows_written += 1
        if playlist["id"] in truncated_playlists:
            _logger.warning(
                "playlist_items replace skipped reason=pagination_truncated playlist=%s fetched=%d title=%r",
                playlist["id"], len(all_items[playlist["id"]]), playlist.get("title"),
            )
            continue
        counts.rows_deleted += database.delete_playlist_items(playlist["id"])
        for item in all_items[playlist["id"]]:
            writer.write(PlaylistItem.from_dict({**item, "updated_at": now()}))
            counts.rows_written += 1

    if playlists_truncated:
        _logger.warning(
            "playlists cleanup skipped reason=pagination_truncated fetched=%d", len(playlists)
        )
        return playlist_video_ids

    status.raise_if_stopping()
    counts.rows_deleted += database.delete_playlists_not_in([p["id"] for p in playlists])
    return playlist_video_ids


def _comment_bootstrap_cutoff(today: date) -> str:
    """Return the rolling lower date bound for a video without stored comments."""
    return date(today.year - 1, 12, 1).isoformat()


def sync_comments(scope: str, counts: SyncCounts) -> None:
    """Sync top-level comments for every stored owned video."""
    cutoff = _comment_bootstrap_cutoff(date.today())
    videos = reader.fetch(Video, queries.owned_video_worklist())
    total = len(videos)

    for i, video in enumerate(videos, start=1):
        if i > 1:
            status.raise_if_stopping()
        status.update_sync_progress("comments", f"Syncing comments ({i}/{total})...")
        assert video.id is not None
        video_id = video.id
        title = video.title
        known_ids = {
            comment.id for comment in reader.select(Comment, ("id",), where=[("video_id", "=", video_id)])
        }
        fetched_before = counts.rows_fetched
        written_before = counts.rows_written
        overlap_remaining: int | None = None
        first_pair = True

        for item in youtube.iter_comment_threads(video_id, title=title, checkpoint=status.raise_if_stopping):
            if not first_pair:
                status.raise_if_stopping()
            first_pair = False
            counts.rows_fetched += 1
            comment = item["comment"]

            if scope != "all":
                if overlap_remaining is not None:
                    if overlap_remaining <= 0:
                        break
                    overlap_remaining -= 1
                elif comment["id"] in known_ids:
                    overlap_remaining = COMMENT_INCREMENTAL_OVERLAP
                elif not known_ids and comment["published_at"] < cutoff:
                    # Only a video with nothing stored falls back to the date cutoff. One
                    # that has comments but whose boundary never appears — every stored
                    # comment since deleted — reads to the end instead of stopping short
                    # of history it may still be missing.
                    break

            try:
                writer.write(CommentAuthor.from_dict({**item["author"], "updated_at": now()}))
                counts.rows_written += 1
                writer.write(Comment.from_dict({**comment, "updated_at": now()}))
                counts.rows_written += 1
            except Exception as exc:
                _logger.warning(
                    "comments item skipped video=%s comment=%s %s",
                    video_id, comment["id"], exception_context(exc),
                )

        _logger.debug(
            "comments %d/%d video=%s scope=%s fetched=%d written=%d title=%r",
            i, total, video_id, scope, counts.rows_fetched - fetched_before,
            counts.rows_written - written_before, title,
        )

    counts.rows_deleted += database.delete_orphan_comment_authors()


def sync_pruning(counts: SyncCounts, channel_owned_ids: set[str]) -> None:
    """Delete database videos absent from the confirmed channel-owned IDs."""
    status.raise_if_stopping()
    counts.rows_deleted += database.delete_videos_not_in(sorted(channel_owned_ids))


def sync_video_analytics(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Sync daily analytics for every eligible owned video."""
    today = date.today()
    effective_end = _effective_range_end(scope, year, today - timedelta(days=1))
    end_date = effective_end.isoformat()

    videos = reader.fetch(Video, queries.owned_video_worklist(published_through=end_date))
    total = len(videos)
    for i, video in enumerate(videos, start=1):
        if i > 1:
            status.raise_if_stopping()
        status.update_sync_progress("video_analytics", f"Syncing video analytics ({i}/{total})...")
        assert video.id is not None
        video_id = video.id
        title = video.title
        if not video.published_at:
            _logger.debug(
                "video_analytics %d/%d video=%s skipped reason=no_publish_date title=%r",
                i, total, video_id, title,
            )
            continue
        publish_date = video.published_at[:10]

        requests = _video_period_requests("video_analytics", video_id, scope, year, today, end_date, publish_date)
        if not requests:
            _logger.debug(
                "video_analytics %d/%d video=%s skipped reason=empty_range title=%r",
                i, total, video_id, title,
            )
            continue

        rows_before = counts.rows_fetched
        for j, (start, range_end, months) in enumerate(requests):
            if j > 0:
                status.raise_if_stopping()
            first_row = True
            for row in youtube.iter_video_analytics(
                video_id, start, range_end, publish_date=publish_date, title=title,
                checkpoint=status.raise_if_stopping,
            ):
                if not first_row:
                    status.raise_if_stopping()
                first_row = False
                counts.rows_fetched += 1
                writer.write(VideoAnalytics.from_dict({**row, "updated_at": now()}))
                counts.rows_written += 1
            status.raise_if_stopping()
            writer.write_many(_coverage_rows("video_analytics", video_id, months))
        _logger.debug(
            "video_analytics %d/%d video=%s rows=%d title=%r",
            i, total, video_id, counts.rows_fetched - rows_before, title,
        )


def sync_video_traffic_sources(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Sync daily traffic-source breakdowns for every eligible owned video."""
    today = date.today()
    effective_end = _effective_range_end(scope, year, today - timedelta(days=1))
    end_date = effective_end.isoformat()

    videos = reader.fetch(Video, queries.owned_video_worklist(published_through=end_date))
    total = len(videos)
    for i, video in enumerate(videos, start=1):
        if i > 1:
            status.raise_if_stopping()
        status.update_sync_progress("video_traffic_sources", f"Syncing traffic sources ({i}/{total})...")
        assert video.id is not None
        video_id = video.id
        title = video.title
        if not video.published_at:
            _logger.debug(
                "video_traffic_sources %d/%d video=%s skipped reason=no_publish_date title=%r",
                i, total, video_id, title,
            )
            continue
        publish_date = video.published_at[:10]

        requests = _video_period_requests("video_traffic_sources", video_id, scope, year, today, end_date, publish_date)
        if not requests:
            _logger.debug(
                "video_traffic_sources %d/%d video=%s skipped reason=empty_range title=%r",
                i, total, video_id, title,
            )
            continue

        rows_before = counts.rows_fetched
        for j, (start, range_end, months) in enumerate(requests):
            if j > 0:
                status.raise_if_stopping()
            first_row = True
            for row in youtube.iter_video_traffic_sources(
                video_id, start, range_end, publish_date=publish_date, title=title,
                checkpoint=status.raise_if_stopping,
            ):
                if not first_row:
                    status.raise_if_stopping()
                first_row = False
                counts.rows_fetched += 1
                writer.write(VideoTrafficSource.from_dict({**row, "updated_at": now()}))
                counts.rows_written += 1
            status.raise_if_stopping()
            writer.write_many(_coverage_rows("video_traffic_sources", video_id, months))
        _logger.debug(
            "video_traffic_sources %d/%d video=%s rows=%d title=%r",
            i, total, video_id, counts.rows_fetched - rows_before, title,
        )


def sync_search_insights(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Sync monthly Search-source terms for every eligible owned video."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    effective_end = _effective_range_end(scope, year, yesterday)
    # Captured once so a midnight rollover mid-run cannot change the worklist. Used only
    # as the incremental fallback for a video with no publish date to compute a range from.
    incremental_windows = monthly_insights.monthly_search_windows(today)
    videos = reader.fetch(Video, queries.owned_video_worklist(published_through=effective_end.isoformat()))
    total = len(videos)

    for i, video in enumerate(videos, start=1):
        if i > 1:
            status.raise_if_stopping()
        assert video.id is not None
        video_id = video.id
        title = video.title
        status.update_sync_progress("search_insights", f"Syncing search insights ({i}/{total})...")

        if scope in ("year", "all"):
            if not video.published_at:
                _logger.debug(
                    "search_insights %d/%d video=%s skipped reason=no_publish_date title=%r",
                    i, total, video_id, title,
                )
                continue
            publish_date = date.fromisoformat(video.published_at[:10])
            if scope == "year":
                assert year is not None, "scope=year requires a year"
                start = max(publish_date, date(year, 1, 1))
                end = min(yesterday, date(year, 12, 31))
            else:
                start = publish_date
                end = yesterday
            windows = monthly_insights.monthly_windows_for_range(start, end)
        elif video.published_at:
            publish_date = date.fromisoformat(video.published_at[:10])
            windows = _incremental_monthly_windows("search_insights", video_id, publish_date, yesterday, incremental_windows)
        else:
            windows = incremental_windows

        rows_before = counts.rows_fetched
        for j, window in enumerate(windows):
            if j > 0:
                status.raise_if_stopping()
            result = youtube.fetch_video_search_terms(
                video_id, window.start_date, window.end_date, checkpoint=status.raise_if_stopping
            )
            counts.rows_fetched += result.raw_row_count
            terms = write_preparation.search_term_rows(video_id, window.month, result.terms, updated_at=now())
            counts.rows_written += writer.write_many(terms)
            writer.write_many(_coverage_rows("search_insights", video_id, [window.month]))
        _logger.debug(
            "search_insights %d/%d video=%s months=%d rows=%d title=%r",
            i, total, video_id, len(windows), counts.rows_fetched - rows_before, title,
        )


def sync_related_video_insights(scope: str, year: int | None, counts: SyncCounts) -> None:
    """Sync monthly Related Video referrers and resolve new referrer metadata."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    effective_end = _effective_range_end(scope, year, yesterday)
    # Captured once so a midnight rollover mid-run cannot change the worklist. Used only
    # as the incremental fallback for a video with no publish date to compute a range from.
    incremental_windows = monthly_insights.monthly_search_windows(today)
    videos = reader.fetch(Video, queries.owned_video_worklist(published_through=effective_end.isoformat()))
    total = len(videos)
    newly_encountered_ids: set[str] = set()

    for i, video in enumerate(videos, start=1):
        if i > 1:
            status.raise_if_stopping()
        assert video.id is not None
        video_id = video.id
        title = video.title
        status.update_sync_progress("related_video_insights", f"Syncing related video insights ({i}/{total})...")

        if scope in ("year", "all"):
            if not video.published_at:
                _logger.debug(
                    "related_video_insights %d/%d video=%s skipped reason=no_publish_date title=%r",
                    i, total, video_id, title,
                )
                continue
            publish_date = date.fromisoformat(video.published_at[:10])
            if scope == "year":
                assert year is not None, "scope=year requires a year"
                start = max(publish_date, date(year, 1, 1))
                end = min(yesterday, date(year, 12, 31))
            else:
                start = publish_date
                end = yesterday
            windows = monthly_insights.monthly_windows_for_range(start, end)
        elif video.published_at:
            publish_date = date.fromisoformat(video.published_at[:10])
            windows = _incremental_monthly_windows(
                "related_video_insights", video_id, publish_date, yesterday, incremental_windows
            )
        else:
            windows = incremental_windows

        rows_before = counts.rows_fetched
        for j, window in enumerate(windows):
            if j > 0:
                status.raise_if_stopping()
            result = youtube.fetch_video_related_videos(
                video_id, window.start_date, window.end_date, checkpoint=status.raise_if_stopping
            )
            counts.rows_fetched += result.raw_row_count
            referrers = write_preparation.related_video_rows(
                video_id, window.month, result.referrers, updated_at=now()
            )
            if referrers and reader.select_one(Video, ("id",), where=[("id", "=", video_id), ("own", "=", True)]) is None:
                raise ValueError(f"target_video_id {video_id!r} is not an owned video")
            counts.rows_written += writer.write_many(referrers)
            writer.write_many(_coverage_rows("related_video_insights", video_id, [window.month]))
            newly_encountered_ids.update(r["referrer_video_id"] for r in result.referrers)
        _logger.debug(
            "related_video_insights %d/%d video=%s months=%d rows=%d title=%r",
            i, total, video_id, len(windows), counts.rows_fetched - rows_before, title,
        )

    _resolve_related_video_metadata(newly_encountered_ids, counts)


def _resolve_related_video_metadata(newly_encountered_ids: set[str], counts: SyncCounts) -> None:
    """Resolve and classify metadata for previously unknown referrer videos."""
    known_ids = {video.id for video in reader.select(Video, ("id",))}
    unknown_ids = sorted(newly_encountered_ids - known_ids)
    if not unknown_ids:
        return

    try:
        channel_id, _ = youtube.fetch_channel_identity()
    except Exception as exc:
        _logger.warning(
            "related_video_insights metadata resolution skipped: channel identity lookup failed %s",
            exception_context(exc),
        )
        return

    resolved = 0
    for i in range(0, len(unknown_ids), 50):
        if i > 0:
            status.raise_if_stopping()
        batch = unknown_ids[i : i + 50]
        try:
            fetched = youtube.fetch_videos(batch)
        except Exception as exc:
            _logger.warning(
                "related_video_insights metadata batch failed count=%d %s",
                len(batch), exception_context(exc),
            )
            continue
        for j, video in enumerate(fetched):
            if j > 0:
                status.raise_if_stopping()
            counts.rows_fetched += 1
            writer.write(Video.from_dict({**video, "own": video.get("channel_id") == channel_id, "updated_at": now()}))
            counts.rows_written += 1
            resolved += 1
    _logger.debug(
        "related_video_insights metadata unknown=%d resolved=%d", len(unknown_ids), resolved,
    )


def sync_fx_rates(counts: SyncCounts) -> None:
    """Fetch daily USD/SGD rates from Yahoo Finance, filling weekends/holidays with last known rate."""
    import yfinance as yf
    import pandas as pd

    yesterday = date.today() - timedelta(days=1)
    last_rate = reader.select_one(FxRate, ("date", "usd_to_sgd"), order_by=("-date",))
    carry: float | None = last_rate.usd_to_sgd if last_rate else None
    start = (
        date.fromisoformat(last_rate.date) + timedelta(days=1)
        if last_rate and last_rate.date else date(2015, 1, 1)
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
        if current > start:
            status.raise_if_stopping()
        day_str = current.isoformat()
        if day_str in closes:
            carry = closes[day_str]
        if carry is not None:
            counts.rows_fetched += 1
            writer.write(FxRate(date=day_str, usd_to_sgd=carry, updated_at=now()))
            counts.rows_written += 1
        current += timedelta(days=1)

    _logger.debug(
        "fx_rates start=%s end=%s days_written=%d", start.isoformat(), yesterday.isoformat(), counts.rows_written
    )
