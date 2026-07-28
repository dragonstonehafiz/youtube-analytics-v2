from __future__ import annotations

import uuid

import database

from . import status
from .stages import (
    SyncCounts,
    sync_fx_rates,
    sync_playlists,
    sync_video_analytics,
    sync_video_traffic_sources,
    sync_videos,
)

# The five stages that make up one full pipeline run, sharing a batch_id. Used to
# identify the latest successful full-pipeline batch for scheduler checkpointing.
FULL_SYNC_TYPES = (
    "videos",
    "playlists",
    "video_analytics",
    "video_traffic_sources",
    "fx_rates",
)


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


def run_sync(scope: str = "incremental", year: int | None = None) -> None:
    """Run a full sync: videos → playlists → video analytics → traffic sources → fx rates.

    `scope` controls the date range used for video analytics and traffic sources only
    (videos, playlists, and fx rates are always synced incrementally):
      - "incremental" (default): resume from INCREMENTAL_LOOKBACK_DAYS before each video's
        last synced date, clamped to its publish date.
      - "year": refetch the given `year` (Jan 1 - Dec 31, clamped to publish date / yesterday)
        for every video, ignoring any existing resume checkpoint.
      - "all": refetch each video's entire history (publish date - yesterday), ignoring
        any existing resume checkpoint.

    Each of the five stages is recorded as its own sync_runs row, all sharing one
    batch_id, tracking status/timing/row counts/errors.

    Safe to call from a background thread. Sets is_syncing for the duration.
    """
    if scope == "year" and year is None:
        raise ValueError("year is required when scope='year'")

    if not status.try_start():
        return

    batch_id = str(uuid.uuid4())

    try:
        status.set_message("Syncing videos...")
        _run_stage(batch_id, "videos", "incremental", None, sync_videos)

        status.set_message("Syncing playlists...")
        _run_stage(batch_id, "playlists", "incremental", None, sync_playlists)

        _run_stage(
            batch_id, "video_analytics", scope, year,
            lambda counts: sync_video_analytics(scope, year, counts),
        )

        _run_stage(
            batch_id, "video_traffic_sources", scope, year,
            lambda counts: sync_video_traffic_sources(scope, year, counts),
        )

        status.set_message("Syncing FX rates...")
        _run_stage(batch_id, "fx_rates", "incremental", None, sync_fx_rates)

        status.set_message("Sync complete.")

    finally:
        status.finish()
