# Synchronization Reference

## Purpose

How data gets from the YouTube APIs into SQLite: plan validation, stage order, startup freshness, scope semantics, and the caveats that affect data freshness/correctness. Database-side query/aggregation semantics live in `database.md`; this file covers ingestion only.

## Authoritative source files

- `backend/sync/plans.py`, `backend/sync/status.py`, `backend/sync/orchestration.py`, `backend/sync/stages.py`, `backend/sync/scheduler.py`
- `backend/youtube/auth.py`, `backend/youtube/data_api.py`, `backend/youtube/analytics_api.py`
- `backend/logging_config.py` (shared logging configuration used by `orchestration.py`, `stages.py`, `data_api.py`, `analytics_api.py`)
- `backend/database/` (sync-run helpers only: `create_sync_run`/`complete_sync_run`/`fail_sync_run`/`get_sync_runs`/`get_last_successful_run_completed_at` in `sync_runs.py`, `get_last_analytics_date` in `analytics.py`, `get_last_traffic_source_date` in `traffic_sources.py`, `get_last_fx_rate` in `fx_rates.py`, `get_all_video_ids` in `videos.py`)

## Contents

- [Pipeline overview](#pipeline-overview)
- [Sync plans and validation](#sync-plans-and-validation)
- [Startup freshness and state](#startup-freshness-and-state)
- [Scope behavior](#scope-behavior)
- [Stage tracking](#stage-tracking)
- [Video and playlist synchronization](#video-and-playlist-synchronization)
- [Shared incremental lookback](#shared-incremental-lookback)
- [Analytics synchronization](#analytics-synchronization)
- [Traffic-source synchronization](#traffic-source-synchronization)
- [FX-rate synchronization](#fx-rate-synchronization)
- [YouTube API requests and pagination](#youtube-api-requests-and-pagination)
- [Pagination termination](#pagination-termination)
- [Authentication](#authentication)
- [Sync logging](#sync-logging)

## Pipeline overview

A sync runs an explicit **plan**: a set of selected stages, always executed in the canonical order defined by `STAGE_ORDER` (`sync/plans.py:14-21`), regardless of the order the stages were submitted in:

```
playlists → videos → pruning → video_analytics → video_traffic_sources → fx_rates
```

`pruning` is the only stage that deletes video rows. It is opt-in: `validate_plan()` rejects any plan that names it without also naming both `playlists` and `videos` (`STAGES_REQUIRING_PLAYLISTS_AND_VIDEOS`, `sync/plans.py:33`), and it is excluded from the startup plan (`DESTRUCTIVE_STAGES`, `sync/plans.py:25`; see [Startup freshness and state](#startup-freshness-and-state)).

`execute_plan()` (`sync/orchestration.py:112-183`) iterates `STAGE_ORDER` and skips any stage the plan omits. Each selected stage is wrapped by `_run_stage()` (`sync/orchestration.py:54-109`) and recorded as its own `sync_runs` row; every row from one plan shares one `batch_id` (a UUID generated once per plan). Omitted stages get **no** row — there are no placeholder records. Execution is fail-fast: a failing stage is recorded with its partial counters, and the stages after it neither run nor create rows — this is also what guarantees `pruning` can never run after a `playlists` or `videos` failure.

The stage implementations themselves (`sync_videos`, `sync_playlists`, `sync_pruning`, `sync_video_analytics`, `sync_video_traffic_sources`, `sync_fx_rates`) live in `sync/stages.py`. `orchestration.py` looks up each stage's progress message in `_STAGE_MESSAGES` (`sync/orchestration.py`) and publishes it via `status.update_sync_progress()` before dispatching to its call inline inside `execute_plan()`'s loop, since `playlists`/`videos`/`pruning` thread plan-local video-ID sets between each other (see [Video and playlist synchronization](#video-and-playlist-synchronization)) while the other stages don't need that state. `video_analytics` and `video_traffic_sources` have no entry in `_STAGE_MESSAGES` (`None`) since they report their own per-video progress from inside their loop via the same `update_sync_progress()` call.

Two entry points wrap the executor:

- `execute_plan(stages)` — runs a plan whose active-state reservation the caller **already holds**. Used by `POST /sync/trigger`, which reserves before responding.
- `run_plan(stages)` (`sync/orchestration.py:184-195`) — acquires the reservation itself and returns `False` if a sync is already active. Used by the startup sync.

Calling `execute_plan` from an unreserved caller leaves the sync unguarded; calling `run_plan` from a caller that already reserved would be blocked by its own reservation. The split exists for exactly that reason.

## Sync plans and validation

`sync/plans.py` owns the plan vocabulary. Constants: `STAGE_ORDER` (canonical order, `sync/plans.py:14-21`), `DESTRUCTIVE_STAGES` (`sync/plans.py:25` — just `pruning`; excluded from `full_incremental_plan()`), `PERIOD_AWARE_STAGES` (`sync/plans.py:29` — `video_analytics` and `video_traffic_sources`), `STAGES_REQUIRING_PLAYLISTS_AND_VIDEOS` (`sync/plans.py:33` — just `pruning`), `SCOPES` (`sync/plans.py:36`), and `FULL_SYNC_TYPES` (`sync/plans.py:43`), which is *derived from* `STAGE_ORDER` so the execution order and the complete-batch definition cannot drift.

`PlanStage` (`sync/plans.py:51-61`) is a frozen dataclass of `stage`, `scope`, `year`. `scope`/`year` stay `None` for the always-incremental stages, which keeps `validate_plan()` idempotent — a validated plan revalidates cleanly rather than being rejected for carrying a scope it should not.

`validate_plan(stages)` (`sync/plans.py:89-120`) returns the stages in canonical order and raises `PlanValidationError` when:

- the plan is empty;
- a stage appears more than once;
- a stage name is not in `STAGE_ORDER`;
- a period-aware stage omits `scope`, or names a scope outside `SCOPES`;
- `scope="year"` without a `year`, or a `year` supplied with `incremental`/`all`;
- a `scope` or `year` is attached to `videos`, `playlists`, `pruning`, or `fx_rates`;
- the requested year is outside `available_years()`;
- `pruning` is named without both `playlists` and `videos` also in the plan.

`available_years()` (`sync/plans.py:64-74`) spans `database.get_earliest_published_year()` through the current year, newest first. It returns an **empty tuple** when no videos have been synced yet, in which case every year-scoped plan is rejected; `incremental` and `all` plans stay valid.

`execute_plan()` revalidates its input rather than trusting the caller, so no code path can drive the stage loop with an unchecked plan. `full_incremental_plan()` (`sync/plans.py:144-154`) builds the five-stage **non-destructive** startup plan — every canonical stage except `pruning` — used by the startup sync.

## Startup freshness and state

- `start_background_scheduler()` (`sync/scheduler.py:30-44`), called once from `server.py`'s lifespan, runs **one** non-destructive incremental sync (`full_incremental_plan()`, which excludes `pruning`) on a daemon thread unless `synced_today()` is already true. There is no recurring timer: the app is not expected to stay running long enough for one to fire, so freshness is decided per launch. Pruning is never selected automatically at any freshness check — it is manual-only.
- `synced_today()` (`sync/scheduler.py:12-27`) calls `database.get_last_successful_run_completed_at()` and compares its local calendar date against today. A missing or unparseable timestamp counts as not-synced. Restarting the backend after any successful sync on the same local date therefore does nothing.
- There is no separate persisted checkpoint — `sync_runs` is the sole source of truth. Any single succeeded run qualifies: its `sync_type`, scope, and `batch_id` do not matter, and other stages in the same batch may have failed or never run. Only failed and still-running rows are ignored.
- A selective manual sync therefore suppresses that day's startup sync. Manually syncing one stage — even just `fx_rates` — marks the day as synced, and the next launch runs nothing. A day on which every run failed still counts as not-synced, so the next launch retries.
- `get_sync_status()` (`sync/status.py`) exposes `{state, message}` guarded by a module-level `threading.Lock`, where `state` is one of `idle | running | success | failed` — safe to poll from any thread. All mutation of that shared state is centralized in `sync/status.py` behind `try_begin_sync()`, `update_sync_progress()`, `complete_sync()`, `fail_sync()`, and `reset_sync_status()`.
- `try_begin_sync(message="")` (`sync/status.py`) sets `state="running"` **and** the initial message under one lock acquisition, so a status poll can never observe the running state still carrying the previous run's terminal message. It is the single reservation primitive: the manual route calls it before responding, and `run_plan()` calls it for the startup sync. Whichever loses the race gets `False` — the route turns that into `409`, the startup sync silently declines. A successful reservation replaces any retained terminal result (`success`/`failed`) from the previous run.
- `update_sync_progress(message)` is a no-op unless `state="running"`, so a stray call cannot fabricate a running state.
- `execute_plan()` transitions to exactly one terminal state — `complete_sync("Sync complete")` on success, or `fail_sync(...)` with a fixed, safe, operation-specific message on any exception (plan validation or any stage) — before re-raising. There is no separate "finish"/cleanup step: the terminal transition itself is what ends the running state, so failed and invalid runs cannot leave the app permanently "syncing". Terminal state (`success`/`failed`) is retained until the next reservation.
- Public failure text never includes exception content, headers, credentials, tokens, or API response bodies — see [Sync logging](#sync-logging) for how the same constraint applies to log records. `_STAGE_FAILURE_LABELS` (`sync/orchestration.py`) maps each stage to a fixed label (e.g. `"syncing videos"`) used to build `"Sync failed while syncing videos"`; a failure before any stage starts (plan validation) reports `"Sync failed during plan validation"`. Terminal messages carry no trailing period; in-progress messages keep their trailing `...`. Raw exception text still reaches `sync_runs.error_message` via `fail_sync_run()` and safe exception context still reaches the sync logger, unchanged.

## Scope behavior

Scopes are per-stage, not per-sync: `video_analytics` and `video_traffic_sources` each carry their own `scope`/`year` and can differ within one plan (e.g. analytics for `2024` alongside a full-history traffic-source refetch).

- `scope`/`year` affect **only** `sync_video_analytics` and `sync_video_traffic_sources` (`sync/stages.py`). Videos, playlists, pruning, and FX rates always sync incrementally (or, for pruning, run once against current state) and must not be given a scope at all — `validate_plan()` rejects a plan that tries.
- `"incremental"`: resume each video from `INCREMENTAL_LOOKBACK_DAYS` before its own last-synced date, clamped to its publish date (see [Shared incremental lookback](#shared-incremental-lookback)).
- `"year"`: refetch the given calendar year for every video, ignoring any resume checkpoint, clamped to `[publish_date, yesterday]`.
- `"all"`: refetch each video's entire history (`publish_date` → yesterday), ignoring any resume checkpoint.

## Stage tracking

- `SyncCounts` (`sync/stages.py:21-25`) is a mutable dataclass (`rows_fetched`, `rows_written`, `rows_deleted`) accumulated incrementally *as rows are processed inside each stage's loop* — not computed from a return value at the end. If a stage raises partway through (e.g. video 200 of 378), the `sync_runs` row for that stage still reflects accurate partial totals, not zeros. It's defined in `sync/stages.py` since that's what the stage functions mutate directly; `sync/orchestration.py` imports it only to construct a fresh instance per stage.
- `_run_stage()` (`sync/orchestration.py:54-109`) always re-raises the underlying exception after recording failure via `fail_sync_run()`, so `execute_plan()`'s enclosing `except` still runs its `fail_sync()` transition and the exception propagates to the caller. It also logs that stage's start, completion, and failure — see [Sync logging](#sync-logging).
- For `videos`/`playlists`/`pruning`/`fx_rates`, `sync_runs.scope` is always `"incremental"` and `year` is `NULL`. For `video_analytics`/`video_traffic_sources`, `scope`/`year` reflect that stage's own plan entry. `recorded_scope()`/`recorded_year()` (`sync/plans.py:77-86`) derive both values, so a non-period stage can never record a scope it was not run with.
- `pruning` gets its own `sync_runs` row and its own `rows_deleted` count, independent of `videos`'/`playlists`' counts — it is the only stage that writes to `rows_deleted` for video rows.
- The playlists stage's `rows_deleted` sums `delete_playlist_items()`'s return value across every playlist in the loop (items are deleted and fully re-inserted on every sync, `sync/stages.py:140`) plus `delete_playlists_not_in()`'s return value (`sync/stages.py:151`) — cascaded FK deletes (e.g. `video_analytics` rows removed because their parent video was deleted) are not counted, since those helpers only report `cursor.rowcount` for the row they directly targeted.

## Video and playlist synchronization

Video deletion and video/playlist discovery are separate stages. `playlists` and `videos` only fetch and upsert; only `pruning` deletes video rows. This split exists so a plan can safely refresh video/playlist data without any risk of deleting anything — pruning has to be selected deliberately.

- `sync_playlists()` (`sync/stages.py:101-152`): fetches all playlists and their items, upserts them, then deletes any DB playlist not returned by the API (cascades to `playlist_items`). Its item replace is delete-then-reinsert per playlist, gated on that playlist's own item pagination completing (leaving stored items untouched otherwise); the listing-level reconcile (`delete_playlists_not_in()`) is gated on the playlist *listing* itself completing. Both gates emit a `WARNING` naming `reason=pagination_truncated` when they skip. It also collects every non-null `video_id` referenced by any playlist item — regardless of that playlist's own truncation state, since a partial page set is still real, known membership — and returns that set for `sync_videos()` to combine with the uploads-playlist IDs.
- `sync_videos()` (`sync/stages.py:37-98`): calls `fetch_channel_identity()` to get the authenticated channel's ID and uploads-playlist ID, fetches the Shorts video-ID set (via UUSH) and the full uploads-playlist ID list, then fetches details (batches of 50, the Data API's per-request ID limit) for the **union** of the uploads IDs and the playlist-discovered candidates passed in from `sync_playlists()`. Every uploads ID is treated as channel-owned outright; a playlist-only candidate is upserted only when its returned `snippet.channelId` matches the authenticated channel — this ownership check is what stops a video from someone else's playlist being imported as if it were this channel's. It never deletes. It returns the full channel-owned ID set (every uploads ID, even one `videos.list` didn't return details for, plus every ownership-confirmed playlist-only ID) for `sync_pruning()` to use as its retain set.
- `sync_pruning()` (`sync/stages.py:155-158`): the sole stage that deletes video rows (cascades to `video_analytics`/`video_traffic_sources`). Calls `database.delete_videos_not_in()` unconditionally with the channel-owned ID set built by `sync_playlists()` + `sync_videos()` in the same plan — there is no truncation-based safety gate on pruning itself; canonical stage ordering and `validate_plan()`'s `playlists`+`videos` dependency are what keep it from ever running without that set populated. An empty set deletes every video (`database/videos.py::delete_videos_not_in()` has no empty-list guard) — correct only when the channel genuinely has zero owned videos, which is why pruning is manual-only and never part of the startup plan.
- The uploads playlist is how the Data API enumerates a channel's videos — there is no channel-wide video listing endpoint — so `fetch_all_video_ids()`'s result is one of the two authorities pruning's retain set is built from (the other being playlist membership, for videos the uploads enumeration might otherwise miss).
- `sync_video_analytics()`, `sync_video_traffic_sources()`, and `sync_fx_rates()` only ever upsert; analytics and traffic-source rows are removed exclusively by cascade from a pruning-triggered video deletion. Their writes are idempotent, so a short fetch there is self-healing on the next run and needs no gate.

## Shared incremental lookback

`_incremental_lookback_start(last_date, publish_date)` (`sync/stages.py:28-34`) is the single helper both `sync_video_analytics` and `sync_video_traffic_sources` call for their `"incremental"` start date, so the two stages can't drift apart:

- If `last_date` is `None` (never synced), returns `publish_date`.
- Otherwise returns `max(publish_date, last_date - INCREMENTAL_LOOKBACK_DAYS)` (`INCREMENTAL_LOOKBACK_DAYS = 7`, `sync/stages.py:15`) — i.e. resumes a week before the last stored date, clamped so it never goes earlier than the video's publish date.

## Analytics synchronization

`sync_video_analytics(scope, year, counts)` (`sync/stages.py:161-216`):

- Per video, computes `start`/`range_end` based on `scope` (see [Scope behavior](#scope-behavior)); for `"incremental"`, `start = _incremental_lookback_start(get_last_analytics_date(video_id), publish_date)`.
- If `start > range_end`, the video is skipped entirely via `continue` — **zero API calls** for that video. This is what prevents querying analytics for a video before it existed even when an unrelated `year` is requested.
- **7-day lookback on incremental mode** (see [Shared incremental lookback](#shared-incremental-lookback)): analytics metrics (views/watch time/revenue) for recent days are not fully settled in the YouTube API at sync time, so each incremental run re-fetches and re-upserts the last 7 days rather than resuming strictly after the last synced date. Re-upserting an already-settled day leaves its metric values unchanged, but `updated_at` is still refreshed on every upsert (see `database.md`) — it is not a true no-op at the row level.
- Both `continue` branches (no publish date, empty range) and the per-video row count emit a sync-only `DEBUG` record — see [Sync logging](#sync-logging).

## Traffic-source synchronization

`sync_video_traffic_sources(scope, year, counts)` (`sync/stages.py:219-274`):

- Same `scope` semantics as analytics, including the shared [incremental lookback](#shared-incremental-lookback): `start = _incremental_lookback_start(get_last_traffic_source_date(video_id), publish_date)`.
- Traffic-source data for a given day is not fully available from the API until some time after that day ends; the lookback corrects any recent day that was stored before its data had fully arrived. Re-upserting an already-settled day leaves its metric values unchanged, but `updated_at` is still refreshed on every upsert (see `database.md`) — it is not a true no-op at the row level.
- Same per-video `DEBUG` detail records as analytics — see [Sync logging](#sync-logging).

## FX-rate synchronization

`sync_fx_rates()` (`sync/stages.py:277-316`):

- Incremental from `get_last_fx_rate()["date"] + 1 day`; first run starts `2015-01-01`.
- Fetches `USDSGD=X` from Yahoo Finance via `yfinance` (imported **inside** the function, not at module scope).
- Weekends/holidays (days with no `yfinance` close) are forward-filled with the last known `carry` value.
- Logs one sync-only `DEBUG` record for the no-work early return, and one after the download loop reporting days written — see [Sync logging](#sync-logging).

## YouTube API requests and pagination

- Both `iter_video_analytics()` and `iter_video_traffic_sources()` (`youtube/analytics_api.py`) chunk the requested date range into **12-month windows** via `_chunk_date_range(..., months=12)` (`youtube/analytics_api.py:84-97`; the function's own default is `months=4`, but both call sites override it to 12). Chunks are anchored to the video's own start date, not calendar-aligned Jan–Dec.
- `maxResults` is set high enough to avoid pagination in the common case:
  - `iter_video_analytics`: `maxResults=2000` (`youtube/analytics_api.py:166`) — a year is at most 365 rows, single `day` dimension.
  - `iter_video_traffic_sources`: `maxResults=10000` (`youtube/analytics_api.py:218`) — a year's theoretical ceiling is 365 days × 21 possible `insightTrafficSourceType` values = 7665 rows.
- Both generators pass an explicit `sort` param (`day` / `day,insightTrafficSourceType`) so that `_fetch_analytics_rows()`'s `startIndex`-based pagination fallback (used only if a chunk's row count ever exceeds `maxResults`) returns rows in a stable, deterministic order across pages.
- `iter_video_analytics()` and `iter_video_traffic_sources()` are generators (`yield`-based) — rows are upserted by the caller as they arrive, not batched into a single list first.
- `_analytics_query()` (`youtube/analytics_api.py:61-81`) retries with exponential backoff (`2^(attempt-1)`, capped at 30s, up to 5 attempts) on HTTP 5xx, or 403/429 specifically when the error body indicates `rateLimitExceeded`/`quotaExceeded`. Each retry emits a `WARNING` record — see [Sync logging](#sync-logging).
- All three YouTube API modules share OAuth via `youtube/auth.py`'s `get_credentials()`; `youtube/data_api.py`'s `_data_client()` and `youtube/analytics_api.py`'s `_analytics_client()` each call it independently to build their respective `googleapiclient` service objects.
- The four token-pagination loops in `youtube/data_api.py` (`fetch_shorts_video_ids()`, `fetch_all_video_ids()`, `fetch_playlists()`, `fetch_playlist_items()`) each emit one record per fetched page — see [Sync logging](#sync-logging) and [Pagination termination](#pagination-termination).

## Pagination termination

All four Data API loops delegate their stop/continue decision to `_next_page_token()`
(`youtube/data_api.py`), which returns `(token_to_follow, truncated)` and logs the page
as a side effect. Each of the four returns `(items, truncated)` to its caller.

| Returned items | `nextPageToken` | Result | `truncated` |
|---|---|---|---|
| Non-empty | Absent | Finish | False |
| Non-empty | Present, not seen this call | Record the token and request the next page | False |
| Non-empty | Present, already seen this call | `WARNING` `repeated_page_token`, finish; the page's items are kept | True |
| Empty | Absent | Finish with what was collected | False |
| Empty | Present | `WARNING` `empty_page_with_token`, finish with what was collected | True |

Two conditions end pagination early. An **empty page that still carries a token** would
otherwise be followed indefinitely. A **repeated cursor** — the same `nextPageToken`
returned twice within one call — means the next request would re-fetch a page already
seen; this covers both an immediate repeat (the token equal to the one used for the
current request) and a longer cycle such as `A → B → A`, because every followed token is
retained for the whole call. Both were observed in production: a run that returned 36
items on page 1 then reissued the identical cursor `EAAaBlBUOkNDUQ` for 178 further
pages until the Data API quota was gone.

Cursor history is per invocation. `fetch_playlist_items()` creates its set inside the
function, so two playlists that legitimately hand back the same token string are never
confused for a cycle; nothing about token history is shared across playlists, calls,
clients, or batches.

`truncated` is what makes early termination safe rather than merely quiet: it marks the
returned rows as an incomplete view that must not be treated as authoritative for
absence. See [Video and playlist synchronization](#video-and-playlist-synchronization)
for the two playlist-level deletes it gates (`delete_playlist_items()` per playlist and
the listing-level `delete_playlists_not_in()`) — `sync_videos()` no longer deletes at
all, and `sync_pruning()`'s delete is ungated by any truncation flag. `fetch_all_video_ids()`'s
own `truncated` flag is otherwise unused now that `sync_videos()` doesn't delete against
it. `fetch_shorts_video_ids()` also returns the flag, but no caller acts on it — a
truncated Shorts set only mislabels some videos' `content_type`, which the next complete
sync corrects.

The Analytics API paginator is unaffected. `_fetch_analytics_rows()`
(`youtube/analytics_api.py:100`) is `startIndex`-based rather than token-based and stops
as soon as a page returns fewer rows than `maxResults` — including an empty page — and
continues after a page that returns exactly `maxResults` rows; it has no cursor to
repeat and returns no truncation flag.

## Authentication

- Shorts detection (`fetch_shorts_video_ids()`, `youtube/data_api.py:128-169`) relies exclusively on the channel's UUSH ("uploads → Shorts") playlist; it raises `RuntimeError` if the uploads playlist ID doesn't start with `UU`, or if the derived `UUSH...` playlist 404s.
- `get_credentials()` (`youtube/auth.py:21-42`) deletes `token.json` and re-runs the OAuth flow whenever **any** exception occurs while refreshing an expired token (`youtube/auth.py:28-33`) — this is broader than "only on `invalid_grant`". The re-auth is not deferred to a later call: after deleting the token, the same `get_credentials()` invocation immediately falls through to `InstalledAppFlow.from_client_secrets_file(...).run_local_server(...)` and writes the new token before returning. Token and client-secret paths are resolved from the backend root (`Path(__file__).parent.parent`, one level above the `youtube/` package), so they always resolve to `backend/secrets/token.json` and `backend/secrets/client_secret.json`.

## Sync logging

`backend/logging_config.py` (see `architecture.md`) is the shared configuration every
module below acquires through `get_logger("sync")`. All records here go to the
`youtube_analytics.sync` logger: plan-level and per-stage `INFO`/`WARNING`/`ERROR`
records reach both `data/application.log` and `data/sync.log`; the `DEBUG` detail events
below reach `data/sync.log` only.

Plan-level and per-stage records, all in `sync/orchestration.py`:

- `execute_plan()` logs an `ERROR` and re-raises if `validate_plan()` rejects the plan, otherwise one `INFO` "Sync plan started" record naming the selected `sync_types` — never stage counts, since counts are stage-local (see [Stage tracking](#stage-tracking)).
- `run_plan()` logs a `WARNING` with `reason=already_active` before returning `False` when a sync is already running.
- `_run_stage()` logs an `INFO` "Sync stage started" record right after constructing that stage's fresh `SyncCounts`, an `INFO` "Sync stage completed" record with `rows_fetched`/`rows_written`/`rows_deleted` after `complete_sync_run()` succeeds, and an `ERROR` "Sync stage failed" record (partial counts, `scope`, `year`, and safe exception context) before calling `fail_sync_run()`. A `create_sync_run()`/`complete_sync_run()`/`fail_sync_run()` failure logs its own `ERROR` naming the failing `operation`, without changing any persistence call's arguments, order, or exception propagation.
- Failure records never interpolate the exception message or enable traceback formatting — only the exception's class name and final-frame file/function/line (`logging_config.exception_context()`), so an external API's error body or an OAuth token embedded in an exception message can never reach either log file. `database.fail_sync_run()` is still passed `str(exc)` exactly as before; only the log record is restricted.

The sync-only `DEBUG` detail events, each one line emitted after the work completes —
never a paired before/after record, never one line per returned row:

| Event | Where | Fields |
|---|---|---|
| Page fetched | the four `youtube/data_api.py` token-pagination loops, via `_log_page()` | resource, page number, item count, owning entity id and name where one exists, that page's `nextPageToken` |
| Analytics page fetched | `youtube/analytics_api.py::_fetch_analytics_rows()`, via its own `_log_page()` | resource, page number, row count, `startIndex`, owning `video_id` and title |
| Video processed | the per-video loops in `sync_video_analytics()`/`sync_video_traffic_sources()` | ordinal/total, `video_id`, rows fetched for that video, title |
| Video skipped | the two `continue` branches in each analytics stage | ordinal/total, `video_id`, reason (`no_publish_date` or `empty_range`), title |
| FX rates downloaded | `sync/stages.py::sync_fx_rates()` | requested start/end dates, days written, or the no-work condition |

Two conditions are anomalies rather than routine detail and are logged at `WARNING`, so
they reach `application.log` as well and are visible without lowering the log level:

| Event | Where | Fields |
|---|---|---|
| Empty page with a token | `_log_page()` in `youtube/data_api.py`, when a page returns zero items but still supplies a `nextPageToken` | the page-fetched fields plus `empty_page_with_token=true` |
| Repeated pagination cursor | `_log_page()` in `youtube/data_api.py`, when a `nextPageToken` was already followed during this call | the page-fetched fields plus `repeated_page_token=true`, including the repeated token itself |
| Playlist cleanup skipped | `sync_playlists()`, when a paginator reported truncation | which cleanup was skipped, `reason=pagination_truncated`, the fetched count, and the playlist id/title for the per-playlist case |
| Video classification skipped | `sync_videos()`, when Shorts-playlist pagination reported truncation | `reason=shorts_pagination_truncated` |
| Video details missing | `sync_videos()`, when `fetch_videos()` didn't return an item for one or more requested IDs | count and sorted list of the missing IDs |
| Request retried | `youtube/analytics_api.py::_analytics_query()` | attempt number, HTTP status, classified reason (`server` or `quota`), delay |

`sync_pruning()` has no analogous skip warning: it deletes unconditionally against whatever channel-owned set it's given, with no truncation-based gate of its own (see [Video and playlist synchronization](#video-and-playlist-synchronization)).

Names and pagination tokens are both logged. A `nextPageToken` is an opaque result-set
cursor, not a credential, and logging it is what lets a reader tell a repeating token
apart from fresh tokens walking an empty region — the distinction between a genuine
pagination cycle and a large empty range. Titles come from the row already loaded by
`database.get_video()` or from the caller (`fetch_playlist_items()` takes
`playlist_title`, since the playlistItems response carries video titles rather than the
owning playlist's). The `UU…` uploads and `UUSH…` Shorts playlists have no API title at
all and are named `'Uploads'` and `'Shorts'`; the channel-wide playlist listing is named
`'Playlists'` and has no owner id.

A title is arbitrary YouTube-authored text, so it is always rendered last in the record
and `repr`-quoted — a title containing a newline or an `=` cannot then corrupt the
`key=value` fields ahead of it. Exception and response text stays excluded: failure
records carry only `logging_config.exception_context()` (see above), never an API error
body, which is where an OAuth token could actually appear.

Beyond the truncation/gap warnings above, `sync_videos()` and `sync_playlists()` emit no
further detail records; most of their work is already covered by the page records from
the `data_api.py` loops they call. `sync_pruning()` emits no records of its own at all —
its outcome is fully captured by its `sync_runs` row's `rows_deleted`. The generators'
date chunking emits no records — a chunk boundary is not an event a reader follows, and
the per-video row count already reports what those chunks produced.
