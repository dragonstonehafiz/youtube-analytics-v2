# API Reference

## Purpose

Public FastAPI contracts: every route, its parameters, defaults, and response shape. This is the single source of truth for what the frontend can call — `frontend.md` links here rather than restating parameter lists. Aggregation/zero-fill/filter *semantics* referenced below are defined in `database.md`; this file states which endpoint uses which semantic, not how it's computed.

## Authoritative source files

- `backend/routes.py`
- `backend/database.py` (response-producing helpers only — see `database.md` for their internals)

## Contents

- [Conventions](#conventions)
- [Videos](#videos)
- [Playlists](#playlists)
- [Channel analytics](#channel-analytics)
- [Playlist analytics](#playlist-analytics)
- [Metadata](#metadata)
- [Synchronization](#synchronization)
- [Route-order and compatibility constraints](#route-order-and-compatibility-constraints)

## Conventions

- All list endpoints return `{ items: [...] }`; paginated endpoints additionally return `{ total, page, page_size }`.
- Date filters are always optional query params named `start_date`/`end_date` (ISO `YYYY-MM-DD`).
- `content_type` ∈ `video` | `short`; `privacy_status` ∈ `public` | `private` | `unlisted`. Both are optional filters on nearly every endpoint below.
- 404s are raised explicitly wherever a route takes a `video_id`/`playlist_id` path param and the row doesn't exist (`routes.py`, every playlist-scoped and single-video route).

## Videos

```
GET  /videos
  ?page=1, page_size=50 (max 200), sort_by=published_at, sort_dir=desc,
   title, start_date, end_date, content_type, privacy_status
  sort_by ∈ published_at | view_count | comment_count | total_revenue_sgd
  → { items: Video[], total, page, page_size }
  Video.total_revenue_sgd / total_watch_time_hours are lifetime sums (no date filter applied) — see database.md

GET  /videos/stats
  ?title, start_date, end_date, content_type, privacy_status
  → VideoStats (see frontend.md for the type)
  start_date/end_date set the Legacy/New publication split and the video_analytics date window for period
  views/earnings — see database.md. Comments and privacy-status counts are always current lifetime totals,
  never date-restricted. Omitting both dates uses the full available dataset.

GET  /videos/published
  ?start_date, end_date, content_type, privacy_status, playlist_id
  → { items: PublishedVideo[] }   # id, title, published_at, thumbnail_url, content_type only
  Filters on published_at, not analytics date. No pagination.
  MUST be declared before /videos/{id} in routes.py (path-matching order) — see below.

GET  /videos/{video_id}
  → { item: Video } | 404

GET  /videos/{video_id}/analytics
  ?start_date, end_date
  → { items: AnalyticsRow[] }   # grouped by date; content_type is constant (the video's own type)
  | 404 if video not found

GET  /videos/{video_id}/traffic-sources
  ?start_date, end_date
  → { items: TrafficSourceRow[] }   # daily, per traffic source type; filters vts.date, not published_at
  | 404 if video not found
```

## Playlists

```
GET  /playlists
  ?page=1, page_size=50 (max 200), sort_by=last_item_added, sort_dir=desc, title, start_date, end_date
  sort_by ∈ last_item_added | published_at | item_count | total_views | total_earnings_sgd
  → { items: Playlist[], total, page, page_size }
  Each row includes last_item_added, total_views, total_earnings_sgd (aggregated, see database.md)

GET  /playlists/{playlist_id}
  → { item: Playlist } | 404   # same aggregated fields as above

GET  /playlists/{playlist_id}/videos/stats
  ?title, start_date, end_date, content_type, privacy_status
  → VideoStats | 404 if playlist not found
  Same semantics as GET /videos/stats, scoped to the playlist's member videos (deduplicated by video ID).

GET  /playlists/{playlist_id}/videos
  ?page=1, page_size=50 (max 200), sort_by=published_at, sort_dir=desc,
   title, start_date, end_date, content_type, privacy_status
  sort_by ∈ published_at | view_count | comment_count | total_revenue_sgd
  → { items: Video[], total, page, page_size } | 404 if playlist not found
```

## Channel analytics

```
GET  /analytics/videos
  ?start_date, end_date, content_type, privacy_status   (no title filter)
  → { items: AnalyticsRow[] }
  Grouped by (date, content_type); date filters va.date, not published_at.
  Video and short rows for the same date are separate entries, zero-filled independently per content_type.

GET  /analytics/videos/top
  ?start_date, end_date, content_type, privacy_status
  → { items: TopVideo[] }   # top 10 videos by views, channel-wide
  Views/earnings/watch time are summed within the given period only — not lifetime.

GET  /analytics/traffic-sources
  ?start_date, end_date, content_type, privacy_status   (no title filter)
  → { items: TrafficSourceRow[] }   # channel-wide, daily; date filters vts.date

GET  /analytics/traffic-sources/top
  ?start_date, end_date, content_type, privacy_status
  → { items: Record<traffic_source_type, TrafficSourceTopVideo[]> }
  Top 10 per traffic source type, channel-wide. limit=10 is passed explicitly by routes.py
  — the underlying database.get_top_videos_by_traffic_source() itself defaults to limit=3.
```

## Playlist analytics

```
GET  /analytics/playlists/{playlist_id}
  ?start_date, end_date, content_type, privacy_status   (no title filter)
  → { items: AnalyticsRow[] } | 404 if playlist not found
  Same one-row-per-(date, content_type) semantics as /analytics/videos, scoped to the playlist.

GET  /analytics/playlists/{playlist_id}/top
  ?start_date, end_date, content_type, privacy_status
  → { items: TopVideo[] } | 404 if playlist not found   # top 10 by views, within the playlist

GET  /analytics/playlists/{playlist_id}/traffic-sources
  ?start_date, end_date, content_type, privacy_status   (no title filter)
  → { items: TrafficSourceRow[] } | 404 if playlist not found

GET  /analytics/playlists/{playlist_id}/traffic-sources/top
  ?start_date, end_date, content_type, privacy_status
  → { items: Record<traffic_source_type, TrafficSourceTopVideo[]> } | 404 if playlist not found
  Same explicit limit=10 note as the channel-wide equivalent above.
```

## Metadata

```
GET  /meta/date-range
  → { earliest_year: number | null }   # earliest published_at year across videos (playlists excluded)
```

## Synchronization

```
GET  /sync/status
  → { is_syncing, last_synced_at, message }

POST /sync/trigger
  ?scope=incremental (| year | all), year (int, required if scope=year)
  → { queued: true }
  409 if a sync is already in progress
  400 if scope is invalid, or scope=year without year
  Actual sync runs via FastAPI BackgroundTasks — response returns before the sync completes.

GET  /sync/runs
  ?limit=100 (1-500)
  → { items: SyncRun[] }   # newest first
  SyncRun: { id, batch_id, sync_type, scope, year, status, started_at, completed_at,
             rows_fetched, rows_written, rows_deleted, error_message }
  sync_type ∈ videos | playlists | video_analytics | video_traffic_sources | fx_rates
  status ∈ running | success | failed
```

## Route-order and compatibility constraints

- **`/videos/published` must be declared before `/videos/{video_id}`** in `routes.py` — FastAPI matches routes in declaration order, and a literal path segment (`published`) would otherwise be captured by the `{video_id}` path parameter on an earlier-declared dynamic route. Confirmed current order in `routes.py` has `/videos/published` (line 44) before `/videos/{video_id}` (line 57).
- Frontend's `api.ts` exposes two identically-implemented functions for the same endpoint — `getPlaylistAnalytics(id, params)` and `getPlaylistAggregatedAnalytics(id, params)` both call `GET /analytics/playlists/{id}` with no difference in behavior. Only `getPlaylistAnalytics` is actually used by `PlaylistAnalytics.tsx`; treat the other as a redundant alias, not a second endpoint.
- Adding a new sortable column to any `sort_by` requires updating the backend's allow-list (`_VIDEO_SORT_COLUMNS` / `_PLAYLIST_SORT_COLUMNS` in `database.py`, see `database.md`) — an unrecognized value is silently ignored (falls back to the default sort) rather than rejected with an error.
