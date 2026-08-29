# YouTube Analytics Backend

FastAPI backend for YouTube Analytics.

## Setup

1. Create virtual environment with Python 3.12:
   ```bash
   uv venv --python 3.12
   ```

2. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```

3. Activate virtual environment:

   **Windows:**
   ```bash
   .venv\Scripts\activate
   ```

   **Linux/macOS:**
   ```bash
   source .venv/bin/activate
   ```

4. Place your OAuth client secret at `secrets/client_secret.json`

5. Copy `.env.example` to `.env` and fill in values

## Running

```bash
uvicorn server:app --reload
```

or directly:

```bash
python server.py
```

On first run, a browser window will open for YouTube OAuth. The token is saved to `secrets/token.json` for subsequent runs.

The server runs on `http://127.0.0.1:8000`

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Structure

```
backend/
  server.py            # FastAPI app entry point
  logging_config.py    # Shared logging configuration (see Logging below)

  routes/              # API endpoints, grouped by resource
    videos.py
    playlists.py
    analytics.py
    comments.py
    synchronization.py
    metadata.py

  database/            # DB connection and helpers, grouped by domain
    connection.py
    videos.py
    playlists.py
    analytics.py
    traffic_sources.py
    comments.py
    fx_rates.py
    sync_runs.py

  sync/                # Sync plans, orchestration, and the startup freshness check
    status.py
    plans.py
    orchestration.py
    stages.py
    scheduler.py

  tests/               # stdlib unittest suite (database, API contracts, sync, logging) run via pytest
    conftest.py          # autouse fixture that fails closed on real network/OAuth access
    support.py           # shared isolated-database base case, row factories, dataset seeder

  youtube/              # YouTube Data + Analytics API clients and fetchers
    auth.py
    data_api.py
    analytics_api.py

  schema.sql            # Database table definitions
```

## Endpoints

```
GET  /videos                  List all videos
GET  /videos/{id}             Single video detail
GET  /videos/{id}/analytics   Daily analytics for a video
GET  /playlists               List all playlists
GET  /playlists/{id}/videos   Videos in a playlist
GET  /comments                Top-level comments across the channel
GET  /comments/videos/{id}    Top-level comments on one video
GET  /comments/playlists/{id} Top-level comments on a playlist's videos
GET  /sync/status             Active sync status and progress
POST /sync/trigger            Queue a manual sync of the selected stages (JSON plan body)
GET  /sync/runs               Recent sync-stage records, newest first
```

## Syncing

On startup the app runs one complete incremental sync unless any sync run already
succeeded today (local date). A single stage counts — manually syncing just FX rates
marks the day as synced and the next launch runs nothing. A day on which every run failed
still counts as not-synced, so the next launch retries.

There is no recurring timer — restarting the server the same day does nothing, and
freshness is otherwise driven manually from the `/sync` page in the frontend, which can
select any combination of stages and give video analytics and traffic sources independent
periods.

The comments stage imports top-level comments for videos already stored locally; reply
bodies are never fetched. It offers two scopes rather than a period: **Incremental**
(the default, used by the startup sync) reads each video back to the comments it already
holds, or to December 1 of the previous year for a video with none, and **All**
re-reads every comment. Neither scope ever deletes a comment.

## Logging

`logging_config.py` configures two fixed, UTF-8, append-mode log files beside the
database under `data/`, created automatically the first time any application module
calls `logging_config.get_logger(area)`:

- `data/application.log` — general/high-level application and sync records (`INFO`+).
- `data/sync.log` — high-level sync records plus detailed sync-only `DEBUG` events.

Every record is one line: `<UTC ISO 8601 timestamp with +00:00> <LEVEL> <logger name>
<message>` (e.g. `2026-07-31T12:34:56.123+00:00 INFO youtube_analytics.sync Sync stage
completed sync_type=video_analytics rows_fetched=0 rows_written=0 rows_deleted=0`).

Routing: the `youtube_analytics.lifecycle` logger (application startup/shutdown) writes
to `application.log` only. The `youtube_analytics.sync` logger writes `INFO`+ records
(plan-level outcomes and per-stage start/success/failure) to both files, and `DEBUG`
detail records only to `sync.log`. Any other application area writes `INFO`+ to
`application.log` only. All application modules acquire their logger through
`get_logger(area)` rather than the standard library's `logging.getLogger()` directly,
so configuration happens once regardless of which module is imported first.

The sync-only `DEBUG` detail events, each one line emitted after the work completes
(never a paired before/after record, never one line per returned row):

| Event | Where | Fields |
|---|---|---|
| Page fetched | the five `youtube/data_api.py` token-pagination loops | resource, page number, item count, owning entity id and name where one exists, that page's `nextPageToken` |
| Analytics page fetched | `youtube/analytics_api.py::_fetch_analytics_rows()` | resource, page number, row count, `startIndex`, owning `video_id` and title |
| Video processed | the per-video loops in both analytics stages | ordinal/total, `video_id`, rows fetched for that video, title |
| Video skipped | the two `continue` branches in each analytics stage | ordinal/total, `video_id`, reason (`no_publish_date` or `empty_range`), title |
| Comments processed | the per-video loop in `sync/stages.py::sync_comments()` | ordinal/total, `video_id`, scope, comments fetched and rows written for that video, title |
| FX rates downloaded | `sync/stages.py::sync_fx_rates()` | requested start/end dates, days written, or the no-work condition |

Two conditions are anomalies rather than routine detail and are logged at `WARNING`, so
they reach `application.log` as well:

| Event | Where |
|---|---|
| Empty page with a token / repeated pagination cursor | `_log_page()` in `youtube/data_api.py` |
| Cleanup skipped due to truncated pagination | `sync_videos()`/`sync_playlists()` |
| Comment video or item skipped | `iter_comment_threads()` (comments disabled, video gone, malformed thread) and `sync_comments()` (write failure) |
| Request retried | `youtube/analytics_api.py::_analytics_query()` |

Every logged field is an identifier, counter, date, name, or pagination token. Titles
and pagination tokens are logged deliberately — see `sync.md`'s "Sync logging" section
for why. Records never carry descriptions, thumbnails, statistics payloads,
credentials, OAuth tokens, request/response bodies, or raw exception text — failure
records use only the exception's class name and source location.

`APP_LOG_PATH`/`SYNC_LOG_PATH` in `.env.example` document the defaults but, like
`DB_PATH` and `CLIENT_SECRET_PATH` beside them, are not read by any code; changing a log
destination means editing the `_APP_LOG_PATH`/`_SYNC_LOG_PATH` constants in
`logging_config.py`. There is no rotation or retention — both files grow indefinitely
and are safe to delete between runs, since nothing reads them back.

## Testing

Run tests and type checks through the backend's virtual environment (`backend/.venv`),
not a global `python`/`pip` — dependencies like `pytest` and `mypy` are installed there,
not system-wide.

```bash
cd backend
.venv/Scripts/python.exe -m pytest          # Windows
.venv/bin/python -m pytest                  # macOS/Linux
```

`pytest.ini` sets `testpaths = tests`, so the bare command above is the canonical,
complete run — no `tests/` argument is needed. This is also the exact command CI runs,
so a local pass is a reliable predictor of the CI result.

`pytest` (not raw `python -m unittest discover`) is the only supported runner: every
test in `tests/` gets an autouse `conftest.py` fixture that fails any test attempting a
real (non-loopback) network connection or an OAuth credential fetch — including the
`get_credentials` reference each of `youtube.auth`, `youtube.data_api`, and
`youtube.analytics_api` holds independently — with a clear `AssertionError`, so an
unmocked external call fails loudly instead of reaching the network. Running the same
stdlib `unittest.TestCase` classes through `unittest discover` skips that fixture and is
not safety-equivalent.

Every database-backed test extends `tests.support.IsolatedDatabaseTestCase` (or the
pre-seeded `SeededDatabaseTestCase`), which creates a fresh temporary SQLite file per
test, calls the real `database.init_db()` against it, and refuses to run if the resolved
path ever matches the real application database — so no test can touch
`data/youtube.db`. `tests/support.py` also provides deterministic row factories
(`make_video`, `make_playlist`, `make_video_analytics`, etc.), a `freeze_now()` context
manager that pins every generated `updated_at`/`started_at`/`completed_at` timestamp so
seeded fixtures stay reproducible, and a `seed_dataset()` convenience (built on
`freeze_now()`) that populates every table with a small, fixed dataset.
`create_test_app()`/`create_test_client()` build a lifespan-free FastAPI app from one or
more routers for API contract tests, so — unlike a real request through `server.app` —
`mark_incomplete_sync_runs()` and `sync.start_background_scheduler()` never run; only the
test's own `IsolatedDatabaseTestCase.setUp()` initializes the database. Extend the suite
by adding new focused tests on top of these factories rather than duplicating
temp-database or app-construction boilerplate.

Beyond database isolation, external APIs and sync stage execution are mocked directly,
and the logging tests redirect both log files to a `TemporaryDirectory`.

## Dependencies

- `fastapi` — web framework
- `uvicorn` — ASGI server
- `google-api-python-client` — YouTube Data + Analytics API
- `google-auth-oauthlib` — OAuth2 flow
- `httpx2` — required by `starlette.testclient` for the test suite only
- `pydantic-settings` — `.env` config management
