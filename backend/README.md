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
    synchronization.py
    metadata.py

  database/            # DB connection and helpers, grouped by domain
    connection.py
    videos.py
    playlists.py
    analytics.py
    traffic_sources.py
    fx_rates.py
    sync_runs.py

  sync/                # Sync plans, orchestration, and the startup freshness check
    status.py
    plans.py
    orchestration.py
    stages.py
    scheduler.py

  tests/               # stdlib unittest suite for the sync subsystem

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
GET  /sync/status             Active sync status and progress
POST /sync/trigger            Queue a manual sync of the selected stages (JSON plan body)
GET  /sync/runs               Recent sync-stage records, newest first
```

## Syncing

On startup the app runs one complete incremental sync unless a complete five-stage batch
already succeeded today (local date). There is no recurring timer — restarting the server
the same day does nothing, and freshness is otherwise driven manually from the `/sync`
page in the frontend, which can select any combination of stages and give video analytics
and traffic sources independent periods.

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

The five sync-only `DEBUG` detail events, each one line emitted after the work
completes (never a paired before/after record, never one line per returned row):

| Event | Where | Fields |
|---|---|---|
| Page fetched | the four `youtube/data_api.py` token-pagination loops | resource, page number, item count, owning entity id where one exists |
| Video processed | the per-video loops in both analytics stages | ordinal/total, `video_id`, rows fetched for that video |
| Video skipped | the two `continue` branches in each analytics stage | ordinal/total, `video_id`, reason (`no_publish_date` or `empty_range`) |
| Request retried | `youtube/analytics_api.py::_analytics_query()` | attempt number, HTTP status, classified reason (`server` or `quota`), delay |
| FX rates downloaded | `sync/stages.py::sync_fx_rates()` | requested start/end dates, days written, or the no-work condition |

Every logged field is an identifier, counter, or date. Records never carry pagination
tokens, video/playlist titles, descriptions, thumbnails, statistics payloads,
credentials, OAuth tokens, request/response bodies, or raw exception text — failure
records use only the exception's class name and source location.

`APP_LOG_PATH`/`SYNC_LOG_PATH` in `.env.example` document the defaults but, like
`DB_PATH` and `CLIENT_SECRET_PATH` beside them, are not read by any code; changing a log
destination means editing the `_APP_LOG_PATH`/`_SYNC_LOG_PATH` constants in
`logging_config.py`. There is no rotation or retention — both files grow indefinitely
and are safe to delete between runs, since nothing reads them back.

## Testing

```bash
python -m unittest discover -s tests
```

Stage execution and external APIs are mocked; the checkpoint tests run against a
throwaway SQLite file, and the logging tests redirect both log files to a
`TemporaryDirectory`, so no test touches `data/youtube.db`, `data/*.log`, or the
network.

## Dependencies

- `fastapi` — web framework
- `uvicorn` — ASGI server
- `google-api-python-client` — YouTube Data + Analytics API
- `google-auth-oauthlib` — OAuth2 flow
- `httpx2` — required by `starlette.testclient` for the test suite only
- `pydantic-settings` — `.env` config management
