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

## Testing

```bash
python -m unittest discover -s tests -p "test_sync*.py"
```

Stage execution and external APIs are mocked; the checkpoint tests run against a
throwaway SQLite file, so no test touches `data/youtube.db` or the network.

## Dependencies

- `fastapi` — web framework
- `uvicorn` — ASGI server
- `google-api-python-client` — YouTube Data + Analytics API
- `google-auth-oauthlib` — OAuth2 flow
- `httpx2` — required by `starlette.testclient` for the test suite only
- `pydantic-settings` — `.env` config management
