# Synchronization Reference

## Purpose

How data gets from the YouTube APIs into SQLite: plan validation, stage order, startup freshness, scope semantics, and the caveats that affect data freshness/correctness. Database-side query/aggregation semantics live in `database.md`; this file covers ingestion only.

## Authoritative source files

- `backend/sync/plans.py`, `backend/sync/status.py`, `backend/sync/orchestration.py`, `backend/sync/stages.py`, `backend/sync/scheduler.py`, `backend/sync/monthly_insights.py`, `backend/sync/coverage.py`
- `backend/youtube/auth.py`, `backend/youtube/data_api.py`, `backend/youtube/analytics_api.py`
- `backend/logging_config.py` (shared logging configuration used by `orchestration.py`, `stages.py`, `data_api.py`, `analytics_api.py`)
- `backend/database/` (sync-run helpers only: `create_sync_run`/`complete_sync_run`/`fail_sync_run`/`cancel_sync_run`/`get_sync_runs`/`mark_incomplete_sync_runs`/`get_last_successful_run_completed_at` in `sync_runs.py`, `get_covered_periods`/`upsert_coverage` in `sync_coverage.py` (see `database.md`), `get_last_fx_rate` in `fx_rates.py`, `get_owned_video_ids`/`get_all_video_ids`/`upsert_own_video`/`upsert_related_video` in `videos.py`, `upsert_search_terms` in `search_terms.py`, `upsert_related_videos` in `related_videos.py`)

## Contents

- [Pipeline overview](#pipeline-overview)
- [Sync plans and validation](#sync-plans-and-validation)
- [Analytics API worker split](#analytics-api-worker-split)
- [Startup freshness and state](#startup-freshness-and-state)
- [Cooperative cancellation checkpoints](#cooperative-cancellation-checkpoints)
- [Scope behavior](#scope-behavior)
- [Stage tracking](#stage-tracking)
- [Video and playlist synchronization](#video-and-playlist-synchronization)
- [Comment synchronization](#comment-synchronization)
- [Shared monthly coverage selection](#shared-monthly-coverage-selection)
- [Prefiltered worklist (effective range end)](#prefiltered-worklist-effective-range-end)
- [Analytics synchronization](#analytics-synchronization)
- [Traffic-source synchronization](#traffic-source-synchronization)
- [FX-rate synchronization](#fx-rate-synchronization)
- [Search insights synchronization](#search-insights-synchronization)
- [Related video insights synchronization](#related-video-insights-synchronization)
- [YouTube API requests and pagination](#youtube-api-requests-and-pagination)
- [Pagination termination](#pagination-termination)
- [Authentication](#authentication)
- [Sync logging](#sync-logging)

## Pipeline overview

A sync runs an explicit **plan**: a set of selected stages, always executed in the canonical order defined by `STAGE_ORDER` (`sync/plans.py`), regardless of the order the stages were submitted in. `STAGE_ORDER` is `PRE_ANALYTICS_STAGES + ANALYTICS_STAGES`:

```
playlists → videos → pruning → fx_rates → comments   (PRE_ANALYTICS_STAGES, serial)
video_analytics, video_traffic_sources, search_insights, related_video_insights   (ANALYTICS_STAGES, up to two workers)
```

The selected `PRE_ANALYTICS_STAGES` run one after another, in that order, on the plan's own thread. Only once every selected pre-analytics stage has succeeded does the plan move on to the selected `ANALYTICS_STAGES`, which run on at most two independent worker threads (see [Analytics API worker split](#analytics-api-worker-split)). An analytics-only plan (no pre-analytics stage selected) skips straight to the workers, using whatever video list is already stored — it neither requires nor triggers discovery.

`pruning` sits ahead of `comments` deliberately: a video that pruning is about to delete is never fetched for comments in the same plan. `comments` reads the video rows `videos` wrote, and runs against whatever survives pruning.

`search_insights` and `related_video_insights` share no dependency with `video_traffic_sources`, or with each other — canonical order only controls their placement (and worker assignment) when more than one happens to be selected in the same plan; selecting or deselecting any one of them never affects the others. See [Search insights synchronization](#search-insights-synchronization) and [Related video insights synchronization](#related-video-insights-synchronization).

`pruning` is the only stage that deletes video rows. It is opt-in: `validate_plan()` rejects any plan that names it without also naming both `playlists` and `videos` (`STAGES_REQUIRING_PLAYLISTS_AND_VIDEOS`, `sync/plans.py`), and it is excluded from the startup plan (`DESTRUCTIVE_STAGES`, `sync/plans.py`; see [Startup freshness and state](#startup-freshness-and-state)).

`execute_plan()` (`sync/orchestration.py`) runs the selected `PRE_ANALYTICS_STAGES` serially and fail-fast, then — once they all succeed — hands the selected `ANALYTICS_STAGES` to `allocate_analytics_workers()` and runs the resulting queues concurrently. Every started stage, on either path, is wrapped by `_run_tracked_stage()` → `_run_stage()` and recorded as its own `sync_runs` row; every row from one plan shares one `batch_id` (a UUID generated once per plan). Omitted stages get **no** row — there are no placeholder records. The serial stages are fail-fast: a failing pre-analytics stage is recorded with its partial counters, and the stages after it (including every Analytics API stage) neither run nor create rows — this is also what guarantees `pruning` can never run after a `playlists` or `videos` failure. Once the Analytics API phase has started, failure isolation switches to a per-worker basis — see [Analytics API worker split](#analytics-api-worker-split).

The stage implementations themselves (`sync_videos`, `sync_playlists`, `sync_comments`, `sync_pruning`, `sync_video_analytics`, `sync_video_traffic_sources`, `sync_search_insights`, `sync_related_video_insights`, `sync_fx_rates`) live in `sync/stages.py`. `_run_tracked_stage()` (`sync/orchestration.py`) looks up each stage's initial progress message in `_STAGE_MESSAGES` and publishes it via `status.update_sync_progress(stage_key, message)`, keyed by that stage's own name; `playlists`/`videos`/`pruning` additionally thread plan-local video-ID sets between each other (see [Video and playlist synchronization](#video-and-playlist-synchronization)) via accessor callables built by `_pre_analytics_runner()`. `comments`, `video_analytics`, `video_traffic_sources`, `search_insights`, and `related_video_insights` have no entry in `_STAGE_MESSAGES` (`None`) since they report their own per-unit progress from inside their loop via that same keyed `update_sync_progress()` call — each stage function hardcodes its own stage-name key, since each stage function corresponds to exactly one stage.

Two entry points wrap the executor:

- `execute_plan(stages)` — runs a plan whose active-state reservation the caller **already holds**. Used by `POST /sync/trigger`, which reserves before responding.
- `run_plan(stages)` (`sync/orchestration.py`) — acquires the reservation itself and returns `False` if a sync is already active. Used by the startup sync.

Calling `execute_plan` from an unreserved caller leaves the sync unguarded; calling `run_plan` from a caller that already reserved would be blocked by its own reservation. The split exists for exactly that reason.

## Sync plans and validation

`sync/plans.py` owns the plan vocabulary. Constants: `PRE_ANALYTICS_STAGES` (`playlists`, `videos`, `pruning`, `fx_rates`, `comments`, in execution order), `ANALYTICS_STAGES` (`video_analytics`, `video_traffic_sources`, `search_insights`, `related_video_insights`), `STAGE_ORDER` (`PRE_ANALYTICS_STAGES + ANALYTICS_STAGES`, the canonical order), `FAST_ANALYTICS_STAGES`/`SLOW_ANALYTICS_STAGES` (the issue's Analytics API scheduling-priority groups; see [Analytics API worker split](#analytics-api-worker-split)), `DESTRUCTIVE_STAGES` (just `pruning`; excluded from `full_incremental_plan()`), `PERIOD_AWARE_STAGES` (`video_analytics`, `video_traffic_sources`, `search_insights`, and `related_video_insights`), `SCOPE_AWARE_STAGES` (just `comments`), `STAGES_REQUIRING_PLAYLISTS_AND_VIDEOS` (just `pruning`), `SCOPES`, `SCOPE_AWARE_SCOPES` (`incremental` and `all`), and `FULL_SYNC_TYPES`, which is *derived from* `STAGE_ORDER` so the execution order and the complete-batch definition cannot drift.

A scope-aware stage picks how far back to scan but has no per-year view, so it accepts a `scope` and never a `year`. `comments` walks each video's threads newest-first until it hits a boundary rather than over a date range, which is what makes a single year unrequestable — reaching one would mean reading everything newer than it anyway.

`PlanStage` (`sync/plans.py`) is a frozen dataclass of `stage`, `scope`, `year`. `scope`/`year` stay `None` for the always-incremental stages, which keeps `validate_plan()` idempotent — a validated plan revalidates cleanly rather than being rejected for carrying a scope it should not.

`validate_plan(stages)` (`sync/plans.py`) returns the stages in canonical order and raises `PlanValidationError` when:

- the plan is empty;
- a stage appears more than once;
- a stage name is not in `STAGE_ORDER`;
- a period-aware stage omits `scope`, or names a scope outside `SCOPES`;
- `scope="year"` without a `year`, or a `year` supplied with `incremental`/`all`;
- a scope-aware stage names a scope outside `SCOPE_AWARE_SCOPES`, or carries a `year` at all — including `scope="year"`, which is not one of its two scopes. An omitted scope is not an error there: it means the `incremental` default;
- a `scope` or `year` is attached to `videos`, `playlists`, `pruning`, or `fx_rates`;
- the requested year is outside `available_years()`;
- `pruning` is named without both `playlists` and `videos` also in the plan.

`available_years()` (`sync/plans.py`) spans `database.get_earliest_published_year()` through the current year, newest first. It returns an **empty tuple** when no videos have been synced yet, in which case every year-scoped plan is rejected; `incremental` and `all` plans stay valid.

`execute_plan()` revalidates its input rather than trusting the caller, so no code path can drive the stage loop with an unchecked plan. `full_incremental_plan()` builds the eight-stage **non-destructive** startup plan — every canonical stage except `pruning` — used by the startup sync. Period-aware and scope-aware stages, `search_insights` and `related_video_insights` included, are entered at `incremental`, so an unattended run never triggers a full-history comment scan or a full-history/year Search or Related Video backfill (see [Search insights synchronization](#search-insights-synchronization) and [Related video insights synchronization](#related-video-insights-synchronization)).

## Analytics API worker split

Once every selected `PRE_ANALYTICS_STAGES` stage has succeeded (or immediately, for an analytics-only plan), `execute_plan()` (`sync/orchestration.py`) passes the plan's selected `ANALYTICS_STAGES` to `allocate_analytics_workers()` (`sync/plans.py`), which deterministically splits them across at most two workers, and runs each non-empty queue on its own `threading.Thread`. Each worker runs its own queue sequentially, in the order `allocate_analytics_workers()` returned; the two threads otherwise run independently of each other. `execute_plan()` joins every started worker thread before deciding the plan's terminal outcome — the reservation is held, and `/sync/status` keeps reporting `running`, until both workers have exited, however long the slower one takes.

`allocate_analytics_workers()` is a pure function of which stages were selected — never submission order, never a measured or estimated duration. It groups `video_analytics` and `video_traffic_sources` as the issue's **faster** scheduling-priority stages, and `search_insights` and `related_video_insights` as the **slower** group (`FAST_ANALYTICS_STAGES`/`SLOW_ANALYTICS_STAGES`, `sync/plans.py`) — a comparative ranking the issue specifies, not a benchmark: no elapsed time, ratio, or fastest-sync baseline is computed or implied, and the serial pre-analytics stages (`PRE_ANALYTICS_STAGES`: `playlists`, `videos`, `pruning`, `fx_rates`, `comments`) are outside this ranking entirely — including `fx_rates` (Yahoo Finance, not the YouTube Data API) and `pruning` (a local delete, no API call at all). Within a worker's own queue, a fast stage always precedes a slow one. The full distribution:

| Selected stages | Worker A | Worker B |
|---|---|---|
| One stage | Selected stage | Idle |
| Two fast | Fast | Fast |
| Two slow | Slow | Slow |
| One fast, one slow | Fast | Slow |
| Two fast, one slow | Fast → slow | Fast |
| One fast, two slow | Fast → slow | Slow |
| Two fast, two slow (all four) | video_analytics → search_insights | video_traffic_sources → related_video_insights |

Related-video metadata resolution stays inside `sync_related_video_insights()`'s own Analytics API stage — it is never split out as a separate stage or worker (see [Related video insights synchronization](#related-video-insights-synchronization)).

**Failure isolation.** `_run_analytics_worker()` (`sync/orchestration.py`) runs one worker's queue via the shared `_run_tracked_stage()` helper. A genuine exception in one stage stops only that worker's own remaining queued stages — recorded via `outcome.failed_stages` — while the other worker keeps running its queue to completion or its own first failure, unaffected. Only after both workers have been joined does `execute_plan()` decide the plan-level outcome, with this priority: any genuine stage failure on either worker → `failed`, naming every failed stage (`_multi_failure_message()`, stages listed in canonical `ANALYTICS_STAGES` order regardless of which worker or order they actually failed in); otherwise, an accepted Stop on either worker → `cancelled`; otherwise → `success`. A Stop request reaches both workers independently through the same `status.raise_if_stopping()` checkpoint each worker checks before starting its next queued stage — it is not special-cased per worker.

**Live status message.** While more than one stage can be active at once, `sync/status.py` tracks each active stage's progress text under its own key (`_stage_progress`, keyed by stage name) instead of a single shared string, so one worker's `update_sync_progress()` call can never clobber the other's. The public `/sync/status` `message` field is the combination of every currently active stage's own text, in the order each was registered, with any already-failed stage's fixed label appended as `"<label> failed"` — visible alongside the other worker's continuing progress rather than replaced by it. `/sync/status` also exposes that same set of entries unjoined, as `stages: [{key, message}]` — one entry per currently active or just-failed stage, each carrying its own untruncated text — so a consumer like the navbar can render concurrent stages as separate items instead of parsing the combined string; `stages` is `[]` outside `state="running"`. `status.end_stage(key)` removes a stage's entry on success or cancellation; `status.fail_stage(key, label)` replaces it with the fixed label, which stays visible until the plan's terminal transition (which overwrites the whole message and empties `stages`) or the next `try_begin_sync()` reservation (which clears both `_stage_progress` and `_stage_failures`).

**Concurrent OAuth.** Each worker's stage functions build their own YouTube API clients, each independently calling `youtube/auth.py`'s `get_credentials()`. A module-level `threading.Lock` (`auth._credentials_lock`) serializes the whole read/refresh/write sequence, so two workers starting at the same moment never both read a near-expired token, both refresh it, and race to write `token.json` — the second caller simply waits for the first to finish and then observes the now-valid, already-refreshed credentials. Token format and refresh/re-auth behavior are otherwise unchanged (see [Authentication](#authentication)).

**Concurrent SQLite writes.** Each stage function opens its own connection per `database` helper call (WAL mode, a busy timeout) exactly as it does when run serially; no additional locking was needed for the sync-runs bookkeeping itself; two workers writing their own `sync_runs` rows under the same shared `batch_id` at the same time is exactly the scenario the existing per-call-connection model already supports.

## Startup freshness and state

- `start_background_scheduler()` (`sync/scheduler.py:30-44`), called once from `server.py`'s lifespan, runs **one** non-destructive incremental sync (`full_incremental_plan()`, which excludes `pruning`) on a daemon thread unless `synced_today()` is already true. There is no recurring timer: the app is not expected to stay running long enough for one to fire, so freshness is decided per launch. Pruning is never selected automatically at any freshness check — it is manual-only.
- `synced_today()` (`sync/scheduler.py:12-27`) calls `database.get_last_successful_run_completed_at()` and compares its local calendar date against today. A missing or unparseable timestamp counts as not-synced. Restarting the backend after any successful sync on the same local date therefore does nothing.
- There is no separate persisted checkpoint — `sync_runs` is the sole source of truth. Any single succeeded run qualifies: its `sync_type`, scope, and `batch_id` do not matter, and other stages in the same batch may have failed or never run. The query matches `status = 'success'` alone, so failed, still-running, and startup-swept `incomplete` rows are all ignored.
- A selective manual sync therefore suppresses that day's startup sync. Manually syncing one stage — even just `fx_rates` — marks the day as synced, and the next launch runs nothing. A day on which every run failed still counts as not-synced, so the next launch retries.
- `get_sync_status()` (`sync/status.py`) exposes `{state, message, stages}` guarded by a module-level `threading.Lock`, where `state` is one of `idle | running | stopping | success | failed | cancelled` — safe to poll from any thread; see [Live status message](#analytics-api-worker-split) above for `stages`. All mutation of that shared state is centralized in `sync/status.py` behind `try_begin_sync()`, `update_sync_progress()`, `end_stage()`, `fail_stage()`, `request_stop()`, `raise_if_stopping()`, `complete_sync()`, `fail_sync()`, `cancel_sync()`, and `reset_sync_status()`.
- `try_begin_sync(message="")` (`sync/status.py`) sets `state="running"` **and** the initial message under one lock acquisition, so a status poll can never observe the running state still carrying the previous run's terminal message. It also clears `_stage_progress`/`_stage_failures` (see [Analytics API worker split](#analytics-api-worker-split)), so a new plan never inherits a previous plan's per-stage entries. It rejects reservation while `state` is `running` **or** `stopping`, so a stop request blocks a new sync from starting until the stopping worker actually exits. It is the single reservation primitive: the manual route calls it before responding, and `run_plan()` calls it for the startup sync. Whichever loses the race gets `False` — the route turns that into `409`, the startup sync silently declines. A successful reservation replaces any retained terminal result (`success`/`failed`/`cancelled`) from the previous run.
- `update_sync_progress(stage_key, message)` is a no-op unless `state="running"`, so a stray call cannot fabricate a running state and cannot overwrite the `stopping` message once cancellation has been requested. `stage_key` scopes the update to one stage's entry, so two stages active at once (the two Analytics API workers) never clobber each other's text — see [Analytics API worker split](#analytics-api-worker-split) for how `end_stage()`/`fail_stage()` and the combined message work.
- `request_stop()` (`sync/status.py`) is the cooperative-cancellation entry point behind `POST /sync/stop`. Under the same lock: `running → stopping` (message set to `"Stopping sync..."`) returns `True`; already `stopping` returns `True` without mutation (idempotent); `idle` or any terminal state returns `False` — reporting no active sync — without mutating a result that may have just been recorded by the competing worker.
- `raise_if_stopping()` (`sync/status.py`) is the checkpoint primitive: a no-op while `state != "stopping"`, otherwise raises the internal `SyncCancelled` exception. Every long-running loop in `sync/stages.py` and the paginated/retrying YouTube API helpers calls it between safe units of work — never inside an in-flight HTTP request, a retry `time.sleep()`, or a SQLite statement/transaction — so a stop request is observed within one unit's latency, not the rest of the plan. See [Cooperative cancellation checkpoints](#cooperative-cancellation-checkpoints).
- `execute_plan()` transitions to exactly one terminal state: `complete_sync("Sync complete")` on success, `cancel_sync("Sync stopped")` when a `SyncCancelled` unwinds to the plan level (caught before the generic exception handler, so it is never treated as failure and never re-raised), or `fail_sync(...)` with a fixed, safe, operation-specific message on any other exception (plan validation or any stage) before re-raising. There is no separate "finish"/cleanup step: the terminal transition itself is what ends the running/stopping state, so failed, cancelled, and invalid runs cannot leave the app permanently "syncing". `complete_sync()` is a no-op while `state="stopping"` or already terminal — so a plan that finishes its last unit of work after a stop was requested, but before its next checkpoint, still resolves to whichever the checkpoint sees first; `fail_sync()`/`cancel_sync()` are no-ops only once a terminal result is already recorded, so a genuine error during the stopping window still fails the sync. Terminal state (`success`/`failed`/`cancelled`) is retained until the next reservation.
- Public failure text never includes exception content, headers, credentials, tokens, or API response bodies — see [Sync logging](#sync-logging) for how the same constraint applies to log records. `_STAGE_FAILURE_LABELS` (`sync/orchestration.py`) maps each stage to a fixed label (e.g. `"syncing videos"`) used to build `"Sync failed while syncing videos"`; a failure before any stage starts (plan validation) reports `"Sync failed during plan validation"`. Terminal messages carry no trailing period; in-progress messages keep their trailing `...`. Raw exception text still reaches `sync_runs.error_message` via `fail_sync_run()` and safe exception context still reaches the sync logger, unchanged. Cancellation carries no exception text at all — `cancel_sync_run()` leaves `error_message` `NULL` and `_run_stage()` logs it at `INFO`, not `ERROR`.

## Cooperative cancellation checkpoints

`POST /sync/stop` (see `api.md`) calls `status.request_stop()` to flip `running → stopping`. Cancellation is cooperative: nothing preempts an in-flight request or database write. Instead, `status.raise_if_stopping()` is threaded down as an optional `checkpoint` callback and invoked at hand-picked safe boundaries — never mid-request, mid-sleep, or mid-transaction:

- `sync/orchestration.py`'s `execute_plan()` checks before each pre-analytics stage's row is created, once more before entering the Analytics API phase, and once more before the final `complete_sync()` call. `_run_analytics_worker()` checks before dispatching each of its own queued stages — independently per worker, so a Stop reaches both workers at their own next queued-stage boundary regardless of what the other is doing.
- `sync/stages.py` checks between videos/playlists/comments/requests/months/batches in every stage's own loop (including before advancing `sync_coverage` after each Video Analytics/Traffic Sources request — see [Shared monthly coverage selection](#shared-monthly-coverage-selection)), and immediately before the pruning delete and each FX-rate day.
- `youtube/data_api.py`'s paginated fetchers (`fetch_all_video_ids`, `fetch_shorts_video_ids`, `fetch_playlists`, `fetch_playlist_items`, `iter_comment_threads`) accept an optional `checkpoint` parameter (default: a no-op, for callers outside sync) invoked before requesting each page after the first.
- `youtube/analytics_api.py`'s `_analytics_query()` invokes its `checkpoint` after a retry's backoff sleep returns and before the next attempt; `_fetch_analytics_rows()` invokes it before requesting each page after the first and forwards it into `_analytics_query()`; `iter_video_analytics()`/`iter_video_traffic_sources()` invoke it before each year-chunk after the first; `fetch_video_search_terms()`/`fetch_video_related_videos()` forward it through to their own `_analytics_query()` call.

When a checkpoint raises `SyncCancelled`, `_run_stage()` (`sync/orchestration.py`) catches it ahead of the generic exception handler, persists the active stage via `database.cancel_sync_run()` with its partial counters, logs it at `INFO` (not `ERROR`), and re-raises. On the serial pre-analytics path this unwinds straight to `execute_plan()`'s own handler, which records the plan-level `cancelled` terminal state. On the Analytics API path, `_run_tracked_stage()` re-raises it out of `_run_stage()` to `_run_analytics_worker()`, which marks that worker's own `outcome.cancelled = True` and returns — stopping only that worker's queue; `execute_plan()` decides the plan-level terminal state only after joining both workers (see [Analytics API worker split](#analytics-api-worker-split)). Either way, stages that already completed keep their `success` rows; stages after the cancelled one never start and get no row — identical to the fail-fast behavior on a genuine exception, except the terminal state and log severity differ.

## Scope behavior

Scopes are per-stage, not per-sync: `video_analytics`, `video_traffic_sources`, and `comments` each carry their own scope and can differ within one plan (e.g. analytics for `2024` alongside a full-history traffic-source refetch).

- `scope`/`year` affect `sync_video_analytics`, `sync_video_traffic_sources`, `sync_search_insights`, and `sync_related_video_insights`; `scope` alone also affects `sync_comments` (`sync/stages.py`). Videos, playlists, and pruning always sync incrementally (or, for pruning, run once against current state) and must not be given a scope at all — `validate_plan()` rejects a plan that tries. FX rates likewise takes no scope — it always resumes from its own last stored date (see [FX-rate synchronization](#fx-rate-synchronization)).
- `"incremental"`: for the four Analytics API stages, find every calendar month not yet marked complete in `sync_coverage` and always re-check the previous/current month pair regardless of coverage (see [Shared monthly coverage selection](#shared-monthly-coverage-selection)); for `comments`, stop at each video's own boundary (see [Comment synchronization](#comment-synchronization)).
- `"year"`: refetch the given calendar year for every video, ignoring `sync_coverage` for selection (but still updating it — see below), clamped to `[publish_date, yesterday]`. Period-aware stages only.
- `"all"`: refetch each video's entire history (`publish_date` → yesterday) for the analytics stages, ignoring `sync_coverage` for selection (but still updating it — see below); for `comments`, re-read every page of every stored video. Labelled **All** in the Sync page's Comments row.

## Stage tracking

- `SyncCounts` (`sync/stages.py:20-25`) is a mutable dataclass (`rows_fetched`, `rows_written`, `rows_deleted`) accumulated incrementally *as rows are processed inside each stage's loop* — not computed from a return value at the end. If a stage raises partway through (e.g. video 200 of 378), the `sync_runs` row for that stage still reflects accurate partial totals, not zeros. It's defined in `sync/stages.py` since that's what the stage functions mutate directly; `sync/orchestration.py` imports it only to construct a fresh instance per stage.
- `_run_stage()` (`sync/orchestration.py`) always re-raises the underlying exception after recording failure via `fail_sync_run()`. On the serial pre-analytics path, `execute_plan()`'s enclosing `except` runs its `fail_sync()` transition and the exception propagates to the caller. On the Analytics API path, `_run_tracked_stage()` and `_run_analytics_worker()` catch it instead — see [Analytics API worker split](#analytics-api-worker-split). It also logs that stage's start, completion, and failure — see [Sync logging](#sync-logging).
- For `videos`/`playlists`/`pruning`/`fx_rates`, `sync_runs.scope` is always `"incremental"` and `year` is `NULL`. For `video_analytics`/`video_traffic_sources`/`search_insights`/`related_video_insights`, `scope`/`year` reflect that stage's own plan entry. For `comments`, `scope` reflects its plan entry (defaulting to `"incremental"` when omitted) and `year` is always `NULL`. `recorded_scope()`/`recorded_year()` (`sync/plans.py`) derive both values, so a non-period stage can never record a scope it was not run with.
- `pruning` gets its own `sync_runs` row and its own `rows_deleted` count, independent of `videos`'/`playlists`' counts — it is the only stage that writes to `rows_deleted` for video rows.
- The playlists stage's `rows_deleted` sums `delete_playlist_items()`'s return value across every playlist in the loop (items are deleted and fully re-inserted on every sync, `sync/stages.py:226`) plus `delete_playlists_not_in()`'s return value (`sync/stages.py:238`) — cascaded FK deletes (e.g. `video_analytics` rows removed because their parent video was deleted) are not counted, since those helpers only report `cursor.rowcount` for the row they directly targeted.

## Video and playlist synchronization

Video deletion and video/playlist discovery are separate stages. `playlists` and `videos` only fetch and upsert; only `pruning` deletes video rows. This split exists so a plan can safely refresh video/playlist data without any risk of deleting anything — pruning has to be selected deliberately.

- `sync_playlists()` (`sync/stages.py:183-250`): fetches all playlists and their items, upserts them, then deletes any DB playlist not returned by the API (cascades to `playlist_items`). Its item replace is delete-then-reinsert per playlist, gated on that playlist's own item pagination completing (leaving stored items untouched otherwise); the listing-level reconcile (`delete_playlists_not_in()`) is gated on the playlist *listing* itself completing. Both gates emit a `WARNING` naming `reason=pagination_truncated` when they skip. It also collects every non-null `video_id` referenced by any playlist item — regardless of that playlist's own truncation state, since a partial page set is still real, known membership — and returns that set for `sync_videos()` to combine with the uploads-playlist IDs.
- `sync_videos()` (`sync/stages.py:113-180`): calls `fetch_channel_identity()` to get the authenticated channel's ID and uploads-playlist ID, fetches the Shorts video-ID set (via UUSH) and the full uploads-playlist ID list, then fetches details (batches of 50, the Data API's per-request ID limit) for the **union** of the uploads IDs and the playlist-discovered candidates passed in from `sync_playlists()`. Every uploads ID is treated as channel-owned outright; a playlist-only candidate is upserted only when its returned `snippet.channelId` matches the authenticated channel — this ownership check is what stops a video from someone else's playlist being imported as if it were this channel's. It never deletes. It returns the full channel-owned ID set (every uploads ID, even one `videos.list` didn't return details for, plus every ownership-confirmed playlist-only ID) for `sync_pruning()` to use as its retain set.
- `sync_pruning()` (`sync/stages.py:328-332`): the sole stage that deletes video rows (cascades to `video_analytics`/`video_traffic_sources`). Calls `database.delete_videos_not_in()` unconditionally with the channel-owned ID set built by `sync_playlists()` + `sync_videos()` in the same plan — there is no truncation-based safety gate on pruning itself; canonical stage ordering and `validate_plan()`'s `playlists`+`videos` dependency are what keep it from ever running without that set populated. An empty set deletes every video (`database/videos.py::delete_videos_not_in()` has no empty-list guard) — correct only when the channel genuinely has zero owned videos, which is why pruning is manual-only and never part of the startup plan.
- The uploads playlist is how the Data API enumerates a channel's videos — there is no channel-wide video listing endpoint — so `fetch_all_video_ids()`'s result is one of the two authorities pruning's retain set is built from (the other being playlist membership, for videos the uploads enumeration might otherwise miss).
- `sync_video_analytics()`, `sync_video_traffic_sources()`, and `sync_fx_rates()` only ever upsert; analytics and traffic-source rows are removed exclusively by cascade from a pruning-triggered video deletion. Their writes are idempotent, so a short fetch there is self-healing on the next run and needs no gate.

## Comment synchronization

`sync_comments(scope, counts)` (`sync/stages.py`) imports top-level comments and their commenters for videos **already stored in SQLite**. Reply bodies are never requested or stored; only `total_reply_count` is kept as thread metadata.

- Its worklist is `database.get_owned_video_ids()` and nothing else. The stage makes no channel, uploads-playlist, search, or `videos.list` call of its own — an owned video missing from `videos` simply has no comments imported until the `videos` stage adds it, and an external (`own=0`) video written only as a Related referrer's metadata is never a comment target. This is also why it runs directly after `videos`.
- Per video it walks `youtube.iter_comment_threads(video_id, title=...)`, which requests `commentThreads.list` with `part="snippet"`, `order="time"`, `textFormat="plainText"`, and `maxResults=COMMENT_THREADS_PAGE_SIZE` (100, the API maximum). `part="snippet"` is what omits the optional `replies` part while still returning `snippet.totalReplyCount`. The generator requests the next page only once the consumer has worked through the current one, so stopping early spends no further quota.
- **`"incremental"`** bounds each video independently:
  - A video that already has stored comments is read until the first comment ID already held locally, then `COMMENT_INCREMENTAL_OVERLAP` further comments (`sync/stages.py`, set to one maximum-size page) before stopping. The overlap costs no extra request and catches edits and late arrivals just behind the boundary.
  - A video with no stored comments is read back to `_comment_bootstrap_cutoff()` — January 1 of the current year minus one calendar month, i.e. December 1 of the previous year, inclusive. It is recomputed from the local date per run, so the window rolls forward with the calendar rather than being pinned to when the feature was installed.
  - Because the boundary is per video, a first run that failed part-way resumes correctly: populated videos use their boundary, untouched ones the cutoff. Neither case escalates itself to a full-history scan.
  - A video that has stored comments but whose boundary never appears — every stored comment since deleted upstream — reads to the end rather than stopping short of history it may still be missing.
- **`"all"`** ignores both bounds and re-reads every page of every stored video, refreshing like counts, reply counts, and edited text across the full history.
- Both scopes only insert and update. A comment deleted on YouTube keeps its stored row; nothing in this stage infers a deletion from a comment's absence, which is also why the paginator's `truncated` signal is logged here and not acted on. The only deletions are `database.delete_orphan_comment_authors()` at the end of the stage, whose count lands in `rows_deleted` (see `database.md`).
- Each thread's author is upserted before its comment, since `comments.author_id` is a non-null FK. Both writes count toward `rows_written`, matching the playlists stage's convention of counting every directly written row. `rows_fetched` counts every returned thread, including the boundary item inspected to decide to stop, which is one more than the number written.
- Failures are isolated at two levels. A malformed individual thread is skipped by the fetcher; a per-item author/comment write failure is caught, logged, and the walk continues. A video whose comments are disabled or that has disappeared from YouTube yields nothing and is logged, and the stage moves to the next video — that decision is made on the Data API's machine-readable error reason (`commentsDisabled`, `videoNotFound`), not the HTTP status, so `quotaExceeded` (also a 403) still propagates and fails the stage rather than silently skipping every remaining video.

## Shared monthly coverage selection

All four Analytics API stages (`video_analytics`, `video_traffic_sources`, `search_insights`, `related_video_insights`) resume from `sync_coverage` (`database/sync_coverage.py`, see `database.md`) instead of a reporting-table `MAX(date)`/`MAX(month)` — a successful response with zero reportable rows (e.g. a video with no views that month) leaves no reporting row, so a reporting-derived checkpoint cannot tell "not checked yet" from "checked and genuinely empty." Coverage is tracked by calendar month for all four collectors, even though Video Analytics/Traffic Sources still request date ranges spanning many months per call (see [YouTube API requests and pagination](#youtube-api-requests-and-pagination)) — what gets *marked done* and what gets *requested* are independent granularities.

`_incremental_monthly_windows(collector, video_id, publish_date, yesterday, forced)` (`sync/stages.py`) is the one helper all four stages' `"incremental"` selection calls, so they can't drift apart:

1. Generate every calendar month from `publish_date` through `yesterday` via `monthly_insights.monthly_windows_for_range()`.
2. Read `database.get_covered_periods(collector, video_id, ...)` and drop every month already covered, via `sync/coverage.py`'s pure `missing_windows()`.
3. Union in whichever months of `forced` (the previous/current pair from `monthly_insights.monthly_search_windows(today)`) are within this video's eligible range — re-checking them even when already covered, since a just-finished or in-progress month's metrics are not fully settled by the API yet. A month already present from step 2 is not added twice.
4. Rebuild the result by filtering the original step-1 list (not by concatenating steps 2 and 3), so the output stays chronologically ordered even when a forced month sorts earlier than a genuine gap — required for `search_insights`/`related_video_insights` (whose months become independent API calls in order) and, more importantly, for `coalesce_missing_windows()` (step below) to merge adjacent months correctly.

`video_analytics`/`video_traffic_sources` additionally coalesce that list into as few date ranges as possible via `sync/coverage.py`'s `coalesce_missing_windows()`, since one API call can span many months (see [Analytics synchronization](#analytics-synchronization)); `search_insights`/`related_video_insights` use the list as-is, one API call per month (the Search Analytics detail report cannot be requested across multiple months in one call — see [Search insights synchronization](#search-insights-synchronization)).

Coverage is written only after a request's fetch **and** reporting upsert both succeed — a failed or cancelled request leaves its months uncovered, so a later Incremental run resumes there rather than restarting already-successful work. In steady state (a video synced every run) this leaves nothing for the coverage-diff step to find, since each month already got marked complete when it was the "current" or "previous" month; the diff only produces work for a genuine backlog — first sync, or a gap left by missed runs. `"year"`/`"all"` ignore `sync_coverage` for selection (as before) but still mark every month their own scoped range actually spans as complete once each request succeeds — including a still-open trailing month, which is harmless: nothing treats "already covered" as a reason to skip the forced previous/current pair, and by the time a later Incremental's coverage-diff would ever consult that same month again, it has genuinely finished.

An existing database populates `sync_coverage` via the standalone `backend/scripts/issue-62-migration.py` (see `database.md`); a fresh database simply starts with no coverage rows, which Incremental treats as a backlog to fill from scratch like any other gap.

## Prefiltered worklist (effective range end)

`_effective_range_end(scope, year, yesterday)` (`sync/stages.py`) is the single helper the four period-aware stages — `sync_video_analytics`, `sync_video_traffic_sources`, `sync_search_insights`, `sync_related_video_insights` — call to compute one inclusive upper bound on the request range for the whole stage: `min(yesterday, date(year, 12, 31))` for `scope="year"`, otherwise `yesterday` itself for `"incremental"`/`"all"`. It does not depend on any individual video.

Each of the four stages passes that date to `database.get_owned_video_ids(published_through=...)` (see `database.md`) **before** computing `total`, publishing any progress message, or reading a single video's metadata or checkpoint. A video whose known `published_at` falls after that date is therefore excluded from the worklist snapshot itself: it makes no `get_owned_video()` lookup, no YouTube API call, is not counted in `total` or any `i/total` ordinal, and emits no per-video `DEBUG` record for that stage. A video with no known `published_at` is never excluded by this filter (see `database.md`) — it still reaches the per-video loop and is handled by that stage's own no-publish-date branch, unchanged.

This is a pure narrowing of the worklist, not a new correctness path: a video's actual fetch range is still computed independently inside the per-video loop from its own publish date and checkpoint, exactly as before. The defensive `empty_range` skip inside each analytics-style stage's loop (see below) is **not removed** — it still guards against inconsistent or corrupted checkpoint data (e.g. a stored last-synced date somehow after the stage's own range end) — but a video excluded purely for being published after the range end no longer reaches that branch at all; it is filtered out one step earlier, at worklist construction.

For `sync_related_video_insights` specifically, prefiltering composes with the stage's own one-time worklist snapshot: the (already filtered) ID list is still captured exactly once at stage start, so a referrer resolved into `videos` mid-run can never join the target worklist within that same run (see [Related video insights synchronization](#related-video-insights-synchronization)).

Comments has no period or year selection from the user, so `sync_comments` calls `get_owned_video_ids()` with no bound — an old video can always receive a new comment, so publication date cannot exclude it there.

## Analytics synchronization

`sync_video_analytics(scope, year, counts)` (`sync/stages.py`):

- The owned-video worklist is prefiltered by this stage's effective range end before `total` is computed or any progress/per-video work begins — see [Prefiltered worklist (effective range end)](#prefiltered-worklist-effective-range-end).
- Per video, `_video_period_requests("video_analytics", video_id, scope, year, today, end_date, publish_date)` (`sync/stages.py`) returns a list of `(start_date, end_date, months_to_mark)` requests:
  - `"incremental"`: `_incremental_monthly_windows()` (see [Shared monthly coverage selection](#shared-monthly-coverage-selection)) coalesced into as few date ranges as possible via `coverage.coalesce_missing_windows()` — a multi-year gap costs one request per contiguous run of missing months, not one per month, since `iter_video_analytics()` can service a many-month range in one call (internally chunked, see [YouTube API requests and pagination](#youtube-api-requests-and-pagination)).
  - `"year"`/`"all"`: the single existing scoped range (unchanged from before coverage), with `months_to_mark` set to every month it actually spans.
- If a video has no non-empty request at all (fully covered history plus no publish-date-eligible previous/current month), it's skipped entirely via `continue` — **zero API calls** for that video, logged once as `reason=empty_range`, not per request.
- For each request: the existing generator/reporting-upsert loop runs (`iter_video_analytics()` → `database.upsert_video_analytics()` per row), then — only after that request's fetch and every upsert succeed — `database.upsert_coverage("video_analytics", video_id, months_to_mark)` marks its months complete, including when the generator yielded zero rows for some or all of them. A fetch, pagination, upsert, or cancellation failure anywhere in a request leaves that request's months uncovered; earlier requests in the same video (or earlier videos) keep their coverage, so a later Incremental run resumes at the failure rather than restarting all successful work.
- Both `continue` branches (no publish date, empty range) and the per-video row count emit a sync-only `DEBUG` record — see [Sync logging](#sync-logging). A prefiltered-out video emits none of these; it never entered the loop.

## Traffic-source synchronization

`sync_video_traffic_sources(scope, year, counts)` (`sync/stages.py`):

- Same prefiltered-worklist behavior, same `_video_period_requests("video_traffic_sources", ...)` selection/coalescing, and the same per-request coverage-write-after-success behavior as analytics — see [Analytics synchronization](#analytics-synchronization) and [Shared monthly coverage selection](#shared-monthly-coverage-selection). The two stages track coverage under independent collector names (`video_analytics` vs. `video_traffic_sources`), so one's coverage can never hide the other's work.
- Same per-video `DEBUG` detail records as analytics — see [Sync logging](#sync-logging).

## FX-rate synchronization

`sync_fx_rates()` (`sync/stages.py:708-749`):

- Incremental from `get_last_fx_rate()["date"] + 1 day`; first run starts `2015-01-01`.
- Fetches `USDSGD=X` from Yahoo Finance via `yfinance` (imported **inside** the function, not at module scope).
- Weekends/holidays (days with no `yfinance` close) are forward-filled with the last known `carry` value.
- Logs one sync-only `DEBUG` record for the no-work early return, and one after the download loop reporting days written — see [Sync logging](#sync-logging).

## Search insights synchronization

`sync_search_insights(scope, year, counts)` (`sync/stages.py`) fetches and upserts monthly Search-source terms for every owned video, one API call per calendar month. It is period-aware, like `video_analytics`/`video_traffic_sources`.

- `scope="incremental"`, video has a `published_at`: `_incremental_monthly_windows("search_insights", video_id, publish_date, yesterday, incremental_windows)` (see [Shared monthly coverage selection](#shared-monthly-coverage-selection)) returns every uncovered month from `publish_date` through yesterday plus the previous/current pair, used directly as the month list — no coalescing, since each becomes its own API call regardless. A video whose history is fully covered collapses to exactly the previous+current pair, same as the original fixed behavior; a video whose backfill was interrupted partway (or that sat unsynced for a while) resumes filling every uncovered month in between rather than being wrongly treated as fully caught up just because it has *some* coverage.
- `scope="incremental"`, video has no `published_at`: falls back to the fixed current+previous window via `monthly_insights.monthly_search_windows(today)` (`sync/monthly_insights.py`, captured once via `date.today()` at the start of the stage so a midnight rollover mid-run cannot change this part of the worklist), since there is no date to compute a resume-from point. Real calendar arithmetic, not a 30-day approximation, so it handles leap February and January-to-December rollover correctly.
- `scope="year"`/`"all"`: `monthly_insights.monthly_windows_for_range(start, end)` returns one `MonthlyWindow` per calendar month in an arbitrary `[start, end]` range, clamping the first/last month's dates to the range boundaries — pure date arithmetic, no I/O. `start`/`end` are computed per video from its own `published_at`, the same way `video_analytics`/`video_traffic_sources` clamp their scopes (`scope="year"`: `max(publish_date, Jan 1)` through `min(yesterday, Dec 31)`; `scope="all"`: `publish_date` through yesterday). A video with no `published_at` is skipped at these two scopes, logged at `DEBUG`.
- The worklist is `database.get_owned_video_ids(published_through=...)`, prefiltered by this stage's effective range end before `total`/progress/per-video work begin — see [Prefiltered worklist (effective range end)](#prefiltered-worklist-effective-range-end). It is otherwise the same owned-only catalog `video_analytics`/`video_traffic_sources`/`related_video_insights` read — no separate discovery call.
- Each `MonthlyWindow` (any scope) is fetched with exactly one request: `youtube.fetch_video_search_terms(video_id, window.start_date, window.end_date)` (`youtube/analytics_api.py`) — `dimensions=insightTrafficSourceDetail`, `metrics=views`, `filters=video==<id>;insightTrafficSourceType==YT_SEARCH`, `sort=-views`, `maxResults=25`, `startIndex` omitted entirely. The Search Analytics detail report hard-caps each request's result set at 25 rows total with **no pagination past it** — verified live against the production API (`search-insights-api-findings.md`): `maxResults>25` and any `startIndex` reaching row 26 both return HTTP 500, not a normal next page. A video whose real search traffic spans more than 25 distinct terms in a month loses everything past the cap; the API supports narrowing each request to a week to raise how much of a month's real traffic gets captured, but that costs roughly 4x the calls for a small coverage gain dominated by low-view long-tail terms (see search-insights-api-findings.md's "Window size" table), so this stage stays at one call per month. The response's terms pass straight through to one `database.upsert_search_terms(video_id, window.month, result.terms)` call per month (see `database.md`); once that upsert succeeds, `database.upsert_coverage("search_insights", video_id, [window.month])` marks the month complete, even when zero terms were fetched or written — for every scope, not only Incremental (so a `scope="all"` run's trailing month gets marked too; see [Shared monthly coverage selection](#shared-monthly-coverage-selection) for why that's harmless). `counts.rows_fetched` accumulates each month's raw row count (including zero-view rows storage drops); `counts.rows_written` accumulates each month's upsert count. A `scope="all"`/`"year"` run issues one call per calendar month in range per video — full history is more calls of the same shape, not a heavier kind of request.
- `fetch_video_search_terms()` never paginates: a response with more than 25 rows, or headers/rows it can't parse, raises `RuntimeError` rather than being silently accepted — retry (via the shared `_analytics_query()` backoff) may repeat the identical request, but a second page is never requested even when exactly 25 rows come back. This is a real, verified API limit (not a bug in this codebase) — do not attempt to fix under-attribution by adding pagination here; see `search-insights-api-findings.md`.
- Independent of `video_traffic_sources` and of `related_video_insights`: this stage neither reads nor requires either in the same plan, and reporting derives any read-time comparison against traffic data separately (see `database.md`/`api.md`) rather than during sync. A fetch, upsert, or coverage-write failure raises immediately, preserving every already-committed `(video, window)` upsert/coverage mark and the counters accumulated so far — the same fail-fast/partial-counter behavior as every other stage (see [Stage tracking](#stage-tracking)).

## Related video insights synchronization

`sync_related_video_insights(scope, year, counts)` (`sync/stages.py`) fetches and upserts monthly Related Video referrers for every owned video, then resolves metadata for newly encountered referrer IDs. It shares `sync_search_insights`'s period-aware shape — `scope="incremental"` uses `_incremental_monthly_windows("related_video_insights", ...)` (every uncovered month from `publish_date` through yesterday plus the previous/current pair, or the fixed current+previous fallback for a video with no `published_at`); `scope="year"`/`"all"` refresh a wider range clamped per video to its own publish date — and the same one-call-per-calendar-month cadence, for the same 25-row-per-request reasoning (see [Search insights synchronization](#search-insights-synchronization) and `search-insights-api-findings.md`). This metadata-resolution logic lives only here, not in `sync_search_insights`. Coverage is tracked under its own `related_video_insights` collector name, independent of `search_insights`'s.

- The worklist is `database.get_owned_video_ids(published_through=...)`, prefiltered by this stage's effective range end (see [Prefiltered worklist (effective range end)](#prefiltered-worklist-effective-range-end)) and, on top of that, still captured once at stage start — a referrer resolved into `videos` during this same run can never become a target within the same run.
- Each `MonthlyWindow` calls `youtube.fetch_video_related_videos(video_id, window.start_date, window.end_date)` (`youtube/analytics_api.py`) exactly once — `dimensions=insightTrafficSourceDetail`, `metrics=views`, `filters=video==<id>;insightTrafficSourceType==RELATED_VIDEO`, `sort=-views`, `maxResults=25`, `startIndex` omitted entirely; parsing (header lookup, the 25-row cap check, malformed-row rejection, positive-views-only filtering) is a shared helper with Search's own parsing, since the two response shapes are identical apart from the traffic-source-type filter and what the detail value represents. The response's referrers pass straight through to one `database.upsert_related_videos(video_id, window.month, result.referrers)` call per month; once that upsert succeeds, `database.upsert_coverage("related_video_insights", video_id, [window.month])` marks the month complete — before the best-effort referrer metadata resolution below runs, so a metadata lookup failure can never invalidate an already-successful month's coverage.
- This stage never reads or writes Video Traffic Sources, and shares no dependency with `sync_search_insights` — either can be selected/resynced without the other, in any combination, and toggling one in the Sync page never selects or deselects the other.
- After every video/month has been fetched, `_resolve_related_video_metadata(newly_encountered_ids, counts)` resolves referrer IDs not already present in `videos` (via `database.get_all_video_ids()`, deliberately unfiltered by ownership — checking "known at all," not "owned"; see `database.md`). If there are no unknown IDs, neither the channel-identity lookup nor `fetch_videos()` is called at all. Otherwise, `youtube.fetch_channel_identity()` is looked up once — a failure there is logged at `WARNING` and metadata resolution is skipped entirely for this run, without failing the stage or discarding Related rows already stored, since it is needed to classify ownership and has no per-batch fallback. Unknown IDs are sorted for determinism and resolved in batches of at most 50 via `youtube.fetch_videos()`, then classified against that channel ID and written via `database.upsert_related_video(video, own=matches_channel)`. A batch lookup failure is likewise logged at `WARNING` and skipped, without stopping other batches or the stage. An ID omitted from its batch's response simply gets no video row and is left to be retried on a future run.
- There is no separate "mark already-stored uploads ID owned" step — the `own = MAX(own, excluded.own)` rule in `upsert_own_video`'s shared conflict clause already promotes ownership the next time a real detail fetch succeeds (see `database.md`), and a video with no existing row and no fresh data has nothing to write regardless.
- A fetch or write failure during the per-video/month loop raises immediately, preserving every already-committed `(video, window)` upsert and the counters accumulated so far — the same fail-fast/partial-counter behavior as every other stage (see [Stage tracking](#stage-tracking)). Metadata resolution runs only after that loop completes without error.

## YouTube API requests and pagination

- Both `iter_video_analytics()` and `iter_video_traffic_sources()` (`youtube/analytics_api.py`) chunk the requested date range into **12-month windows** via `_chunk_date_range(..., months=12)` (`youtube/analytics_api.py:84-97`; the function's own default is `months=4`, but both call sites override it to 12). Chunks are anchored to the video's own start date, not calendar-aligned Jan–Dec.
- `maxResults` is set high enough to avoid pagination in the common case:
  - `iter_video_analytics`: `maxResults=2000` (`youtube/analytics_api.py:166`) — a year is at most 365 rows, single `day` dimension.
  - `iter_video_traffic_sources`: `maxResults=10000` (`youtube/analytics_api.py:218`) — a year's theoretical ceiling is 365 days × 21 possible `insightTrafficSourceType` values = 7665 rows.
- Both generators pass an explicit `sort` param (`day` / `day,insightTrafficSourceType`) so that `_fetch_analytics_rows()`'s `startIndex`-based pagination fallback (used only if a chunk's row count ever exceeds `maxResults`) returns rows in a stable, deterministic order across pages.
- `iter_video_analytics()` and `iter_video_traffic_sources()` are generators (`yield`-based) — rows are upserted by the caller as they arrive, not batched into a single list first.
- `_analytics_query()` (`youtube/analytics_api.py:61-81`) retries with exponential backoff (`2^(attempt-1)`, capped at 30s, up to 5 attempts) on HTTP 5xx, or 403/429 specifically when the error body indicates `rateLimitExceeded`/`quotaExceeded`. Each retry emits a `WARNING` record — see [Sync logging](#sync-logging).
- All three YouTube API modules share OAuth via `youtube/auth.py`'s `get_credentials()`; `youtube/data_api.py`'s `_data_client()` and `youtube/analytics_api.py`'s `_analytics_client()` each call it independently to build their respective `googleapiclient` service objects.
- The five token-pagination loops in `youtube/data_api.py` (`fetch_shorts_video_ids()`, `fetch_all_video_ids()`, `fetch_playlists()`, `fetch_playlist_items()`, `iter_comment_threads()`) each emit one record per fetched page — see [Sync logging](#sync-logging) and [Pagination termination](#pagination-termination).

## Pagination termination

All five Data API loops delegate their stop/continue decision to `_next_page_token()`
(`youtube/data_api.py`), which returns `(token_to_follow, truncated)` and logs the page
as a side effect. The four collection fetchers return `(items, truncated)` to their
caller; `iter_comment_threads()` is a generator that yields items and drops the
truncation flag, since no comment delete is gated on it.

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

Cursor history is per invocation. `fetch_playlist_items()` and `iter_comment_threads()`
each create their set inside the function, so two playlists — or two videos — that
legitimately hand back the same token string are never confused for a cycle; nothing
about token history is shared across playlists, videos, calls, clients, or batches.

`truncated` is what makes early termination safe rather than merely quiet: it marks the
returned rows as an incomplete view that must not be treated as authoritative for
absence. See [Video and playlist synchronization](#video-and-playlist-synchronization)
for the two playlist-level deletes it gates (`delete_playlist_items()` per playlist and
the listing-level `delete_playlists_not_in()`) — `sync_videos()` no longer deletes at
all, and `sync_pruning()`'s delete is ungated by any truncation flag. `fetch_all_video_ids()`'s
own `truncated` flag is otherwise unused now that `sync_videos()` doesn't delete against
it. `fetch_shorts_video_ids()` also returns the flag, but no caller acts on it — a
truncated Shorts set only mislabels some videos' `content_type`, which the next complete
sync corrects. `iter_comment_threads()` logs the condition and stops without surfacing a
flag at all: the comments stage never deletes a comment, so a truncated walk costs
freshness rather than correctness.

The Analytics API paginator is unaffected. `_fetch_analytics_rows()`
(`youtube/analytics_api.py:100`) is `startIndex`-based rather than token-based and stops
as soon as a page returns fewer rows than `maxResults` — including an empty page — and
continues after a page that returns exactly `maxResults` rows; it has no cursor to
repeat and returns no truncation flag.

## Authentication

- Shorts detection (`fetch_shorts_video_ids()`, `youtube/data_api.py:128-169`) relies exclusively on the channel's UUSH ("uploads → Shorts") playlist; it raises `RuntimeError` if the uploads playlist ID doesn't start with `UU`, or if the derived `UUSH...` playlist 404s.
- `_SCOPES` (`youtube/auth.py`) is the authoritative OAuth scope list: `youtube.readonly`, `youtube.force-ssl`, `yt-analytics.readonly`, `yt-analytics-monetary.readonly`. `SCOPES` in `backend/.env`/`.env.example` documents the same set but is read by no code — like the paths beside it, there is no settings layer, so changing scopes means editing that list. `youtube.force-ssl` is required by `commentThreads.list`; `youtube.readonly` alone is rejected with `insufficientPermissions`. It is the narrowest scope Google offers for comment reads even though it also permits comment writes, which no code path makes.
- Adding a scope invalidates every existing `token.json` in practice: Google's grant is fixed at consent time, and the API rejects the new call rather than the token load. Delete `backend/secrets/token.json` and restart to re-consent after any change to `_SCOPES`.
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
| Page fetched | the five `youtube/data_api.py` token-pagination loops, via `_log_page()` | resource, page number, item count, owning entity id and name where one exists, that page's `nextPageToken` |
| Analytics page fetched | `youtube/analytics_api.py::_fetch_analytics_rows()`, via its own `_log_page()` | resource, page number, row count, `startIndex`, owning `video_id` and title |
| Video processed | the per-video loops in `sync_video_analytics()`/`sync_video_traffic_sources()`/`sync_search_insights()`/`sync_related_video_insights()` | ordinal/total, `video_id`, rows fetched for that video (search and related insights also log the month count for that video), title |
| Video skipped | the two `continue` branches in each analytics stage, and `sync_search_insights()`'s/`sync_related_video_insights()`'s `scope="year"`/`"all"` no-publish-date branch | ordinal/total, `video_id`, reason (`no_publish_date` or `empty_range`), title |
| Comments processed | the per-video loop in `sync_comments()` | ordinal/total, `video_id`, scope, comments fetched and rows written for that video, title |
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
| Comment video skipped | `iter_comment_threads()`, when a video's comments are disabled or the video is gone | `video_id`, the API's `reason`, title |
| Comment item skipped | `iter_comment_threads()` for a malformed thread, and `sync_comments()` for a write failure | `video_id`, the thread or comment id, and either `reason=malformed_item` or safe exception context |
| Request retried | `youtube/analytics_api.py::_analytics_query()` | attempt number, HTTP status, classified reason (`server` or `quota`), delay |
| Related video metadata batch failed | `_resolve_related_video_metadata()` in `sync/stages.py`, when a batch lookup via `youtube.fetch_videos()` raises | batch size, safe exception context — the batch is skipped, not retried within the same run |

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
