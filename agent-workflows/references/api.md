# API Reference

## Purpose

Public FastAPI contracts: every route, its parameters, defaults, and response shape. This is the single source of truth for what the frontend can call — `frontend.md` links here rather than restating parameter lists. Aggregation/zero-fill/filter *semantics* referenced below are defined in `database.md`; this file states which endpoint uses which semantic, not how it's computed.

## Authoritative source files

- `backend/routes/videos.py`, `backend/routes/playlists.py`, `backend/routes/analytics.py`, `backend/routes/synchronization.py`, `backend/routes/metadata.py` (`backend/routes/__init__.py` aggregates these into one `router`, in that order)
- `backend/database/` (response-producing helpers only — see `database.md` for their internals)

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
- 404s are raised explicitly wherever a route takes a `video_id`/`playlist_id` path param and the row doesn't exist (every playlist-scoped route in `routes/playlists.py`/`routes/analytics.py` and every single-video route in `routes/videos.py`).

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
  MUST be declared before /videos/{id} in routes/videos.py (path-matching order) — see below.

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
  ?start_date, end_date, content_type, privacy_status, sort_by=views
  sort_by ∈ views | watch_time   (default: views; invalid values → 422)
  → { items: TopVideo[] }   # top 10 videos, channel-wide, ranked by the selected sort
  Each TopVideo has period_views, period_watch_time_hours, period_earnings_sgd — all summed
  within the given period only (not lifetime); ranking happens in SQL before LIMIT.

GET  /analytics/traffic-sources
  ?start_date, end_date, content_type, privacy_status   (no title filter)
  → { items: TrafficSourceRow[] }   # channel-wide, daily; date filters vts.date

GET  /analytics/traffic-sources/top
  ?start_date, end_date, content_type, privacy_status
  → { items: Record<traffic_source_type, TrafficSourceTopVideo[]> }
  Top 10 per traffic source type, channel-wide. limit=10 is passed explicitly by routes/analytics.py
  — the underlying database.get_top_videos_by_traffic_source() itself defaults to limit=3.
```

## Playlist analytics

```
GET  /analytics/playlists/{playlist_id}
  ?start_date, end_date, content_type, privacy_status   (no title filter)
  → { items: AnalyticsRow[] } | 404 if playlist not found
  Same one-row-per-(date, content_type) semantics as /analytics/videos, scoped to the playlist.

GET  /analytics/playlists/{playlist_id}/top
  ?start_date, end_date, content_type, privacy_status, sort_by=views
  sort_by ∈ views | watch_time   (default: views; invalid values → 422)
  → { items: TopVideo[] } | 404 if playlist not found   # top 10 within the playlist, ranked by the selected sort
  Same TopVideo shape and period-based aggregation semantics as /analytics/videos/top.

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
  → { is_syncing, message }

POST /sync/trigger
  Body (JSON): { stages: [ { stage, scope?, year? }, ... ] }
    stage ∈ videos | playlists | pruning | video_analytics | video_traffic_sources | fx_rates
    scope ∈ incremental | year | all   # video_analytics / video_traffic_sources only,
                                       # required for those two, forbidden on the rest
    year  (int)                        # required with scope=year, forbidden otherwise
  → { queued: true }
  422 malformed body, missing `stages`, unknown stage, unknown scope, non-numeric year
  400 empty `stages`, duplicate stage, missing/misapplied scope or year, unavailable year,
      `pruning` submitted without both `playlists` and `videos` in the same plan
  409 a sync is already in progress
  Each period-aware stage carries its own scope/year — the two can differ in one plan.
  Submission order is irrelevant: the backend always executes in canonical stage order
  (playlists → videos → pruning → video_analytics → video_traffic_sources → fx_rates).
  `pruning` is the only stage that deletes video rows (cascades to video_analytics/
  video_traffic_sources) and is never selected automatically — omit it from a plan and
  nothing is deleted.
  Active state is reserved before the response, so two concurrent requests cannot both
  be told they were queued. Actual sync runs via FastAPI BackgroundTasks — the response
  returns before the sync completes.

GET  /sync/runs
  ?limit=100 (1-500)
  → { items: SyncRun[] }   # newest first
  SyncRun: { id, batch_id, sync_type, scope, year, status, started_at, completed_at,
             rows_fetched, rows_written, rows_deleted, error_message }
  sync_type ∈ videos | playlists | pruning | video_analytics | video_traffic_sources | fx_rates
  status ∈ running | success | failed
  Only stages that actually started have rows; a plan's rows share one batch_id.
```

## Route-order and compatibility constraints

- **`/videos/published` must be declared before `/videos/{video_id}`** in `routes/videos.py` — FastAPI matches routes in declaration order, and a literal path segment (`published`) would otherwise be captured by the `{video_id}` path parameter on an earlier-declared dynamic route. Confirmed current order in `routes/videos.py` has `/videos/published` (line 47) before `/videos/{video_id}` (line 60). `routes/__init__.py` includes the five sub-routers in a fixed order (videos, playlists, analytics, synchronization, metadata), but that inter-file order carries no matching-order risk here since no two files declare overlapping path prefixes with the same ambiguity — only the intra-file `/videos/published` vs `/videos/{video_id}` ordering matters.
- Frontend's `api.ts` exposes two identically-implemented functions for the same endpoint — `getPlaylistAnalytics(id, params)` and `getPlaylistAggregatedAnalytics(id, params)` both call `GET /analytics/playlists/{id}` with no difference in behavior. Only `getPlaylistAnalytics` is actually used by `PlaylistAnalytics.tsx`; treat the other as a redundant alias, not a second endpoint.
- Adding a new sortable column to any `sort_by` requires updating the backend's allow-list (`database/videos.py`'s `VIDEO_SORT_COLUMNS` / `database/playlists.py`'s `_PLAYLIST_SORT_COLUMNS`, see `database.md`) — an unrecognized value is silently ignored (falls back to the default sort) rather than rejected with an error.
- The Top Videos routes' `sort_by` is different: it's typed `Literal["views", "watch_time"]` in `routes/analytics.py`, so FastAPI rejects an invalid value with 422 instead of silently falling back. The DB helpers (`get_top_videos_by_views()` / `get_playlist_top_videos_by_views()`, in `database/analytics.py`) still fall back to `"views"` defensively if called directly with an unrecognized value — see `database.md`.
- Frontend repository call sites (`api.ts`'s `getTopVideosByViews()` / `getPlaylistTopVideosByViews()`) require an explicit `TopVideoSortBy` argument with no default, so a missed call site fails `tsc` rather than silently sending the wrong sort. The backend route still defaults to `views` for external API consumers that omit `sort_by`.
