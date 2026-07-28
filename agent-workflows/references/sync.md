# Synchronization Reference

## Purpose

How data gets from the YouTube APIs into SQLite: pipeline order, scheduling, scope semantics, and the caveats that affect data freshness/correctness. Database-side query/aggregation semantics live in `database.md`; this file covers ingestion only.

## Authoritative source files

- `backend/sync/status.py`, `backend/sync/orchestration.py`, `backend/sync/stages.py`, `backend/sync/scheduler.py`
- `backend/youtube/auth.py`, `backend/youtube/data_api.py`, `backend/youtube/analytics_api.py`
- `backend/database/` (sync-run helpers only: `create_sync_run`/`complete_sync_run`/`fail_sync_run`/`get_sync_runs`/`get_last_successful_batch_completed_at` in `sync_runs.py`, `get_last_analytics_date` in `analytics.py`, `get_last_traffic_source_date` in `traffic_sources.py`, `get_last_fx_rate` in `fx_rates.py`, `get_all_video_ids` in `videos.py`)

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

A single sync (`run_sync()`, `sync/orchestration.py:51-99`) runs five stages in order, always in this sequence:

```
videos → playlists → video_analytics → video_traffic_sources → fx_rates
```

Each stage is wrapped by `_run_stage()` (`sync/orchestration.py:28-48`) and recorded as its own `sync_runs` row; all five rows from one `run_sync()` call share one `batch_id` (a UUID generated once per call, `sync/orchestration.py:74`). The stage implementations themselves (`sync_videos`, `sync_playlists`, `sync_video_analytics`, `sync_video_traffic_sources`, `sync_fx_rates`) live in `sync/stages.py`; `orchestration.py` only sequences them and records their outcomes.

## Scheduling and state

- `_scheduler_loop()` (`sync/scheduler.py:12-16`) calls `run_sync()` immediately, then reschedules itself via `threading.Timer(86400, ...)` (24h), as a daemon thread.
- `start_background_scheduler()` (`sync/scheduler.py:20-45`), called once from `server.py`'s lifespan, calls `database.get_last_successful_batch_completed_at(FULL_SYNC_TYPES)` to find the latest batch where all five stages (`FULL_SYNC_TYPES = ("videos", "playlists", "video_analytics", "video_traffic_sources", "fx_rates")`, defined in `sync/orchestration.py:19-25`) succeeded. If that batch completed within the last 24h (by local calendar date), it schedules the next run for the *remaining* time in that window instead of running immediately. If no qualifying batch exists, it starts a sync immediately. This is what keeps a `uvicorn --reload` restart (triggered by every code save during development) from re-syncing on every reload.
- There is no separate persisted scheduler checkpoint — `sync_runs` is the sole source of truth. A partial batch (missing a stage) or a batch containing any non-success row for an expected stage does not count, even if another row for that same stage in the batch succeeded; the scheduler falls back to the latest fully-successful batch before it, or runs immediately if none exists.
- `get_status()` / `is_syncing()` (`sync/status.py:11-20`) expose `{is_syncing, message}` guarded by a module-level `threading.Lock` and `_is_syncing` bool — safe to poll from any thread. All mutation of that shared state (starting/finishing a sync, setting the progress message) is centralized in `sync/status.py` behind `try_start()`, `finish()`, and `set_message()` — `orchestration.py` and `stages.py` call these rather than touching the lock or globals directly. If a sync is already running, `run_sync()` returns immediately without starting a second one (`sync/orchestration.py:71-72`, via `status.try_start()` returning `False`).

## Scope behavior

`run_sync(scope="incremental"|"year"|"all", year=None)` (`sync/orchestration.py`):

- `scope`/`year` affect **only** `sync_video_analytics` and `sync_video_traffic_sources` (`sync/stages.py`). Videos, playlists, and FX rates always sync incrementally regardless of the requested scope (`sync/orchestration.py:78,81` hardcode `"incremental", None`).
- Raises `ValueError` if `scope == "year"` and `year is None` (`sync/orchestration.py:68-69`) — mirrored by `routes/synchronization.py`'s `POST /sync/trigger`, which returns `400` for the same condition before ever calling `run_sync`.
- `"incremental"` (default): resume each video from `INCREMENTAL_LOOKBACK_DAYS` before its own last-synced date, clamped to its publish date (see [Shared incremental lookback](#shared-incremental-lookback)).
- `"year"`: refetch the given calendar year for every video, ignoring any resume checkpoint, clamped to `[publish_date, yesterday]`.
- `"all"`: refetch each video's entire history (`publish_date` → yesterday), ignoring any resume checkpoint.

## Stage tracking

- `SyncCounts` (`sync/stages.py:17-22`) is a mutable dataclass (`rows_fetched`, `rows_written`, `rows_deleted`) accumulated incrementally *as rows are processed inside each stage's loop* — not computed from a return value at the end. If a stage raises partway through (e.g. video 200 of 378), the `sync_runs` row for that stage still reflects accurate partial totals, not zeros. It's defined in `sync/stages.py` since that's what the stage functions mutate directly; `sync/orchestration.py` imports it only to construct a fresh instance per stage.
- `_run_stage()` (`sync/orchestration.py:28-48`) always re-raises the underlying exception after recording failure via `fail_sync_run()` — so `run_sync()`'s overall `try/finally` (which just calls `status.finish()`) is unaffected by a stage failing.
- For `videos`/`playlists`/`fx_rates`, `sync_runs.scope` is always `"incremental"` and `year` is `NULL`. For `video_analytics`/`video_traffic_sources`, `scope`/`year` reflect whatever was passed into `run_sync()`.
- The playlists stage's `rows_deleted` sums `delete_playlist_items()`'s return value across every playlist in the loop (items are deleted and fully re-inserted on every sync, `sync/stages.py:71`) plus `delete_playlists_not_in()`'s return value (`sync/stages.py:76`) — cascaded FK deletes (e.g. `video_analytics` rows removed because their parent video was deleted) are not counted, since those helpers only report `cursor.rowcount` for the row they directly targeted.

## Video and playlist synchronization

- `sync_videos()` (`sync/stages.py:34-52`): fetches the uploads playlist ID, the Shorts video-ID set (via UUSH), and all video IDs; fetches full video details in batches of 50 (YouTube API's per-request ID limit); collects everything into memory first, upserts all of it, **then** deletes any DB video not present in the freshly-fetched ID set (cascades to `video_analytics`/`video_traffic_sources`).
- `sync_playlists()` (`sync/stages.py:55-72`): same collect-then-upsert-then-delete order, at the playlist level (cascades to `playlist_items`).

## Shared incremental lookback

`_incremental_lookback_start(last_date, publish_date)` (`sync/stages.py:25-31`) is the single helper both `sync_video_analytics` and `sync_video_traffic_sources` call for their `"incremental"` start date, so the two stages can't drift apart:

- If `last_date` is `None` (never synced), returns `publish_date`.
- Otherwise returns `max(publish_date, last_date - INCREMENTAL_LOOKBACK_DAYS)` (`INCREMENTAL_LOOKBACK_DAYS = 7`, `sync/stages.py:14`) — i.e. resumes a week before the last stored date, clamped so it never goes earlier than the video's publish date.

## Analytics synchronization

`sync_video_analytics(scope, year, counts)` (`sync/stages.py:75-114`):

- Per video, computes `start`/`range_end` based on `scope` (see [Scope behavior](#scope-behavior)); for `"incremental"`, `start = _incremental_lookback_start(get_last_analytics_date(video_id), publish_date)`.
- If `start > range_end`, the video is skipped entirely via `continue` — **zero API calls** for that video. This is what prevents querying analytics for a video before it existed even when an unrelated `year` is requested.
- **7-day lookback on incremental mode** (see [Shared incremental lookback](#shared-incremental-lookback)): analytics metrics (views/watch time/revenue) for recent days are not fully settled in the YouTube API at sync time, so each incremental run re-fetches and re-upserts the last 7 days rather than resuming strictly after the last synced date. Re-upserting an already-settled day leaves its metric values unchanged, but `updated_at` is still refreshed on every upsert (see `database.md`) — it is not a true no-op at the row level.

## Traffic-source synchronization

`sync_video_traffic_sources(scope, year, counts)` (`sync/stages.py:117-156`):

- Same `scope` semantics as analytics, including the shared [incremental lookback](#shared-incremental-lookback): `start = _incremental_lookback_start(get_last_traffic_source_date(video_id), publish_date)`.
- Traffic-source data for a given day is not fully available from the API until some time after that day ends; the lookback corrects any recent day that was stored before its data had fully arrived. Re-upserting an already-settled day leaves its metric values unchanged, but `updated_at` is still refreshed on every upsert (see `database.md`) — it is not a true no-op at the row level.

## FX-rate synchronization

`sync_fx_rates()` (`sync/stages.py:159-186`):

- Incremental from `get_last_fx_rate()["date"] + 1 day`; first run starts `2015-01-01`.
- Fetches `USDSGD=X` from Yahoo Finance via `yfinance` (imported **inside** the function, not at module scope).
- Weekends/holidays (days with no `yfinance` close) are forward-filled with the last known `carry` value.

## YouTube API requests and pagination

- Both `iter_video_analytics()` and `iter_video_traffic_sources()` (`youtube/analytics_api.py`) chunk the requested date range into **12-month windows** via `_chunk_date_range(..., months=12)` (`youtube/analytics_api.py:52-65`; the function's own default is `months=4`, but both call sites override it to 12). Chunks are anchored to the video's own start date, not calendar-aligned Jan–Dec.
- `maxResults` is set high enough to avoid pagination in the common case:
  - `iter_video_analytics`: `maxResults=2000` (`youtube/analytics_api.py:104`) — a year is at most 365 rows, single `day` dimension.
  - `iter_video_traffic_sources`: `maxResults=10000` (`youtube/analytics_api.py:155`) — a year's theoretical ceiling is 365 days × 21 possible `insightTrafficSourceType` values = 7665 rows.
- Both generators pass an explicit `sort` param (`day` / `day,insightTrafficSourceType`) so that `_fetch_analytics_rows()`'s `startIndex`-based pagination fallback (used only if a chunk's row count ever exceeds `maxResults`) returns rows in a stable, deterministic order across pages.
- `iter_video_analytics()` and `iter_video_traffic_sources()` are generators (`yield`-based) — rows are upserted by the caller as they arrive, not batched into a single list first.
- `_analytics_query()` (`youtube/analytics_api.py:35-49`) retries with exponential backoff (`2^(attempt-1)`, capped at 30s, up to 5 attempts) on HTTP 5xx, or 403/429 specifically when the error body indicates `rateLimitExceeded`/`quotaExceeded`.
- All three YouTube API modules share OAuth via `youtube/auth.py`'s `get_credentials()`; `youtube/data_api.py`'s `_data_client()` and `youtube/analytics_api.py`'s `_analytics_client()` each call it independently to build their respective `googleapiclient` service objects.

## Authentication

- Shorts detection (`fetch_shorts_video_ids()`, `youtube/data_api.py:43-75`) relies exclusively on the channel's UUSH ("uploads → Shorts") playlist; it raises `RuntimeError` if the uploads playlist ID doesn't start with `UU`, or if the derived `UUSH...` playlist 404s.
- `get_credentials()` (`youtube/auth.py:21-41`) deletes `token.json` and re-runs the OAuth flow whenever **any** exception occurs while refreshing an expired token (`youtube/auth.py:27-32`) — this is broader than "only on `invalid_grant`". The re-auth is not deferred to a later call: after deleting the token, the same `get_credentials()` invocation immediately falls through to `InstalledAppFlow.from_client_secrets_file(...).run_local_server(...)` and writes the new token before returning. Token and client-secret paths are resolved from the backend root (`Path(__file__).parent.parent`, one level above the `youtube/` package), so they always resolve to `backend/secrets/token.json` and `backend/secrets/client_secret.json`.
