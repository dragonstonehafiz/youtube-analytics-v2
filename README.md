# YouTube Analytics

[![CI](https://github.com/dragonstonehafiz/youtube-analytics-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/dragonstonehafiz/youtube-analytics-v2/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/dragonstonehafiz/youtube-analytics-v2)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-22-339933?logo=nodedotjs&logoColor=white)](https://nodejs.org/)

A local dashboard for analysing your own YouTube channel showing video and Shorts performance, playlists, earnings, and traffic sources, backed by a background sync from the YouTube Data and Analytics APIs.

## Features

- Dashboard with top videos, top Shorts, latest uploads, and a traffic-source overview
- Sortable, filterable tables for videos and playlists
- Channel-wide, per-video, and per-playlist analytics
- Daily, weekly, and monthly charts, with a cumulative-total mode
- Views, watch time, and estimated earnings (converted to SGD)
- Traffic-source charts, breakdown tables, and top-performing videos per source
- Top-level comments, browsable channel-wide or scoped to a video or playlist, with search by comment text, commenter, or video
- Filter by date range, content type (video/Short), and privacy status
- Manual sync from the Sync page (incremental, a specific year, or full resync)

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

The SQLite database is created at `backend/data/youtube.db` when the backend starts. The first sync opens a browser window for the OAuth consent flow; the resulting token is saved to `backend/secrets/token.json` and reused on future runs.

Syncs run only when started from the Sync page — starting the backend does not sync, and there is no schedule. Choose incremental (new data only), a specific year, or a full resync per stage. The first sync pulls your channel's full history and can take a while for larger channels; later incremental syncs pull only new data.

Comments are the one exception to "full history on first sync": the default **Incremental** comments scope imports top-level comments no further back than December 1 of the previous year for a video with none stored yet. Choose **All** on the Comments row of the Sync page to pull the rest. Only top-level comments are stored — replies are counted but never downloaded.

An active sync can be stopped from the Sync page with the **Stop sync** button. Stopping is cooperative: the current request or database write finishes first, so it may take a moment to take effect, and no data already saved is rolled back.

## Docker

Make sure `backend/secrets/client_secret.json` and `backend/.env` exist (see Local setup above), then:

```bash
docker-compose -p youtube-analytics up --build
```

Backend on `http://127.0.0.1:8000`, frontend on `http://localhost:5173`.
