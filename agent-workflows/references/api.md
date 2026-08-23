# API Reference

## Purpose

Public FastAPI contracts: every route, its parameters, defaults, and response shape. This is the single source of truth for what the frontend can call — `frontend.md` links here rather than restating parameter lists. Aggregation/zero-fill/filter *semantics* referenced below are defined in `database.md`; this file states which endpoint uses which semantic, not how it's computed.

## Authoritative source files

- `backend/routes/videos.py`, `backend/routes/playlists.py`, `backend/routes/analytics.py`, `backend/routes/comments.py`, `backend/routes/synchronization.py`, `backend/routes/metadata.py` (`backend/routes/__init__.py` aggregates these into one `router`, in that order)
- `backend/database/` (response-producing helpers only — see `database.md` for their internals)

## Contents

- [Conventions](#conventions)
- [Videos](#videos)
- [Playlists](#playlists)
- [Channel analytics](#channel-analytics)
- [Playlist analytics](#playlist-analytics)
- [Comments](#comments)
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
  ?start_date, end_date, content_type, privacy_status, playlist_id, title
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
  ?start_date, end_date, content_type, privacy_status, title
  → { items: AnalyticsRow[] }
  Grouped by (date, content_type); date filters va.date, not published_at.
  Video and short rows for the same date are separate entries, zero-filled independently per content_type.

GET  /analytics/videos/top
  ?start_date, end_date, content_type, privacy_status, sort_by=views, title
  sort_by ∈ views | watch_time   (default: views; invalid values → 422)
  → { items: TopVideo[] }   # top 10 videos, channel-wide, ranked by the selected sort
  Each TopVideo has period_views, period_watch_time_hours, period_earnings_sgd — all summed
  within the given period only (not lifetime); ranking happens in SQL before LIMIT.

GET  /analytics/traffic-sources
  ?start_date, end_date, content_type, privacy_status, title
  → { items: TrafficSourceRow[] }   # channel-wide, daily; date filters vts.date

GET  /analytics/traffic-sources/top
  ?start_date, end_date, content_type, privacy_status, title
  → { items: Record<traffic_source_type, TrafficSourceTopVideo[]> }
  Top 10 per traffic source type, channel-wide. limit=10 is passed explicitly by routes/analytics.py
  — the underlying database.get_top_videos_by_traffic_source() itself defaults to limit=3.
```

## Playlist analytics

```
GET  /analytics/playlists/{playlist_id}
  ?start_date, end_date, content_type, privacy_status, title
  → { items: AnalyticsRow[] } | 404 if playlist not found
  Same one-row-per-(date, content_type) semantics as /analytics/videos, scoped to the playlist.

GET  /analytics/playlists/{playlist_id}/top
  ?start_date, end_date, content_type, privacy_status, sort_by=views, title
  sort_by ∈ views | watch_time   (default: views; invalid values → 422)
  → { items: TopVideo[] } | 404 if playlist not found   # top 10 within the playlist, ranked by the selected sort
  Same TopVideo shape and period-based aggregation semantics as /analytics/videos/top.

GET  /analytics/playlists/{playlist_id}/traffic-sources
  ?start_date, end_date, content_type, privacy_status, title
  → { items: TrafficSourceRow[] } | 404 if playlist not found

GET  /analytics/playlists/{playlist_id}/traffic-sources/top
  ?start_date, end_date, content_type, privacy_status, title
  → { items: Record<traffic_source_type, TrafficSourceTopVideo[]> } | 404 if playlist not found
  Same explicit limit=10 note as the channel-wide equivalent above.
```

Each of these four routes is a thin wrapper over the *same* database helper its channel-wide
counterpart calls — there are no playlist-specific query helpers. Every playlist handler follows one
flow, factored into `_resolve_playlist_video_ids()` in `routes/analytics.py`:

1. `database.get_playlist(playlist_id)` — the sole 404 boundary, raising `404 {"detail": "Playlist not found"}`.
2. `database.get_playlist_video_ids(playlist_id)` — the playlist's distinct, catalog-backed member IDs.
3. the shared helper, called with `video_ids=` those IDs.

The shared analytics queries themselves never join `playlist_items`; the route resolves membership
first (that lookup is the only thing that reads `playlist_items`) and passes the resulting IDs down.
Two consequences are worth stating explicitly:

- An **existing but empty** playlist (no members, or only null/dangling ones) yields an empty ID
  collection, and the shared helpers treat that as "no rows" rather than "no filter" — so the route
  returns `{"items": []}` (or `{"items": {}}` for the traffic-sources/top route), never channel-wide data.
  A **nonexistent** playlist is caught in step 1 and never reaches the query at all.
- Duplicate `playlist_items` rows for the same video cannot inflate playlist totals, since membership
  is deduplicated before the query sees it (see `database.md`).

The public surface is unchanged by that internal sharing: the channel and playlist paths remain
separate endpoints with their own query parameters, response envelopes, error behavior, and explicit
`limit=10` on the two top routes.

All nine routes above (the four channel-analytics routes, `/videos/published`, and the four
playlist-analytics routes) accept `title` as an optional query parameter, applying the same
parameterized `v.title LIKE ?` (bound to `%{title}%`) case-insensitive partial-match predicate as `/videos` and
`/videos/stats` (see `database.md`) — combined with any other supplied filters via `AND`, and,
on playlist routes, with the video-ID scope. Omitting `title` produces
identical results to before this filter existed.

## Comments

Read-only: `routes/comments.py` declares `GET` handlers and nothing else, so every other
method on these paths is a `405`. There are no comment mutation or moderation endpoints.

```
GET  /comments
  ?page=1, page_size=50 (max 200), sort_by=newest,
   text, video_title, author, start_date, end_date, content_type
  sort_by ∈ newest | oldest | likes — a value outside that set is a 422, not a silent fallback
  → { items: Comment[], total, page, page_size }
  text/video_title/author are case-insensitive substring matches on the comment body, the parent
  video's title, and the commenter's display name. start_date/end_date filter the comment's own
  published_at, not the video's. Every row carries the joined author snapshot plus video_title,
  video_content_type, and video_thumbnail_url — see database.md.

GET  /comments/videos/{video_id}
  ?page=1, page_size=50 (max 200), sort_by=newest, text, author, start_date, end_date
  → { items: Comment[], total, page, page_size } | 404 if video not found
  Accepts no video_title or content_type filter: a fixed video determines both.

GET  /comments/playlists/{playlist_id}
  ?page=1, page_size=50 (max 200), sort_by=newest,
   text, video_title, author, start_date, end_date, content_type
  → { items: Comment[], total, page, page_size } | 404 if playlist not found
  A video listed twice in the playlist still yields each of its comments once — see database.md.
```

Only top-level comments are served. Reply bodies are never fetched or stored; each row's
`total_reply_count` is the thread's reply count as metadata (see `sync.md`).

## Metadata

```
GET  /meta/date-range
  → { earliest_year: number | null }   # earliest published_at year across videos (playlists excluded)
```

## Synchronization

```
GET  /sync/status
  → { state, message }
    state ∈ idle | running | success | failed
    message is a safe, operation-specific string; on failure it never contains raw
    exception text, headers, credentials, tokens, or API response content.
    A terminal result (success/failed) is retained until the next reservation replaces
    it with running; a fresh backend starts idle with no message.

POST /sync/trigger
  Body (JSON): { stages: [ { stage, scope?, year? }, ... ] }
    stage ∈ videos | playlists | comments | pruning | video_analytics |
            video_traffic_sources | fx_rates
    scope ∈ incremental | year | all   # video_analytics / video_traffic_sources only,
                                       # required for those two, forbidden on the rest
                                       # except comments, which takes incremental | all
                                       # (optional; omitted means incremental)
    year  (int)                        # required with scope=year, forbidden otherwise —
                                       # and always rejected on comments
  → { queued: true }
  422 malformed body, missing `stages`, unknown stage, unknown scope, non-numeric year
  400 empty `stages`, duplicate stage, missing/misapplied scope or year, unavailable year,
      `pruning` submitted without both `playlists` and `videos` in the same plan
  409 a sync is already in progress
  Each period-aware stage carries its own scope/year — the two can differ in one plan.
  Submission order is irrelevant: the backend always executes in canonical stage order
  (playlists → videos → comments → pruning → video_analytics → video_traffic_sources →
  fx_rates).
  `comments` only inserts and updates; scope=all re-reads full comment history but still
  deletes no comments (see sync.md).
  `pruning` is the only stage that deletes video rows (cascades to video_analytics/
  video_traffic_sources) and is never selected automatically — omit it from a plan and
  nothing is deleted.
  Active state is reserved before the response, so two concurrent requests cannot both
  be told they were queued. Actual sync runs via FastAPI BackgroundTasks — the response
  returns before the sync completes.

GET  /sync/runs
  ?page=1 &page_size=25 (1-200)
  → { items: SyncRunBatch[], total, page, page_size }   # newest batch first
  SyncRunBatch: { batch_id, started_at, run_count,
                  rows_fetched, rows_written, rows_deleted, runs: SyncRun[] }
  SyncRun: { id, batch_id, sync_type, scope, year, status, started_at, completed_at,
             rows_fetched, rows_written, rows_deleted, error_message }
  One item per batch_id — the ID execute_plan() shares across every stage of one
  submitted plan. page/page_size/total count BATCHES, not stage rows; a batch is
  never split across pages. started_at is the batch's earliest stage start;
  run_count and the three counters are summed from exactly the rows in `runs`,
  so a group's totals always match its own children. Children are newest first.
  Stages that never started have no row, so run_count omits them.
  error_message and batch_id are part of the contract but are never rendered.
  sync_type ∈ videos | playlists | comments | pruning | video_analytics |
              video_traffic_sources | fx_rates
  status ∈ running | success | failed
  Only stages that actually started have rows; a plan's rows share one batch_id.
```

## Route-order and compatibility constraints

- **`/videos/published` must be declared before `/videos/{video_id}`** in `routes/videos.py` — FastAPI matches routes in declaration order, and a literal path segment (`published`) would otherwise be captured by the `{video_id}` path parameter on an earlier-declared dynamic route. Confirmed current order in `routes/videos.py` has `/videos/published` (line 47) before `/videos/{video_id}` (line 60). `routes/__init__.py` includes the six sub-routers in a fixed order (videos, playlists, analytics, comments, synchronization, metadata), but that inter-file order carries no matching-order risk here since no two files declare overlapping path prefixes with the same ambiguity — only the intra-file `/videos/published` vs `/videos/{video_id}` ordering matters. The comments routes are likewise unambiguous: `/comments` has no dynamic sibling, and `/comments/videos/{id}` and `/comments/playlists/{id}` are distinguished by a literal second segment.
- Frontend's `api.ts` exposes two identically-implemented functions for the same endpoint — `getPlaylistAnalytics(id, params)` and `getPlaylistAggregatedAnalytics(id, params)` both call `GET /analytics/playlists/{id}` with no difference in behavior. Only `getPlaylistAnalytics` is actually used by `PlaylistAnalytics.tsx`; treat the other as a redundant alias, not a second endpoint.
- Adding a new sortable column to any `sort_by` requires updating the backend's allow-list (`database/videos.py`'s `VIDEO_SORT_COLUMNS` / `database/playlists.py`'s `_PLAYLIST_SORT_COLUMNS`, see `database.md`) — an unrecognized value is silently ignored (falls back to the default sort) rather than rejected with an error.
- The Top Videos routes' `sort_by` is different: it's typed `Literal["views", "watch_time"]` in `routes/analytics.py`, so FastAPI rejects an invalid value with 422 instead of silently falling back. The DB helper (`get_top_videos_by_views()`, in `database/analytics.py`) still falls back to `"views"` defensively if called directly with an unrecognized value — see `database.md`.
- Frontend repository call sites (`api.ts`'s `getTopVideosByViews()` / `getPlaylistTopVideosByViews()`) require an explicit `TopVideoSortBy` argument with no default, so a missed call site fails `tsc` rather than silently sending the wrong sort. The backend route still defaults to `views` for external API consumers that omit `sort_by`.
