# Synchronization Reference

## Purpose

How data gets from the YouTube APIs into SQLite: pipeline order, scheduling, scope semantics, and the caveats that affect data freshness/correctness. Database-side query/aggregation semantics live in `database.md`; this file covers ingestion only.

## Authoritative source files

- `backend/sync.py`
- `backend/youtube.py`
- `backend/database.py` (sync-state and sync-run helpers only: `get_sync_state`, `set_sync_state`, `create_sync_run`, `complete_sync_run`, `fail_sync_run`, `get_sync_runs`, `get_last_analytics_date`, `get_last_traffic_source_date`, `get_last_fx_rate`, `get_all_video_ids`)

## Contents

- [Pipeline overview](#pipeline-overview)
- [Scheduling and state](#scheduling-and-state)
- [Scope behavior](#scope-behavior)
- [Stage tracking](#stage-tracking)
- [Video and playlist synchronization](#video-and-playlist-synchronization)
- [Shared incremental lookback](#shared-incremental-lookback)
- [Analytics synchronization](#analytics-synchronization)
- [Traffic-source synchronization](#traffic-source-synchronization)
- [FX-rate synchronization](#fx-rate-synchronization)
- [YouTube API requests and pagination](#youtube-api-requests-and-pagination)
- [Authentication](#authentication)

## Pipeline overview

A single sync (`run_sync()`, `sync.py:93-150`) runs five stages in order, always in this sequence:

```
videos → playlists → video_analytics → video_traffic_sources → fx_rates
```

Each stage is wrapped by `_run_stage()` and recorded as its own `sync_runs` row; all five rows from one `run_sync()` call share one `batch_id` (a UUID generated once per call, `sync.py:120`).

## Scheduling and state

- `_scheduler_loop()` (`sync.py:319-324`) calls `run_sync()` immediately, then reschedules itself via `threading.Timer(86400, ...)` (24h), as a daemon thread.
- `start_background_scheduler()` (`sync.py:327-358`), called once from `server.py`'s lifespan, reads the persisted `last_synced_at` from `sync_state`. If the last sync was under 24h ago, it schedules the next run for the *remaining* time in that window instead of running immediately.
- `last_synced_at` is a single global checkpoint stored in `sync_state` (survives restarts) used only to decide "was the last full sync run more than 24h ago" — it is **not** a per-row or per-date audit trail. It's stored as a **date-only** string (`date.today().isoformat()`, `sync.py:142`), not a full timestamp, and is only written after all five stages succeed.
- `get_status()` / `is_syncing()` (`sync.py:26-35`) expose `{is_syncing, last_synced_at, message}` guarded by a module-level `threading.Lock` and `_is_syncing` bool — safe to poll from any thread. If a sync is already running, `run_sync()` returns immediately without starting a second one (`sync.py:115-118`).

## Scope behavior

`run_sync(scope="incremental"|"year"|"all", year=None)`:

- `scope`/`year` affect **only** `_sync_video_analytics` and `_sync_video_traffic_sources`. Videos, playlists, and FX rates always sync incrementally regardless of the requested scope (`sync.py:124,127,140` hardcode `"incremental", None`).
- Raises `ValueError` if `scope == "year"` and `year is None` (`sync.py:112-113`) — mirrored by `routes.py`'s `POST /sync/trigger`, which returns `400` for the same condition before ever calling `run_sync`.
- `"incremental"` (default): resume each video from `INCREMENTAL_LOOKBACK_DAYS` before its own last-synced date, clamped to its publish date (see [Shared incremental lookback](#shared-incremental-lookback)).
- `"year"`: refetch the given calendar year for every video, ignoring any resume checkpoint, clamped to `[publish_date, yesterday]`.
- `"all"`: refetch each video's entire history (`publish_date` → yesterday), ignoring any resume checkpoint.

## Stage tracking

- `SyncCounts` (`sync.py:49-54`) is a mutable dataclass (`rows_fetched`, `rows_written`, `rows_deleted`) accumulated incrementally *as rows are processed inside each stage's loop* — not computed from a return value at the end. If a stage raises partway through (e.g. video 200 of 378), the `sync_runs` row for that stage still reflects accurate partial totals, not zeros.
- `_run_stage()` (`sync.py:57-77`) always re-raises the underlying exception after recording failure via `fail_sync_run()` — so `run_sync()`'s overall `try/finally` (which just clears `_is_syncing`) is unaffected by a stage failing.
- For `videos`/`playlists`/`fx_rates`, `sync_runs.scope` is always `"incremental"` and `year` is `NULL`. For `video_analytics`/`video_traffic_sources`, `scope`/`year` reflect whatever was passed into `run_sync()`.
- The playlists stage's `rows_deleted` sums `delete_playlist_items()`'s return value across every playlist in the loop (items are deleted and fully re-inserted on every sync, `sync.py:186`) plus `delete_playlists_not_in()`'s return value (`sync.py:191`) — cascaded FK deletes (e.g. `video_analytics` rows removed because their parent video was deleted) are not counted, since those helpers only report `cursor.rowcount` for the row they directly targeted.

## Video and playlist synchronization

- `_sync_videos()` (`sync.py:153-171`): fetches the uploads playlist ID, the Shorts video-ID set (via UUSH), and all video IDs; fetches full video details in batches of 50 (YouTube API's per-request ID limit); collects everything into memory first, upserts all of it, **then** deletes any DB video not present in the freshly-fetched ID set (cascades to `video_analytics`/`video_traffic_sources`).
- `_sync_playlists()` (`sync.py:174-191`): same collect-then-upsert-then-delete order, at the playlist level (cascades to `playlist_items`).

## Shared incremental lookback

`_incremental_lookback_start(last_date, publish_date)` (`sync.py:84-90`) is the single helper both `_sync_video_analytics` and `_sync_video_traffic_sources` call for their `"incremental"` start date, so the two stages can't drift apart:

- If `last_date` is `None` (never synced), returns `publish_date`.
- Otherwise returns `max(publish_date, last_date - INCREMENTAL_LOOKBACK_DAYS)` (`INCREMENTAL_LOOKBACK_DAYS = 7`, `sync.py:14`) — i.e. resumes a week before the last stored date, clamped so it never goes earlier than the video's publish date.

## Analytics synchronization

`_sync_video_analytics(scope, year, counts)` (`sync.py:194-233`):

- Per video, computes `start`/`range_end` based on `scope` (see [Scope behavior](#scope-behavior)); for `"incremental"`, `start = _incremental_lookback_start(get_last_analytics_date(video_id), publish_date)`.
- If `start > range_end`, the video is skipped entirely via `continue` — **zero API calls** for that video. This is what prevents querying analytics for a video before it existed even when an unrelated `year` is requested.
- **7-day lookback on incremental mode** (see [Shared incremental lookback](#shared-incremental-lookback)): analytics metrics (views/watch time/revenue) for recent days are not fully settled in the YouTube API at sync time, so each incremental run re-fetches and re-upserts the last 7 days rather than resuming strictly after the last synced date. Re-upserting an already-settled day leaves its metric values unchanged, but `updated_at` is still refreshed on every upsert (see `database.md`) — it is not a true no-op at the row level.

## Traffic-source synchronization

`_sync_video_traffic_sources(scope, year, counts)` (`sync.py:236-275`):

- Same `scope` semantics as analytics, including the shared [incremental lookback](#shared-incremental-lookback): `start = _incremental_lookback_start(get_last_traffic_source_date(video_id), publish_date)`.
- Traffic-source data for a given day is not fully available from the API until some time after that day ends; the lookback corrects any recent day that was stored before its data had fully arrived. Re-upserting an already-settled day leaves its metric values unchanged, but `updated_at` is still refreshed on every upsert (see `database.md`) — it is not a true no-op at the row level.

## FX-rate synchronization

`_sync_fx_rates()` (`sync.py:278-312`):

- Incremental from `get_last_fx_rate()["date"] + 1 day`; first run starts `2015-01-01`.
- Fetches `USDSGD=X` from Yahoo Finance via `yfinance` (imported **inside** the function, not at module scope).
- Weekends/holidays (days with no `yfinance` close) are forward-filled with the last known `carry` value.

## YouTube API requests and pagination

- Both `iter_video_analytics()` and `iter_video_traffic_sources()` chunk the requested date range into **12-month windows** via `_chunk_date_range(..., months=12)` (`youtube.py:123-136`; the function's own default is `months=4`, but both call sites override it to 12). Chunks are anchored to the video's own start date, not calendar-aligned Jan–Dec.
- `maxResults` is set high enough to avoid pagination in the common case:
  - `iter_video_analytics`: `maxResults=2000` (`youtube.py:375`) — a year is at most 365 rows, single `day` dimension.
  - `iter_video_traffic_sources`: `maxResults=10000` (`youtube.py:426`) — a year's theoretical ceiling is 365 days × 21 possible `insightTrafficSourceType` values = 7665 rows.
- Both generators pass an explicit `sort` param (`day` / `day,insightTrafficSourceType`, `youtube.py:374,425`) so that `_fetch_analytics_rows()`'s `startIndex`-based pagination fallback (used only if a chunk's row count ever exceeds `maxResults`) returns rows in a stable, deterministic order across pages.
- `iter_video_analytics()` and `iter_video_traffic_sources()` are generators (`yield`-based) — rows are upserted by the caller as they arrive, not batched into a single list first.
- `_analytics_query()` (`youtube.py:106-120`) retries with exponential backoff (`2^(attempt-1)`, capped at 30s, up to 5 attempts) on HTTP 5xx, or 403/429 specifically when the error body indicates `rateLimitExceeded`/`quotaExceeded`.

## Authentication

- Shorts detection (`fetch_shorts_video_ids()`, `youtube.py:174-206`) relies exclusively on the channel's UUSH ("uploads → Shorts") playlist; it raises `RuntimeError` if the uploads playlist ID doesn't start with `UU`, or if the derived `UUSH...` playlist 404s.
- `get_credentials()` (`youtube.py:51-72`) deletes `token.json` and re-runs the OAuth flow whenever **any** exception occurs while refreshing an expired token (`youtube.py:57-63`) — this is broader than "only on `invalid_grant`". The re-auth is not deferred to a later call: after deleting the token, the same `get_credentials()` invocation immediately falls through to `InstalledAppFlow.from_client_secrets_file(...).run_local_server(...)` and writes the new token before returning.
