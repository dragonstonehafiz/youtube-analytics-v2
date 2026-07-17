# YouTube Analytics

A local dashboard for analysing your own YouTube channel — video and Shorts performance, playlists, earnings, and traffic sources, backed by a background sync from the YouTube Data and Analytics APIs.

## Features

- Dashboard with top videos, top Shorts, latest uploads, and a traffic-source overview
- Sortable, filterable tables for videos and playlists
- Channel-wide, per-video, and per-playlist analytics
- Daily, weekly, and monthly charts, with a cumulative-total mode
- Views, watch time, and estimated earnings (converted to SGD)
- Traffic-source charts, breakdown tables, and top-performing videos per source
- Filter by date range, content type (video/Short), and privacy status
- Automatic sync every 24 hours, plus manual sync (incremental, a specific year, or full resync)

## Prerequisites

- Python 3.12
- Node.js and npm
- A Google Cloud project with **YouTube Data API v3** and **YouTube Analytics API** enabled
- OAuth 2.0 **Desktop app** credentials for that project, with access to monetary analytics scopes
- Optional: [`uv`](https://github.com/astral-sh/uv) for the backend virtual environment, Docker for containerized setup

## Local setup

1. Download your OAuth credentials from Google Cloud Console and save them as `backend/secrets/client_secret.json`.
2. Copy `backend/.env.example` to `backend/.env` (defaults work out of the box).

### Backend

```bash
cd backend
uv venv --python 3.12
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux
uv pip install -r requirements.txt
python server.py
```

Backend runs on `http://127.0.0.1:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`.

## First run and sync

On first backend startup, a browser window opens for the OAuth consent flow. The resulting token is saved to `backend/secrets/token.json` and reused on future runs; the SQLite database is created at `backend/data/youtube.db`.

The initial sync pulls your channel's full history and can take a while for larger channels. After that, a background sync runs automatically every 24 hours, pulling only new data. You can also trigger a sync manually from the dashboard, choosing incremental (new data only), a specific year, or a full resync.

## Docker

Make sure `backend/secrets/client_secret.json` and `backend/.env` exist (see Local setup above), then:

```bash
docker-compose -p youtube-analytics up --build
```

Backend on `http://127.0.0.1:8000`, frontend on `http://localhost:5173`.
