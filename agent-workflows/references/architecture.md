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
3. `sync.start_background_scheduler()` — runs one complete incremental sync on a daemon thread unless any sync run already succeeded today; no recurring timer is scheduled (see `sync.md`).
4. Yield to serve requests, then — in a `finally`, so it runs after a normal shutdown or a startup/runtime failure alike — log an `INFO` "Application shutdown" record.

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
See `sync.md` for the per-stage records and the five sync-only `DEBUG` detail events.

`APP_LOG_PATH`/`SYNC_LOG_PATH` in `backend/.env.example` document the defaults but are
not read by any code, exactly like `DB_PATH`/`CLIENT_SECRET_PATH` beside them — no
settings layer was introduced. There is no log rotation or retention; both files grow
indefinitely and are safe to delete between runs.

## Backend structure

| Path | Responsibility |
|---|---|
| `server.py` | FastAPI app construction, CORS, lifespan (`init_db` → `start_background_scheduler`) |
| `routes/videos.py`, `routes/playlists.py`, `routes/analytics.py`, `routes/synchronization.py`, `routes/metadata.py` | API route handlers, grouped by resource — thin wrappers around `database` helpers; `routes/__init__.py` aggregates them in a fixed order into one `router` |
| `sync/status.py` | Global sync-status state (`is_syncing`, `message`) and the `try_start()` reservation primitive, behind one lock |
| `sync/plans.py` | Plan types, canonical `STAGE_ORDER`, derived `FULL_SYNC_TYPES`, available years, `validate_plan()` |
| `sync/orchestration.py` | `execute_plan()`/`run_plan()`, stage registry, selected-stage sequencing, `sync_runs` tracking |
| `sync/stages.py` | The five sync stage implementations plus the shared incremental-lookback calculation |
| `sync/scheduler.py` | Startup freshness check (`synced_today()`) and the one-shot startup sync |
| `youtube/auth.py` | OAuth credentials and token/secret paths |
| `youtube/data_api.py` | YouTube Data API v3 client, pagination, Shorts detection, video/playlist fetchers |
| `youtube/analytics_api.py` | YouTube Analytics API v2 client, retry/backoff, date chunking, daily analytics/traffic-source generators |
| `logging_config.py` | Shared logging configuration: `TimezoneAwareFormatter`, `configure_logging()`, `get_logger(area)`, `exception_context()` |
| `database/connection.py` | Connection setup, `init_db()`, `_now()` |
| `database/videos.py`, `database/playlists.py`, `database/analytics.py`, `database/traffic_sources.py`, `database/fx_rates.py`, `database/sync_runs.py` | DB helpers grouped by domain (upserts, queries, aggregation, zero-filling) |
| `schema.sql` | SQLite schema definition (7 tables) — see `database.md` |

Each of `routes/`, `sync/`, `youtube/`, and `database/` re-exports its public callables from its package `__init__.py`, so other modules keep importing them as `import database`, `import sync`, `import youtube`, `from routes import router` — the split is internal.

## Frontend structure

| File | Responsibility |
|---|---|
| `src/main.tsx` | Entry point |
| `src/App.tsx` | `BrowserRouter` + `Routes`; `TopNav` rendered outside `Routes` (persists across all pages) |
| `src/index.css` | Global design tokens + shared CSS classes — see `frontend.md` |
| `src/api.ts` | All fetch calls to the backend |
| `src/types/index.ts` | Shared TypeScript interfaces |
| `src/lib/` | Shared non-component helpers (`trafficSources.ts`, `topVideos.ts`) |
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

## Repository layout

```
backend/
  server.py
  logging_config.py

  tests/                 # stdlib unittest; run with
                         # python -m unittest discover -s tests
    test_sync_plans.py, test_sync_orchestration.py,
    test_sync_scheduler.py, test_sync_routes.py, test_sync_checkpoint.py,
    test_application_logging.py, test_sync_detail_logging.py,
    test_pagination_safety.py
  schema.sql

  routes/
    __init__.py           # aggregates the sub-routers below into one `router`
    videos.py
    playlists.py
    analytics.py
    synchronization.py
    metadata.py

  sync/
    __init__.py            # re-exports the plan types/validation, status primitives,
                           # execute_plan, run_plan, start_background_scheduler
    status.py
    plans.py
    orchestration.py
    stages.py
    scheduler.py

  youtube/
    __init__.py             # re-exports get_credentials + the fetch/iter functions
    auth.py
    data_api.py
    analytics_api.py

  database/
    __init__.py              # re-exports every public helper below
    connection.py
    videos.py
    playlists.py
    analytics.py
    traffic_sources.py
    fx_rates.py
    sync_runs.py

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
    pages/
      Home.tsx, Videos.tsx, Playlists.tsx, Analytics.tsx, VideoAnalytics.tsx,
      PlaylistAnalytics.tsx, Sync.tsx
      (+ colocated .css files where present)
    components/
      TopNav.tsx, SyncStatus.tsx, VideoTable.tsx, VideoStatsBar.tsx, AnalyticsChart.tsx,
      UploadStrip.tsx, TrafficSourceChart.tsx, TrafficSourcesTable.tsx,
      TrafficSourceTopVideosPanel.tsx, TopVideosList.tsx, VideoCarouselCard.tsx,
      TrafficSourceDonutCard.tsx, TopPerformersCard.tsx, PeriodSelect.tsx
      (+ colocated .css files)
```
