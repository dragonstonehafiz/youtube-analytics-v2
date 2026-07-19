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
- [Analytics synchronization](#analytics-synchronization)
- [Traffic-source synchronization](#traffic-source-synchronization)
- [FX-rate synchronization](#fx-rate-synchronization)
- [YouTube API requests and pagination](#youtube-api-requests-and-pagination)
- [Authentication](#authentication)

## Pipeline overview

A single sync (`run_sync()`, `sync.py:79-135`) runs five stages in order, always in this sequence:

```
videos → playlists → video_analytics → video_traffic_sources → fx_rates
```

Each stage is wrapped by `_run_stage()` and recorded as its own `sync_runs` row; all five rows from one `run_sync()` call share one `batch_id` (a UUID generated once per call, `sync.py:105`).

## Scheduling and state

- `_scheduler_loop()` (`sync.py:305-310`) calls `run_sync()` immediately, then reschedules itself via `threading.Timer(86400, ...)` (24h), as a daemon thread.
- `start_background_scheduler()` (`sync.py:313-344`), called once from `server.py`'s lifespan, reads the persisted `last_synced_at` from `sync_state`. If the last sync was under 24h ago, it schedules the next run for the *remaining* time in that window instead of running immediately.
- `last_synced_at` is a single global checkpoint stored in `sync_state` (survives restarts) used only to decide "was the last full sync run more than 24h ago" — it is **not** a per-row or per-date audit trail. It's stored as a **date-only** string (`date.today().isoformat()`, `sync.py:127`), not a full timestamp, and is only written after all five stages succeed.
- `get_status()` / `is_syncing()` (`sync.py:21-30`) expose `{is_syncing, last_synced_at, message}` guarded by a module-level `threading.Lock` and `_is_syncing` bool — safe to poll from any thread. If a sync is already running, `run_sync()` returns immediately without starting a second one (`sync.py:100-103`).

## Scope behavior

`run_sync(scope="incremental"|"year"|"all", year=None)`:

- `scope`/`year` affect **only** `_sync_video_analytics` and `_sync_video_traffic_sources`. Videos, playlists, and FX rates always sync incrementally regardless of the requested scope (`sync.py:109,112,125` hardcode `"incremental", None`).
- Raises `ValueError` if `scope == "year"` and `year is None` (`sync.py:97-98`) — mirrored by `routes.py`'s `POST /sync/trigger`, which returns `400` for the same condition before ever calling `run_sync`.
- `"incremental"` (default): resume each video from its own last-synced date.
- `"year"`: refetch the given calendar year for every video, ignoring any resume checkpoint, clamped to `[publish_date, yesterday]`.
- `"all"`: refetch each video's entire history (`publish_date` → yesterday), ignoring any resume checkpoint.

## Stage tracking

- `SyncCounts` (`sync.py:44-49`) is a mutable dataclass (`rows_fetched`, `rows_written`, `rows_deleted`) accumulated incrementally *as rows are processed inside each stage's loop* — not computed from a return value at the end. If a stage raises partway through (e.g. video 200 of 378), the `sync_runs` row for that stage still reflects accurate partial totals, not zeros.
- `_run_stage()` (`sync.py:52-72`) always re-raises the underlying exception after recording failure via `fail_sync_run()` — so `run_sync()`'s overall `try/finally` (which just clears `_is_syncing`) is unaffected by a stage failing.
- For `videos`/`playlists`/`fx_rates`, `sync_runs.scope` is always `"incremental"` and `year` is `NULL`. For `video_analytics`/`video_traffic_sources`, `scope`/`year` reflect whatever was passed into `run_sync()`.
- The playlists stage's `rows_deleted` sums `delete_playlist_items()`'s return value across every playlist in the loop (items are deleted and fully re-inserted on every sync, `sync.py:171`) plus `delete_playlists_not_in()`'s return value (`sync.py:176`) — cascaded FK deletes (e.g. `video_analytics` rows removed because their parent video was deleted) are not counted, since those helpers only report `cursor.rowcount` for the row they directly targeted.

## Video and playlist synchronization

- `_sync_videos()` (`sync.py:138-156`): fetches the uploads playlist ID, the Shorts video-ID set (via UUSH), and all video IDs; fetches full video details in batches of 50 (YouTube API's per-request ID limit); collects everything into memory first, upserts all of it, **then** deletes any DB video not present in the freshly-fetched ID set (cascades to `video_analytics`/`video_traffic_sources`).
- `_sync_playlists()` (`sync.py:159-176`): same collect-then-upsert-then-delete order, at the playlist level (cascades to `playlist_items`).

## Analytics synchronization

`_sync_video_analytics(scope, year, counts)` (`sync.py:179-214`):

- Per video, computes `start`/`range_end` based on `scope` (see [Scope behavior](#scope-behavior)); for `"incremental"`, `start = get_last_analytics_date(video_id) + 1 day` (or `publish_date` if never synced).
- If `start > range_end`, the video is skipped entirely via `continue` — **zero API calls** for that video. This is what prevents querying analytics for a video before it existed even when an unrelated `year` is requested.
- **No lookback window on incremental mode**: once a day is synced, it is never re-fetched by a later incremental run. If that day's analytics (views/watch time/revenue) hadn't fully settled in the YouTube API at sync time, the stored value can permanently undercount versus YouTube Studio unless a `year`/`all` resync is explicitly run for that period.

## Traffic-source synchronization

`_sync_video_traffic_sources(scope, year, counts)` (`sync.py:217-261`):

- Same `scope` semantics as analytics.
- **7-day lookback on incremental mode**: `start = get_last_traffic_source_date(video_id) - 7 days` (clamped to `publish_date` if that goes earlier), not `last_date + 1 day`. Traffic-source data for a given day is not fully available from the API until some time after that day ends; this lookback corrects any recent day that was stored before its data had fully arrived. Re-upserting an already-settled day leaves its metric values unchanged, but `updated_at` is still refreshed on every upsert (see `database.md`) — it is not a true no-op at the row level.

## FX-rate synchronization

`_sync_fx_rates()` (`sync.py:264-298`):

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
