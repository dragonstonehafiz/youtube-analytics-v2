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

On first run, a browser window will open for YouTube OAuth. The token is saved to `secrets/token.json` for subsequent runs.

The server runs on `http://127.0.0.1:8000`

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Structure

```
backend/
  server.py      # FastAPI app entry point
  schema.sql     # Database table definitions
  database.py    # DB connection and all helpers
  youtube.py     # YouTube Data + Analytics API clients and fetchers
  sync.py        # Background sync scheduler
  routes.py      # All API endpoints
```

## Endpoints

```
GET  /videos                  List all videos
GET  /videos/{id}             Single video detail
GET  /videos/{id}/analytics   Daily analytics for a video
GET  /playlists               List all playlists
GET  /playlists/{id}/videos   Videos in a playlist
GET  /sync/status             Sync status and last synced timestamp
POST /sync/trigger            Manually trigger a sync
```

## Dependencies

- `fastapi` — web framework
- `uvicorn` — ASGI server
- `google-api-python-client` — YouTube Data + Analytics API
- `google-auth-oauthlib` — OAuth2 flow
- `pydantic-settings` — `.env` config management
