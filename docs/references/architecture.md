# Architecture

## Purpose

High-level orientation to the system: stack, data flow, runtime lifecycle, and repository layout. This file stays intentionally shallow — schema detail lives in `database.md`, ingestion detail in `sync.md`, HTTP contracts in `api.md`, and UI detail in `frontend.md`. When any of those conflict with this file, treat the current source code as authoritative, not this document.

## Authoritative source files

- `backend/server.py`
- `backend/logging_config.py` (shared logging configuration — see `sync.md` for the
  detailed sync-event fields)
- `backend/sync/scheduler.py` (scheduler wiring only — see `sync.md` for behavior)
- `frontend/src/App.tsx`
- `frontend/vite.config.ts`, `frontend/tsconfig.app.json`

## Contents

- [System overview](#system-overview)
- [Data flow](#data-flow)
- [Runtime lifecycle](#runtime-lifecycle)
- [Logging](#logging)
- [Backend structure](#backend-structure)
- [Frontend structure](#frontend-structure)
- [Repository layout](#repository-layout)

## System overview

FastAPI (Python) backend, React + TypeScript frontend (Vite), SQLite storage. The backend is the only component that talks to the YouTube Data API v3 and YouTube Analytics API v2; the frontend only talks to the backend's own REST API.

## Data flow

```
YouTube Data API v3 / YouTube Analytics API v2
        │
        ▼
  backend/sync/  (background sync orchestration)
        │
        ▼
   backend/data/youtube.db  (SQLite)
        │
        ▼
  backend/routes/  (FastAPI REST endpoints)
        │
        ▼
  frontend/src/api.ts  (fetch wrappers)
        │
        ▼
   React pages/components
```

## Runtime lifecycle

`backend/server.py` defines the FastAPI app with an `asynccontextmanager` lifespan that
logs its own boundaries through the `youtube_analytics.lifecycle` logger (acquired via
`logging_config.get_logger("lifecycle")`, so configuration happens regardless of which
application module is imported first):

1. Log an `INFO` "Application startup" record.
2. `database.init_db()` — creates tables from `schema.sql` if they don't already exist.
3. `database.writer.update(SyncRun(status="incomplete"), where=(("status", "=", "running"),))` — closes out `sync_runs` rows a killed process left marked `running`, setting them to `incomplete` and logging a `WARNING` with the count when any were found. This belongs at startup specifically: the reservation guarding a live sync is in-memory and died with the previous process, so nothing can legitimately still be running (see `database.md`).
4. Yield to serve requests, then — in a `finally`, so it runs after a normal shutdown or a startup/runtime failure alike — log an `INFO` "Application shutdown" record.

The lifespan starts no sync. `sync.start_background_scheduler()` (`sync/scheduler.py`) is defined and exported but not called, so the only way a sync starts is `POST /sync/trigger` (see `sync.md`).

CORS is configured to allow only `http://localhost:5173` (the Vite dev server). Both `python server.py` and `uvicorn server:app --reload` start the same app; neither hardcodes `reload=True` in `server.py` itself, so file-watching only happens when `--reload` is passed on the `uvicorn` command line (or via `uvicorn.run(..., reload=True)`, which `server.py`'s `__main__` block does not currently set).

## Logging

`backend/logging_config.py` is the shared, standard-library-only logging configuration
used by every application module. It defines two fixed file destinations derived from
the backend root (`backend/data/application.log`, `backend/data/sync.log`), a
`TimezoneAwareFormatter` that renders UTC ISO 8601 timestamps with an explicit
`+00:00` offset, and `get_logger(area)` — the accessor every module must use instead of
calling `logging.getLogger()` directly, so configuration is idempotent regardless of
import order (`sync/orchestration.py` and its dependents are imported directly by the
test suite without importing `server.py`).

Routing: the `youtube_analytics.lifecycle` logger writes `INFO`+ to `application.log`
only; the `youtube_analytics.sync` logger writes `INFO`+ to both files and `DEBUG`
detail only to `sync.log`; every other area writes `INFO`+ to `application.log` only.
See `sync.md` for the per-stage records and the six sync-only `DEBUG` detail events.

`APP_LOG_PATH`/`SYNC_LOG_PATH` in `backend/.env.example` document the defaults but are
not read by any code, exactly like `DB_PATH`/`CLIENT_SECRET_PATH` beside them — no
settings layer was introduced. There is no log rotation or retention; both files grow
indefinitely and are safe to delete between runs.

## Backend structure

| Path | Responsibility |
|---|---|
| `server.py` | FastAPI app construction, CORS, lifespan (`init_db` → stranded `sync_runs` sweep through `writer.update()`) |
| `routes/videos.py`, `routes/playlists.py`, `routes/analytics.py`, `routes/comments.py`, `routes/synchronization.py`, `routes/metadata.py` | API route handlers, grouped by resource. They read through `database.reader` (directly, or with a `database.queries` specification) and serialize row dataclasses with `to_dict(fields=...)`, or call a `database` report function; `routes/__init__.py` aggregates them in a fixed order into one `router` |
| `routes/daily_series.py` | Shared daily-series route helpers: the analytics metric defaults and traffic-source `DateFill` passed to the reader, and the traffic-source row serializer; registers no routes |
| `routes/video_scope.py` | Shared route helpers `require_owned_video()`, `require_playlist()` (404 existence checks through the reader), and `resolve_playlist_video_ids()` (playlist 404, then member IDs, for every playlist-scoped handler); registers no routes |
| `sync/status.py` | Global sync-status lifecycle (`idle \| running \| stopping \| success \| failed \| cancelled`, plus message) behind one lock, with `try_begin_sync()`/`request_stop()` reservation primitives and the `raise_if_stopping()` cooperative-cancellation checkpoint |
| `sync/plans.py` | Plan types, canonical `STAGE_ORDER`, derived `FULL_SYNC_TYPES`, available years, `validate_plan()` |
| `sync/orchestration.py` | `execute_plan()`/`run_plan()`, stage registry, selected-stage sequencing, `sync_runs` tracking through the writer |
| `sync/stages.py` | The nine sync stage implementations plus the shared incremental-lookback calculation, the Related Video referrer metadata resolver, and the comment bootstrap cutoff |
| `sync/monthly_insights.py` | Pure calendar-window helper for the Search insights stage — no I/O, no clock reads beyond the `date` it's given |
| `sync/coverage.py` | Pure missing-month and range-coalescing helpers for `sync_coverage`-based selection — no I/O |
| `sync/write_preparation.py` | Pure validation and aggregation of monthly Search/Related insight payloads into `SearchTerm`/`RelatedVideo` rows — no I/O |
| `sync/scheduler.py` | Freshness check (`synced_today()`) and a one-shot background sync launcher (`start_background_scheduler()`); neither is called by the application |
| `youtube/auth.py` | OAuth credentials and token/secret paths |
| `youtube/data_api.py` | YouTube Data API v3 client, pagination, Shorts detection, video/playlist/comment-thread fetchers |
| `youtube/analytics_api.py` | YouTube Analytics API v2 client, retry/backoff, date chunking, daily analytics/traffic-source generators |
| `logging_config.py` | Shared logging configuration: `TimezoneAwareFormatter`, `configure_logging()`, `get_logger(area)`, `exception_context()` |
| `database/connection.py` | Connection setup, `init_db()`, `now()` (UTC timestamp), shared `_month_bound_conditions()` |
| `database/dataclasses/` | One data-only row dataclass per table (`Video`, `Playlist`, …), every field defaulting to `None`, with shared `from_dict()`/`to_dict(fields=...)` conversion |
| `database/tables.py` | Shared row-class → table registry, primary keys, generated-key and non-decreasing-column rules, used by both reader and writer |
| `database/filters.py` | Shared validated `WHERE` compilation from tuple conditions and `NotExists` predicates, used by reader selects and writer updates and deletes |
| `database/reader.py` | All read execution: `select`/`select_one`/`scalar` for one table, `fetch`/`fetch_joined`/`fetch_scalar` for code-owned SQL, optional daily date filling (`DateFill`), per-field grouping of results (`group_by`), and connection borrowing |
| `database/writer.py` | Every insert/update/delete: `write()`/`write_many()` update-then-insert by key, leaving `None` fields untouched (`write()` can return persisted fields such as a generated ID); `update()` changes only the rows matching a required filter and never inserts; `delete()` removes the rows matching a required filter; each call runs in one committed transaction or a savepoint on a borrowed one |
| `database/queries.py` | Non-executing `Query` specifications for joins, grouping, and ranking shared by routes and sync |
| `database/video_statistics.py` | `get_video_stats()` Legacy/New report |
| `database/sync_runs.py`, `database/related_videos.py` | The reports that do real calculation work (sync-batch assembly and status, referrer totals) |
| `schema.sql` | SQLite schema definition (12 tables) — see `database.md` |
| `scripts/issue-48-migration.py` | Standalone, one-time migration adding `videos.own` to a pre-existing database — not run by `init_db()` (see `database.md`) |
| `scripts/issue-62-migration.py` | Standalone, one-time `sync_coverage` backfill for a pre-existing database — not run by `init_db()` (see `database.md`) |

Each of `routes/`, `sync/`, `youtube/`, and `database/` re-exports its public callables from its package `__init__.py`, so other modules keep importing them as `import database`, `import sync`, `import youtube`, `from routes import router` — the split is internal.

## Frontend structure

| File | Responsibility |
|---|---|
| `src/main.tsx` | Entry point |
| `src/App.tsx` | `BrowserRouter` + `Routes`; `TopNav` rendered outside `Routes` (persists across all pages) |
| `src/index.css` | Global design tokens + shared CSS classes — see `frontend.md` |
| `src/api.ts` | All fetch calls to the backend |
| `src/types/index.ts` | Shared TypeScript interfaces |
| `src/lib/` | Shared non-component helpers (`trafficSources.ts`, `topVideos.ts`, `categoricalColors.ts`) |
| `src/hooks/` | Shared hooks (`useReplaceSearchParams.ts`, `useDebouncedInput.ts`, `useReconciledSelection.ts`) |
| `src/pages/` | Route-level components |
| `src/components/` | Shared/reusable components |

Routes registered in `App.tsx`:

```
/                          → Home
/videos                   → Videos
/playlists                → Playlists
/analytics                → Analytics
/analytics/videos/:id     → VideoAnalytics
/analytics/playlists/:id  → PlaylistAnalytics
/sync                     → Sync
```

Comments has no route of its own: it is a tab on the three Analytics pages, reached at
`/analytics?tab=comments`, `/analytics/videos/:id?tab=comments`, and
`/analytics/playlists/:id?tab=comments` — see `frontend.md`.

## Repository layout

```
backend/
  server.py
  logging_config.py

  tests/                 # stdlib unittest classes, run via pytest (the only safety-guarded runner)
    conftest.py            # autouse fixture: fails any real network/OAuth access
    support.py              # IsolatedDatabaseTestCase, row factories, seed_dataset(), create_test_app()
    test_test_harness.py, test_database_catalog.py, test_database_analytics.py, test_api_contracts.py,
    test_analytics_video_scopes.py, test_analytics_title_filters.py, test_video_statistics_scopes.py,
    test_sync_plans.py, test_sync_orchestration.py, test_sync_status.py,
    test_sync_scheduler.py, test_sync_routes.py, test_sync_checkpoint.py, test_sync_runs.py,
    test_sync_cancellation.py,
    test_application_logging.py, test_sync_detail_logging.py,
    test_pagination_safety.py, test_comment_sync.py, test_comments_api.py,
    test_database_search_terms.py, test_search_insights_sync.py, test_search_insights_api.py,
    test_database_video_ownership.py, test_database_related_videos.py, test_database_reader.py,
    test_database_writer.py, test_write_preparation.py,
    test_related_video_insights_sync.py, test_related_videos_api.py
  schema.sql

  routes/
    __init__.py           # aggregates the sub-routers below into one `router`
    videos.py
    playlists.py
    analytics.py
    comments.py
    synchronization.py
    metadata.py
    video_scope.py         # require_owned_video(), require_playlist(), resolve_playlist_video_ids()
    daily_series.py        # daily analytics/traffic-source fill configuration and serializer

  sync/
    __init__.py            # re-exports the plan types/validation, status primitives,
                           # execute_plan, run_plan, start_background_scheduler
    status.py
    plans.py
    orchestration.py
    stages.py
    scheduler.py
    monthly_insights.py
    coverage.py
    write_preparation.py

  youtube/
    __init__.py             # re-exports get_credentials + the fetch/iter functions
    auth.py
    data_api.py
    analytics_api.py

  database/
    __init__.py              # re-exports row classes, reader, writer, queries, and report functions
    connection.py
    tables.py                # shared registry: tables, keys, write rules
    filters.py               # shared WHERE compilation for reads and deletes
    reader.py                # read execution
    writer.py                # insert/update/delete execution
    queries.py               # non-executing query specifications
    video_statistics.py      # get_video_stats()
    dataclasses/             # one row dataclass per table, plus base.py (from_dict/to_dict)
    sync_runs.py
    related_videos.py

  scripts/
    issue-48-migration.py    # standalone one-time migration adding videos.own
    issue-62-migration.py    # standalone one-time sync_coverage backfill

  secrets/
    token.json           # OAuth token; auto-deleted on any credential-refresh failure, re-created on next auth
    client_secret.json
  data/
    youtube.db           # SQLite database
    application.log      # general/high-level application + sync log (gitignored, no rotation)
    sync.log             # high-level + detailed DEBUG sync log (gitignored, no rotation)

frontend/
  src/
    main.tsx
    App.tsx
    index.css
    api.ts
    types/index.ts
    lib/
      trafficSources.ts
      topVideos.ts
      categoricalColors.ts
    hooks/
      useReplaceSearchParams.ts
      useDebouncedInput.ts
      useReconciledSelection.ts
    pages/
      Home.tsx, Videos.tsx, Playlists.tsx, Analytics.tsx, VideoAnalytics.tsx,
      PlaylistAnalytics.tsx, Sync.tsx
      (+ colocated .css files where present)
    components/
      TopNav.tsx, SyncStatus.tsx, VideoTable.tsx, VideoStatsBar.tsx, AnalyticsChart.tsx,
      UploadStrip.tsx, TrafficSourceChart.tsx, TrafficSourcesTable.tsx,
      TrafficSourceTopVideosPanel.tsx, TopVideosList.tsx, VideoCarouselCard.tsx,
      TrafficSourceDonutCard.tsx, TopPerformersCard.tsx, PeriodSelect.tsx,
      SearchTermsDonutCard.tsx, SearchTermVideosDonutCard.tsx,
      RelatedReferrerBreakdownCard.tsx, RelatedDestinationsByReferrerCard.tsx
      (+ colocated .css files)
```
