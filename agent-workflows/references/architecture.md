# Architecture

## Purpose

High-level orientation to the system: stack, data flow, runtime lifecycle, and repository layout. This file stays intentionally shallow — schema detail lives in `database.md`, ingestion detail in `sync.md`, HTTP contracts in `api.md`, and UI detail in `frontend.md`. When any of those conflict with this file, treat the current source code as authoritative, not this document.

## Authoritative source files

- `backend/server.py`
- `backend/sync.py` (scheduler wiring only — see `sync.md` for behavior)
- `frontend/src/App.tsx`
- `frontend/vite.config.ts`, `frontend/tsconfig.app.json`

## Contents

- [System overview](#system-overview)
- [Data flow](#data-flow)
- [Runtime lifecycle](#runtime-lifecycle)
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
  backend/sync.py  (background sync orchestration)
        │
        ▼
   backend/data/youtube.db  (SQLite)
        │
        ▼
  backend/routes.py  (FastAPI REST endpoints)
        │
        ▼
  frontend/src/api.ts  (fetch wrappers)
        │
        ▼
   React pages/components
```

## Runtime lifecycle

`backend/server.py` defines the FastAPI app with an `asynccontextmanager` lifespan:

1. `database.init_db()` — creates tables from `schema.sql` if they don't already exist.
2. `sync.start_background_scheduler()` — starts the 24-hour sync loop (see `sync.md`).

CORS is configured to allow only `http://localhost:5173` (the Vite dev server). Running `python server.py` directly starts `uvicorn` on `0.0.0.0:8000` with `reload=True`; in normal development the file is run via `uvicorn server:app --reload` instead.

## Backend structure

| File | Responsibility |
|---|---|
| `server.py` | FastAPI app construction, CORS, lifespan (`init_db` → `start_background_scheduler`) |
| `routes.py` | All API route handlers — thin wrappers around `database.py` helpers |
| `sync.py` | Sync orchestration, scope handling, `sync_runs` tracking, 24h background scheduler, global sync-status state |
| `youtube.py` | YouTube Data API v3 / Analytics API v2 clients, OAuth, pagination, chunking, Shorts detection |
| `database.py` | All DB helpers (connection setup, upserts, queries, aggregation, zero-filling) |
| `schema.sql` | SQLite schema definition (8 tables) — see `database.md` |

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
```

## Repository layout

```
backend/
  server.py
  routes.py
  sync.py
  youtube.py
  database.py
  schema.sql
  secrets/
    token.json           # OAuth token; auto-deleted on any credential-refresh failure, re-created on next auth
    client_secret.json
  data/
    youtube.db           # SQLite database

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
      Home.tsx, Videos.tsx, Playlists.tsx, Analytics.tsx, VideoAnalytics.tsx, PlaylistAnalytics.tsx
      (+ colocated .css files where present)
    components/
      TopNav.tsx, SyncStatus.tsx, VideoTable.tsx, VideoStatsBar.tsx, AnalyticsChart.tsx,
      UploadStrip.tsx, TrafficSourceChart.tsx, TrafficSourcesTable.tsx,
      TrafficSourceTopVideosPanel.tsx, TopVideosList.tsx, VideoCarouselCard.tsx,
      TrafficSourceDonutCard.tsx, TopPerformersCard.tsx, PeriodSelect.tsx
      (+ colocated .css files)
```
