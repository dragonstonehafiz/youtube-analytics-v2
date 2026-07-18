# CLAUDE.md

YouTube analytics dashboard — FastAPI + React/TypeScript + SQLite.

```
YouTube API → Background Sync → SQLite → FastAPI → React Frontend
```

---

### Do
- use parameterized queries in all DB helpers — never string concatenation
- qualify all column names with table aliases in any query that joins multiple tables (e.g. `va.date`, not `date`) — `video_analytics` and `fx_rates` both have a `date` column
- use type hints and docstrings on all backend functions
- use explicit TypeScript types; avoid `any`
- use HTML `<table>` with `table-layout: fixed` for all data tables
- keep CSS in colocated `.css` files; no inline styles
- use `@/` alias imports (e.g. `import { getVideos } from '@/api'`)
- keep `.method()` on same line as object in Python — no chained calls starting on new lines

### Don't
- don't add new heavy dependencies without approval
- don't run project-wide builds when a file-scoped check will do
- don't use `console.log` in frontend code

### FK constraints
- `video_analytics.video_id → videos.id` ON DELETE CASCADE
- `video_traffic_sources.video_id → videos.id` ON DELETE CASCADE
- `playlist_items.playlist_id → playlists.id` ON DELETE CASCADE
- `playlist_items.video_id` has no FK — it's a raw YouTube ID that may not exist in `videos`
- `PRAGMA foreign_keys = ON` is set on every connection in `get_connection()`

---

### Commands

```bash
# Backend — type check a single file
cd backend && python -m mypy database.py

# Backend — run server
cd backend && uvicorn server:app --reload

# Frontend — type check
cd frontend && npx tsc --noEmit

# Frontend — lint a single file
cd frontend && npx eslint src/pages/Videos.tsx --fix

# Frontend — full build (only when explicitly requested)
cd frontend && npm run build
```

---

### Safety and permissions

Allowed without asking:
- read files, list files, search
- type check, lint single files
- run backend server locally

Ask first:
- `pip install` / `npm install` new packages
- `git push` or force-push
- deleting files or DB records
- full project builds

---

### Project structure

```
backend/
  server.py        # FastAPI entry point; lifespan: init_db → start_background_scheduler
  routes.py        # all API route handlers
  sync.py          # sync orchestration; background scheduler (24h loop); global state
  youtube.py       # YouTube API clients (OAuth, fetch videos/playlists/analytics)
  database.py      # all DB helpers (get/upsert per table); every upsert sets updated_at automatically
  schema.sql       # SQLite schema (8 tables)
  token.json       # OAuth token (auto-deleted on invalid_grant, re-created on next auth)
  data.db          # SQLite database

frontend/
  src/
    main.tsx       # entry point
    App.tsx        # BrowserRouter + Routes; TopNav rendered outside Routes
    index.css      # global design tokens + shared CSS classes
    api.ts         # all fetch calls to backend
    types/
      index.ts     # shared TypeScript interfaces (Video, Playlist, AnalyticsRow, TrafficSourceRow,
                   #   SyncState, VideoStats, TopVideo, PublishedVideo)
    lib/
      trafficSources.ts  # formatTrafficSource() (raw API enum -> human label, e.g. YT_SEARCH ->
                   #   "YouTube Search"); getTrafficSourceColor() (fixed Record<type, hex> lookup —
                   #   every traffic source type keeps the same color everywhere it's rendered,
                   #   regardless of rank in any given filtered view); TRAFFIC_SOURCE_OTHER_COLOR
                   #   (grey, also the fallback for unmapped types); aggregateTrafficSourceTotals()
                   #   (sums views/watch_time_minutes per type across all rows, sorted by views desc)
    pages/
      Home.tsx + Home.css              # 3-card grid linking to Videos, Playlists, Analytics, plus a
                                       #   3-column `.home-carousels` grid below it: VideoCarouselCard
                                       #   ×3 (Top Videos/Top Shorts last 28 days, Latest Uploads — all
                                       #   public only) then a 4th item, TrafficSourceDonutCard (last 28
                                       #   days, public only, via getChannelTrafficSources), which wraps
                                       #   to its own row since the grid stays 3 columns
      Videos.tsx                       # sortable table of all videos
      Playlists.tsx                    # sortable table of all playlists
      Analytics.tsx + Analytics.css    # channel-wide analytics with filter bar; two-column
                                       #   `.analytics-layout` grid (1fr 320px) below the stats bar —
                                       #   left column: chart + top-videos list; right column
                                       #   `.analytics-sidebar`: two VideoCarouselCard (Latest Videos /
                                       #   Latest Shorts, public only, independent of the page's filters)
      VideoAnalytics.tsx + VideoAnalytics.css  # single video: meta card + filter bar + tabs
                                       #   (Analytics / Traffic Sources, URL param `tab`, both tabs
                                       #   share the same start_date/end_date filter — no param
                                       #   clearing needed on switch); Analytics tab renders
                                       #   AnalyticsChart, Traffic Sources tab renders
                                       #   TrafficSourceChart + TrafficSourcesTable; no uploadedVideos
                                       #   prop passed to any chart on this page
      PlaylistAnalytics.tsx            # tabbed: Analytics tab, Traffic Sources tab, Videos tab (in that
                                       #   button order)
    components/
      TopNav.tsx + TopNav.css          # sticky glass navbar; no separate "Home" link — the
                                       #   "YouTube Analytics" brand text is itself a button that
                                       #   navigates to `/`; back arrow on detail pages only;
                                       #   SyncStatus in right side of nav on all pages;
                                       #   nav links use replace (no history push)
      SyncStatus.tsx + SyncStatus.css  # polls /sync/status every 5s; shows sync state; when idle,
                                       #   renders plain inline text/controls (no bordered pill wrapper)
                                       #   — last synced date, a scope `<select>` ("New data only" =
                                       #   incremental default, "Full resync" = all, then each year back
                                       #   to `earliest_year` from `/meta/date-range`), and "Sync now";
                                       #   select and button both height 28px/font-size 12px so they
                                       #   align (`.sync-scope-select`/`.sync-trigger-btn` in
                                       #   SyncStatus.css); triggerSync(scope, year) call derives scope
                                       #   from the select value ('incremental'/'all' passed through,
                                       #   anything else treated as a year string and sent as scope=year)
      VideoTable.tsx + VideoTable.css  # shared video table + pagination + filter bar; exports
                                       #   PAGE_SIZE, SortKey, SortDir; parents own URL param state
      VideoStatsBar.tsx + VideoStatsBar.css  # standalone stats bar (5 cols: uploads/views/earnings |
                                       #   videos/video views/video earnings | shorts/short views/
                                       #   short earnings | comments | public/private/unlisted);
                                       #   parents own fetch + placement
      AnalyticsChart.tsx + AnalyticsChart.css  # area chart (recharts AreaChart/Area, type="linear" —
                                       #   straight segments, no curve smoothing) for AnalyticsRow[] data;
                                       #   renders one Area per content_type actually present in the input
                                       #   rows (video = var(--blue), short = amber #f59e0b), determined via
                                       #   a presentTypes Set derived from rows — a single-video page's rows
                                       #   are all one content_type so exactly one line renders; a channel/
                                       #   playlist page with no content_type filter gets both lines (both
                                       #   zero-filled by the backend, see AnalyticsRow above), a content_type-
                                       #   filtered view gets one; a legend row (.analytics-chart-legend in
                                       #   AnalyticsChart.css) is only rendered when more than one series is
                                       #   present; fill is solid at 10% opacity down to the axis, no gradient;
                                       #   chart-type row (Per Bucket/Cumulative Total, thin full-width buttons,
                                       #   under a "Chart Type" section-header) rendered above the bucket-size
                                       #   row (Daily/Weekly/Monthly, same button style, under a "Bucket Size"
                                       #   section-header), which is rendered above the metric buttons —
                                       #   aggregateRows()/bucketKey() pivot rows client-side into one ChartPoint
                                       #   per bucket with independent video_*/short_* fields per metric (weekly
                                       #   buckets start Monday UTC, monthly buckets key on the 1st) before
                                       #   charting, so Video and Shorts are summed into separate buckets, never
                                       #   combined; Cumulative Total mode runs toCumulative() as independent
                                       #   running sums per content_type over the already-bucketed rows (so
                                       #   bucket size still controls the step resolution of the curve, only the
                                       #   final total per series is bucket-size-independent); metric switcher
                                       #   (Views / Watch Time hours / Estimated Earnings SGD) rendered as
                                       #   full-width grouped buttons below the bucket row, each showing the
                                       #   Video+Shorts combined total for the period (totals always computed
                                       #   from unaggregated rows summed across content_type, independent of
                                       #   bucket size and chart type); active metric highlighted with blue
                                       #   underline; tooltip entries are named per-series ("Video"/"Shorts") so
                                       #   both lines are distinguishable on hover; x-axis hidden, quarterly
                                       #   ReferenceLine labels when <8 quarters else yearly (derived from the
                                       #   currently displayed rows); empty rows renders chart-placeholder
                                       #   fallback; watch_time_hours computed client-side from
                                       #   watch_time_minutes; y-axis ticks use formatCompact() — plain number
                                       #   below 1,000, "1.5K"-style (1 decimal) from 1,000, "1.1M"-style from
                                       #   1,000,000; optional uploadedVideos prop (PublishedVideo[]) renders
                                       #   upload strip below chart via shared UploadStrip component (see
                                       #   below); ResizeObserver on card div (always mounted); used by
                                       #   Analytics.tsx and PlaylistAnalytics.tsx (not VideoAnalytics, which
                                       #   has no uploadedVideos to pass, though it still renders one series
                                       #   since its rows are single-content_type)
      UploadStrip.tsx                  # shared upload-indicator infra used by both AnalyticsChart and
                                       #   TrafficSourceChart: formatCompact() (y-axis tick formatter),
                                       #   getMarks() (quarterly/yearly ReferenceLine labels),
                                       #   computeUploadBuckets() (buckets PublishedVideo[] into
                                       #   pixel-width-derived groups along the chart's date range),
                                       #   and <UploadStrip> (renders the badge row + hover popover);
                                       #   YAXIS_WIDTH/CHART_RIGHT/BUCKET_WIDTH constants also live here
      TrafficSourceChart.tsx + TrafficSourceChart.css  # recharts LineChart (not Area) for
                                       #   TrafficSourceRow[] data; mirrors AnalyticsChart's chart
                                       #   controls exactly: a "Chart Type" row (Per Bucket / Cumulative
                                       #   Total, local toCumulative() summing every series key — top 6
                                       #   traffic source types + "Other" — since AnalyticsChart's
                                       #   toCumulative() is hardcoded to AnalyticsRow's fixed fields and
                                       #   isn't reusable here) above a "Bucket Size" row (Daily/Weekly/
                                       #   Monthly via a local bucketKey(), same pattern as
                                       #   AnalyticsChart's bucketKey/aggregateRows) since underlying
                                       #   rows are daily; metric buttons are Views / Watch Time
                                       #   (hours) only — no earnings; top 6 traffic source types by
                                       #   total views become their own colored Line each (color via
                                       #   getTrafficSourceColor()), everything else summed into one
                                       #   grey "Other" line (TRAFFIC_SOURCE_OTHER_COLOR); custom
                                       #   legend row above the chart (not recharts' built-in Legend);
                                       #   reuses YAXIS_WIDTH/CHART_RIGHT/formatCompact/getMarks/
                                       #   computeUploadBuckets/UploadStrip from UploadStrip.tsx and
                                       #   the `.analytics-chart`/`.chart-metric-*` classes from
                                       #   AnalyticsChart.css; optional uploadedVideos prop renders the
                                       #   same upload strip as AnalyticsChart
      TrafficSourcesTable.tsx + TrafficSourcesTable.css  # aggregates TrafficSourceRow[] via
                                       #   aggregateTrafficSourceTotals() (sums across all days in the
                                       #   filtered period) into one row per source type, sorted by
                                       #   views desc; columns: Source | relative bar (width scaled to
                                       #   the max-views source, colored via getTrafficSourceColor()) |
                                       #   Views | Watch Time (hrs) | % (share of total views); renders
                                       #   chart-placeholder fallback when rows is empty
      TrafficSourceTopVideosPanel.tsx + TrafficSourceTopVideosPanel.css  # single card with a pill-button
                                       #   switcher row (color dot + label, one pill per traffic source
                                       #   type, ordered via aggregateTrafficSourceTotals(rows) — same
                                       #   order as TrafficSourcesTable) above a top-10-by-views table
                                       #   (rank | thumbnail | title | views | watch time) for whichever
                                       #   type is selected (internal useState, defaults to the
                                       #   highest-views type); takes rows: TrafficSourceRow[] (for
                                       #   ordering) and bySource: Record<type, TrafficSourceTopVideo[]>
                                       #   (the fetched top-10 data); renders nothing when rows is empty
      PeriodSelect.tsx                 # shared period quick-select (Custom/Last 365/Last 90/Last 28/
                                       #   year list, in that order); fetches earliest year from
                                       #   /meta/date-range; exports last365Dates()/last90Dates()/
                                       #   last28Dates(); component default is Custom (empty dates =
                                       #   no filter) — pages that want a non-Custom default (e.g.
                                       #   Last 28 days) set it themselves via initial URL param state
      TopVideosList.tsx + TopVideosList.css  # shared top-10-videos-by-views table; columns:
                                       #   thumbnail (120×68px) | title (links to /analytics/videos/:id) |
                                       #   upload date | views | earnings SGD; renders nothing when
                                       #   videos array is empty; used by Analytics.tsx and
                                       #   PlaylistAnalytics.tsx analytics tab
      VideoCarouselCard.tsx + VideoCarouselCard.css  # single-video-at-a-time card, one video's
                                       #   thumbnail with a bottom gradient + title overlay (links to
                                       #   /analytics/videos/:id), "Uploaded <years/months/days> ago"
                                       #   (timeSincePublished(), calendar-based diff), then Views /
                                       #   Watch Time (hours) / Earnings (SGD) stat rows (no divider
                                       #   between rows), then Previous/Next arrows + "X/N" page
                                       #   indicator; takes `title` (section-header label) and
                                       #   `videos: TopVideo[]` — deliberately reuses TopVideo's shape
                                       #   rather than its own type; renders nothing when videos is
                                       #   empty; self-contained carousel index via useState; used by
                                       #   Home.tsx and Analytics.tsx
      TrafficSourceDonutCard.tsx + TrafficSourceDonutCard.css  # single card, same footprint as
                                       #   VideoCarouselCard (`.traffic-donut` padding matches
                                       #   `.video-carousel`); recharts donut (Pie with innerRadius/
                                       #   outerRadius, no gradient) of aggregated views per traffic
                                       #   source type, center label = total views; top 6 types by
                                       #   views get their own colored slice (getTrafficSourceColor()),
                                       #   everything else rolled into one grey "Other" slice
                                       #   (TRAFFIC_SOURCE_OTHER_COLOR) — same TOP_N=6 grouping as
                                       #   TrafficSourceChart; legend below the donut lists the top 6
                                       #   with % share, then (if any rows were rolled up) an "Other
                                       #   includes:" divider followed by each rolled-up type's own
                                       #   name + % share, so "Other" is never an opaque bucket; takes
                                       #   `title` and `rows: TrafficSourceRow[]` (no fetch of its own,
                                       #   parent fetches and passes rows — same pattern as
                                       #   TrafficSourcesTable/TrafficSourceChart); renders nothing when
                                       #   rows is empty or total views is 0; used by Home.tsx, wraps to
                                       #   a second row below the 3-column carousel grid
```

---

### Database schema (8 tables)

```sql
videos           -- id, title, description, published_at, duration_seconds, thumbnail_url,
                 --   content_type, privacy_status, view_count, like_count, comment_count, updated_at
video_analytics  -- video_id, date, views, watch_time_minutes, estimated_revenue,
                 --   average_view_duration_seconds, average_view_percentage,
                 --   likes, subscribers_gained, subscribers_lost, updated_at
video_traffic_sources -- video_id, date, traffic_source_type, views, watch_time_minutes, updated_at
                 --   (daily — one row per traffic source type per day)
playlists        -- id, title, description, published_at, thumbnail_url, item_count, updated_at
playlist_items   -- id, playlist_id, video_id, position, updated_at
sync_state       -- key, value  (persists last_synced_at across restarts)
fx_rates         -- date, usd_to_sgd, updated_at  (daily USD→SGD close rate; weekends/holidays forward-filled)
sync_runs        -- id, batch_id, sync_type, scope, year, status, started_at, completed_at,
                 --   rows_fetched, rows_written, rows_deleted, error_message
                 --   (one row per sync stage per run_sync() call; see Sync pipeline below)
```

`updated_at` (TEXT, UTC ISO 8601, e.g. `2026-07-17T08:30:45.123456+00:00`) is set automatically by every upsert helper in `database.py` via `_now()` and `excluded.updated_at` — it reflects "last successfully pulled and upserted," not "last changed," so it updates even when a re-fetched row's values are identical to what's already stored. Not present on `sync_state` (state values, not synced source records) or `sync_runs` (has its own `started_at`/`completed_at`).

---

### Sync pipeline

Single sync: `videos → playlists → video analytics → video traffic sources → fx rates` (runs on startup only if last sync was >24h ago or never, then repeats every 24h via daemon thread). If last sync was recent, the first run is scheduled for the remaining time in the 24h window.

Key behaviors:
- `sync.py` exposes `get_status() → {is_syncing, last_synced_at, message}`; `_is_syncing` is a module-level bool guarded by `threading.Lock`
- `last_synced_at` persisted in `sync_state` table so it survives restarts — this is a single global checkpoint used only to decide "was the last full sync more than 24h ago" for the scheduler; it is not a per-row or per-date audit trail (see `sync_runs` below for that)
- `run_sync(scope="incremental"|"year"|"all", year=None)` — `scope`/`year` only affect `_sync_video_analytics` and `_sync_video_traffic_sources` (videos, playlists, fx rates always sync incrementally regardless of scope); raises `ValueError` if `scope="year"` and `year` is `None`; the background 24h scheduler always calls `run_sync()` with defaults (`scope="incremental"`)
- each `run_sync()` call generates one `batch_id` (UUID) shared by all five stages; each stage (`videos`, `playlists`, `video_analytics`, `video_traffic_sources`, `fx_rates`) is wrapped by `_run_stage()`, which creates a `sync_runs` row (`status="running"`) before the stage starts and marks it `"success"`/`"failed"` on completion via `database.complete_sync_run()`/`fail_sync_run()`; `last_synced_at` is only updated after every stage succeeds
- each stage accumulates a mutable `SyncCounts(rows_fetched, rows_written, rows_deleted)` incrementally as rows are fetched/upserted/deleted inside its loop — not computed from a return value at the end — so if a stage raises partway through (e.g. video 200 of 378), the `sync_runs` row for that stage still reflects accurate partial totals rather than zeros; the exception is always re-raised after recording failure, so `run_sync()`'s overall try/finally behavior is unchanged
- for `videos`/`playlists`/`fx_rates`, `sync_runs.scope` is always `"incremental"` and `year` is `NULL`; for `video_analytics`/`video_traffic_sources`, `scope`/`year` reflect whatever was passed into `run_sync()`
- the playlists stage's `rows_deleted` sums `delete_playlist_items()`'s return value across every playlist in the loop (each playlist's items are deleted and re-inserted on every sync) plus `delete_playlists_not_in()`'s return value — cascaded FK deletes (e.g. `video_analytics`/`video_traffic_sources` rows removed when a video itself is deleted) are not counted, only rows these helpers directly report via `cursor.rowcount`
- `_sync_videos`: collects all videos into memory first, then upserts all, then deletes DB videos not in the fetched set (cascades to `video_analytics`, `video_traffic_sources`)
- `_sync_playlists`: collects all playlists + items into memory first, then upserts all, then deletes DB playlists not in the fetched set (cascades to `playlist_items`)
- `_sync_video_analytics(scope, year)`: `scope="incremental"` resumes per-video from `get_last_analytics_date(video_id)` (safe to Ctrl+C mid-sync); `scope="year"` refetches `{year}-01-01`–`{year}-12-31` clamped to `[publish_date, yesterday]`; `scope="all"` refetches `publish_date`–yesterday; in all cases the video is skipped entirely (`continue`, zero API calls) if the resulting `start > range_end` — this is what keeps a video from being queried before it was published even when an unrelated `year` is requested; unlike traffic sources below, incremental mode has **no lookback window** — a day is never re-fetched once synced once, so if that day's analytics (views/watch time/revenue) hadn't fully settled in the YouTube API yet at sync time, the stored value can permanently undercount versus YouTube Studio unless a `year`/`all` resync is run for that period
- `_sync_video_traffic_sources(scope, year)`: same `scope` semantics as above; `scope="incremental"` additionally re-fetches starting 7 days before the last synced date (not right after it), since traffic-source data for a given day is not fully available from the API until some time after that day ends — upserting re-pulled days is a no-op once the data has settled, and corrects any recent day that was stored before its data had fully arrived
- `_sync_fx_rates`: incremental from `get_last_fx_rate()["date"] + 1 day` (first run starts 2015-01-01); weekends/holidays forward-filled with last known close; yfinance imported inside function
- `database.get_all_video_ids()` has no `ORDER BY` — the video processing order in `_sync_video_analytics`/`_sync_video_traffic_sources` is whatever SQLite's default row order happens to be (roughly insertion order), not sorted by publish date, views, or anything meaningful
- both `iter_video_analytics()` and `iter_video_traffic_sources()` chunk by **12-month (year-sized) windows** via `_chunk_date_range(..., months=12)`, not calendar-aligned Jan-Dec — a video published `2019-12-28` gets chunks like `('2019-12-28','2020-12-30')`, `('2020-12-31','2021-12-30')`, etc.
- `maxResults` is set well above the realistic per-chunk row ceiling instead of the API's default-suggested 200, specifically to avoid pagination in the common case: `iter_video_analytics` uses `maxResults=2000` (a year is at most 365 rows, single `day` dimension); `iter_video_traffic_sources` uses `maxResults=10000` (a year's theoretical ceiling is 365 days × 21 possible `insightTrafficSourceType` values = 7665 rows). There is no documented upper bound on `maxResults` in the API's discovery doc (only `minValue: 1`) — confirmed live against a real 2.3M-view video: a single `maxResults=5000` call for full-year 2025 traffic sources returned all 2883 rows across all 365 distinct dates (Jan 1–Dec 31, zero gaps) in one call, vs. 15 calls that would've been needed at the default `maxResults=200`
- both `iter_video_analytics()` and `iter_video_traffic_sources()` pass an explicit `sort` param (`day` / `day,insightTrafficSourceType`) so `startIndex`-based pagination in `_fetch_analytics_rows()` (still present as a fallback for the rare chunk that exceeds `maxResults`) returns a stable, deterministic row order across pages — confirmed live with zero row overlap between consecutive pages and strictly increasing (day, type) order
- `iter_video_analytics()` and `iter_video_traffic_sources()` are generators — rows upserted as they arrive, not batched
- a full `scope="all"` resync across the whole channel costs roughly ~160 API calls/video on average pre-yearly-chunking estimate (more for older videos) — now substantially lower per video since year-chunking + high `maxResults` collapses what used to be many paginated monthly calls into one call per year of the video's history in the common case; still worth spreading a full historical backfill across multiple days via `scope="year"` rather than running `scope="all"` in one shot, since call count still scales with number of videos × years of history
- Shorts detection uses UUSH playlist only — raises if unavailable
- `token.json` deleted automatically on `invalid_grant`; fresh OAuth flow runs next startup

---

### API endpoints

```
GET  /videos                     -> { items: Video[], total: number, page: number, page_size: number }
                                    ?page, page_size (default 50), sort_by, sort_dir,
                                     title, start_date, end_date, content_type, privacy_status
                                    sort_by: published_at (default) | view_count | comment_count | total_revenue_sgd
                                    Video.total_revenue_sgd and Video.total_watch_time_hours are both
                                    lifetime sums (SUM(video_analytics...) with no date filter applied)
GET  /videos/stats               -> { total_uploads, total_videos, total_shorts, total_views,
                                       total_video_views, total_short_views, total_comments,
                                       total_earnings_sgd, total_video_earnings_sgd, total_short_earnings_sgd,
                                       total_public, total_private, total_unlisted }
                                    ?title, start_date, end_date, content_type, privacy_status
GET  /videos/published           -> { items: PublishedVideo[] }  # lightweight: id, title, published_at, thumbnail_url, content_type
                                    ?start_date, end_date, content_type, privacy_status, playlist_id
                                    (filters on published_at, not analytics date; no pagination)
                                    IMPORTANT: must be declared before /videos/{id} in routes.py
GET  /videos/{id}                -> { item: Video }
GET  /videos/{id}/analytics      -> { items: AnalyticsRow[] }   # grouped by date and content_type
                                    ?start_date, end_date
                                    (content_type is constant across rows — it's the video's own type —
                                     but every row still carries it since AnalyticsRow always does)
GET  /videos/{id}/traffic-sources -> { items: TrafficSourceRow[] }   # daily, per traffic source type
                                    ?start_date, end_date
                                    (date filters vts.date, not published_at)
GET  /playlists                  -> { items: Playlist[], total: number, page: number, page_size: number }
                                    ?page, page_size (default 50), sort_by, sort_dir, title
                                    sort_by: last_item_added (default) | published_at | item_count | total_views | total_earnings_sgd
                                    each Playlist row includes last_item_added, total_views, total_earnings_sgd
GET  /playlists/{id}             -> { item: Playlist }  # includes last_item_added, total_views, total_earnings_sgd
GET  /playlists/{id}/videos      -> { items: Video[], total: number, page: number, page_size: number }
                                    ?page, page_size (default 50), sort_by, sort_dir,
                                     title, start_date, end_date, content_type, privacy_status
                                    sort_by: published_at (default) | view_count | comment_count | total_revenue_sgd
GET  /playlists/{id}/videos/stats -> { total_uploads, total_videos, total_shorts, total_views,
                                        total_video_views, total_short_views, total_comments,
                                        total_earnings_sgd, total_video_earnings_sgd, total_short_earnings_sgd,
                                        total_public, total_private, total_unlisted }
                                    ?title, start_date, end_date, content_type, privacy_status
GET  /analytics/videos           -> { items: AnalyticsRow[] }   # channel aggregated, grouped by date and content_type
                                    ?start_date, end_date, content_type, privacy_status
                                    (date filters va.date, not published_at; no title filter;
                                     one row per (date, content_type) — video and short rows for the
                                     same date are separate entries, not summed together; zero-filled
                                     independently per content_type, see AnalyticsRow below)
GET  /analytics/videos/top       -> { items: TopVideo[] }   # top 10 videos by views (channel-wide)
                                    ?start_date, end_date, content_type, privacy_status
                                    (same date/filter semantics as /analytics/videos; views/earnings/
                                     watch time all summed within the given period only, not lifetime)
GET  /analytics/traffic-sources  -> { items: TrafficSourceRow[] }   # channel aggregated, daily
                                    ?start_date, end_date, content_type, privacy_status
                                    (date filters vts.date, not published_at; no title filter)
GET  /analytics/traffic-sources/top -> { items: Record<traffic_source_type, TrafficSourceTopVideo[]> }
                                    ?start_date, end_date, content_type, privacy_status
                                    (top 10 videos by views per traffic source type, channel-wide;
                                     limit=10 passed explicitly by routes.py — the get_top_videos_by_
                                     traffic_source() DB helper itself defaults to limit=3)
GET  /analytics/playlists/{id}   -> { items: AnalyticsRow[] }   # playlist aggregated, grouped by date and content_type
                                    ?start_date, end_date, content_type, privacy_status
                                    (date filters va.date, not published_at; no title filter;
                                     same one-row-per-(date, content_type) semantics as /analytics/videos)
GET  /analytics/playlists/{id}/top -> { items: TopVideo[] }   # top 10 videos by views in playlist
                                    ?start_date, end_date, content_type, privacy_status
GET  /analytics/playlists/{id}/traffic-sources -> { items: TrafficSourceRow[] }   # playlist aggregated, daily
                                    ?start_date, end_date, content_type, privacy_status
                                    (date filters vts.date, not published_at; no title filter)
GET  /analytics/playlists/{id}/traffic-sources/top -> { items: Record<traffic_source_type, TrafficSourceTopVideo[]> }
                                    ?start_date, end_date, content_type, privacy_status
                                    (top 10 videos by views per traffic source type, within the playlist;
                                     same limit=10-passed-explicitly note as the channel-wide endpoint)
GET  /meta/date-range            -> { earliest_year: number | null }
GET  /sync/status                -> { is_syncing: bool, last_synced_at: str|null, message: str }
POST /sync/trigger               -> { queued: true }
                                    ?scope ("incremental" default | "year" | "all"), year (int, required if scope=year)
                                    409 if a sync is already in progress; 400 if scope invalid or scope=year without year
GET  /sync/runs                  -> { items: SyncRun[] }   # recent sync-stage records, newest first
                                    ?limit (default 100, 1-500)
                                    SyncRun: { id, batch_id, sync_type, scope, year, status, started_at,
                                    completed_at, rows_fetched, rows_written, rows_deleted, error_message }
                                    sync_type: videos | playlists | video_analytics |
                                    video_traffic_sources | fx_rates; status: running | success | failed
```

---

### Frontend types (`src/types/index.ts`)

```ts
export interface Video {
  id: string; title: string; description: string | null
  published_at: string; duration_seconds: number | null
  thumbnail_url: string | null; content_type: string
  view_count: number; like_count: number; comment_count: number
  total_revenue_sgd: number; total_watch_time_hours: number
}
export interface Playlist {
  id: string; title: string; published_at: string; thumbnail_url: string | null; item_count: number
  last_item_added: string | null; total_views: number; total_earnings_sgd: number
}
export type ContentType = 'video' | 'short'
export interface AnalyticsRow {
  date: string; content_type: ContentType; views: number; watch_time_minutes: number
  estimated_revenue: number; estimated_revenue_sgd: number; average_view_duration_seconds: number
  average_view_percentage: number; likes: number
  subscribers_gained: number; subscribers_lost: number
}
export interface TrafficSourceRow {
  date: string; traffic_source_type: string
  views: number; watch_time_minutes: number
}
export interface TrafficSourceTopVideo {
  id: string; title: string; thumbnail_url: string | null; content_type: string
  views: number; watch_time_minutes: number
}
export interface TopVideo {
  id: string; title: string; published_at: string; thumbnail_url: string | null; content_type: string
  period_views: number; period_earnings_sgd: number; period_watch_time_hours: number
}
export interface PublishedVideo {
  id: string; title: string; published_at: string; thumbnail_url: string | null; content_type: string
}
export interface SyncState { is_syncing: boolean; last_synced_at: string | null; message: string }
export interface VideoStats {
  total_uploads: number; total_videos: number; total_shorts: number
  total_views: number; total_video_views: number; total_short_views: number; total_comments: number
  total_earnings_sgd: number; total_video_earnings_sgd: number; total_short_earnings_sgd: number
  total_public: number; total_private: number; total_unlisted: number
}
```

---

### Frontend imports

Use `@/` alias (maps to `src/`). Configured in `vite.config.ts` and `tsconfig.app.json`.

```ts
import { getVideos } from '@/api'
import type { Video } from '@/types'
import TopNav from '@/components/TopNav'
```

---

### Design system (`index.css`)

**Tokens:**
- `--blue: #1a73e8`, `--blue-dark`, `--blue-light: #e8f0fe`, `--blue-mid`
- `--surface: #ffffff`, `--surface-glass: rgba(255,255,255,0.75)`
- `--border: #e2e8f0`, `--border-light`
- `--text: #3c4149`, `--text-secondary: #6b7280`, `--text-heading: #111827`
- `--shadow-sm/md/lg`, `--radius: 12px`, `--radius-sm: 8px`, `--radius-lg: 16px`
- Font: Plus Jakarta Sans (Google Fonts)

**Key classes:**
- `.page` — width 80% of viewport, 2rem padding (also mirrored by `.home` in `Home.css` and `.topnav-inner` in `TopNav.css` — keep all three in sync if this changes)
- `.page-header` — flex row for h1 + actions, margin-bottom 1.5rem
- `.card` — glass card (backdrop-filter blur, surface-glass bg, border-light border)
- `.data-table` — fixed-layout table with sortable headers (`.sortable` + hover highlight)
- `.filter-bar` — inline filter row with date inputs and selects; `.filter-bar-sep` = 1px vertical divider between logical groups
- `.tabs` / `.tab` — underline tab strip; `.tab.active` = blue underline
- `.chart-placeholder` — dashed placeholder box, 280px tall
- `.badge` / `.badge.short` — pill badge (blue for Video, amber for Short)
- `.btn-primary` — blue gradient button
- `.btn-ghost` — outlined blue button
- `.loading` — centered muted loading text
- `.pagination` — centered flex row for Previous/Next controls; `.pagination-info` for "Page X of Y" label
- `.section-header` — small-caps label; symmetric 0.5rem top/bottom margin

**Global h1:** gradient text (dark → blue), applied to all `h1` elements via `index.css`.

---

### Page patterns

**Home.tsx** — 3-card grid (Videos/Playlists/Analytics) plus a 3-column `.home-carousels` grid below it: "Top Videos (Last 28 Days)" and "Top Shorts (Last 28 Days)" via `getTopVideosByViews(last28Dates(), 'video'|'short', 'public')`, and "Latest Uploads" via `getVideos(1, 10, 'published_at', 'desc', ..., 'public')` (no content-type filter, so mixes videos/shorts) mapped into `TopVideo` shape via a local `toTopVideoShape()` helper. All three always public-only, independent of any page filter (there is no filter bar on Home).

**Videos.tsx** — paginated, server-side sorted and filtered video table. Sort/page/filters stored in URL params (`?sort_by=`, `?sort_dir=`, `?page=`, `?title=`, `?start_date=`, `?end_date=`, `?content_type=`, `?privacy_status=`). Page size 25. Only `initialLoading` shows spinner — page/sort/filter changes swap rows in place. `VideoStatsBar` rendered above `VideoTable`, fetched separately with same filters.

**Playlists.tsx** — same pagination/sort/URL-param pattern. Filter bar has title search only (no date or type filter). Sortable columns: `last_item_added` (default desc), `published_at`, `item_count`, `total_views`, `total_earnings_sgd`. Column order: Thumbnail | Title | Last Added | Created | Views | Earnings (SGD) | Videos.

**PlaylistAnalytics.tsx** — playlist meta card (thumbnail, title, stats: Views/Earnings/Videos/Last Added/Created) rendered above tabs via `GET /playlists/{id}`; uses `.video-meta-card` classes from `VideoAnalytics.css`. Three tabs, in button order: `analytics`, `traffic-sources`, `videos`. Videos tab renders `<VideoTable>` with Privacy filter. The Analytics and Traffic Sources tabs share one filter bar and one set of URL params, prefixed `analytics_` (`analytics_start_date`, `analytics_end_date`, `analytics_content_type`, `analytics_privacy_status`) — prefixed to avoid colliding with the Videos tab's own `start_date`/`end_date`/`content_type`/`privacy_status` params; default period: Last 28 days; live fetch, no Apply button; fetches `AnalyticsRow[]`, `VideoStats`, `TrafficSourceRow[]` (via `GET /analytics/playlists/{id}/traffic-sources`), and the top-5-per-source map (via `GET /analytics/playlists/{id}/traffic-sources/top`) together off the same params. Analytics tab renders `<VideoStatsBar>` below the filter, then `<AnalyticsChart>`. Traffic Sources tab renders `<TrafficSourceChart>`, then `<TrafficSourcesTable>`, then `<TrafficSourceTopVideosPanel>` below the same filter bar instead. Switching to Videos tab clears all `analytics_*` params; switching to Analytics or Traffic Sources clears all video-tab URL params (`page`, `sort_by`, `sort_dir`, `title`, `start_date`, `end_date`, `content_type`, `privacy_status`); switching between Analytics and Traffic Sources clears nothing (shared params).

**VideoTable.tsx** — shared component used by Videos.tsx and PlaylistAnalytics.tsx. Renders filter bar (PeriodSelect + From + To | Title | Type | Privacy), table with sortable headers, rows, and pagination. Exports `PAGE_SIZE = 25`, `SortKey`, `SortDir`. Props: `videos`, `total`, `initialLoading`, `page`, `sortKey`, `sortDir`, `title`, `startDate`, `endDate`, `contentType`, `privacyStatus`, `onPageChange`, `onSort`, `onFilterChange(title, startDate, endDate, contentType, privacyStatus)` — parents own all URL param, fetch, and stats fetch logic.

**PeriodSelect.tsx** — shared quick-select used in all filter bars. Options: Custom (clears dates, i.e. all data), Last 365 days, Last 90 days, Last 28 days, then years from earliest `published_at` in `videos` table down to current year (fetched from `/meta/date-range`; playlists excluded). Derives its displayed value from current `startDate`/`endDate`. Exports `last365Dates()`, `last90Dates()`, `last28Dates()`.

**Filter bar order (all pages):** Period → From → To | Title | Type | Privacy (separators between groups via `.filter-bar-sep`). No Apply button — all filters trigger live fetch on change. VideoAnalytics has no Type or Privacy filter. Playlists has title only. Privacy filter (Public/Private/Unlisted) on Videos.tsx, Analytics.tsx, and PlaylistAnalytics.tsx.

**Filter state (all pages)** lives in URL search params, never component state, so filters survive reloads/back-forward nav and are shareable. On `Videos.tsx` and `PlaylistAnalytics.tsx` (videos tab) the default for `start_date`/`end_date` is `''` (absent param and explicit empty string are the same thing — "all data" — so no ambiguity). On `Analytics.tsx`, `VideoAnalytics.tsx`, and `PlaylistAnalytics.tsx` (analytics tab) the default is Last 28 days instead, which makes an *absent* param mean something different from an *explicit empty string* (Custom/all data) — reading must use `searchParams.has(key)` to tell them apart, and any handler that writes an empty date must call `.set(key, '')` rather than `.delete(key)`, otherwise selecting Custom immediately snaps back to Last 28 days.

**TopNav.tsx** — sticky glass nav; no "Home" nav-link entry — the "YouTube Analytics" brand text is a `<button>` that navigates to `/` (styled identically to the old plain text); nav links (Videos/Playlists/Analytics) call `navigate(to, { replace: true })` — no history push; back arrow (`path d="M19 12H5M12 5l-7 7 7 7"`) shown only on detail pages (`/analytics/videos/:id`, `/analytics/playlists/:id`) detected via regex; `SyncStatus` rendered in right side of nav bar on every page.

**SyncStatus.tsx** — polls `/sync/status` every 5s via `setInterval`; animated blue dot + message when syncing; when idle: last synced date, scope `<select>` ("New data only" / "Full resync" / each year), and "Sync now" button, all as plain inline items (no bordered pill).

**VideoAnalytics.tsx** — meta card shows thumbnail, title (truncated, single line), badge, stats row (views/likes/comments/published/length/earnings-SGD each as bold value + small-caps label with dividers), then collapsible description (`max-height: 1.55em` collapsed, expand/collapse toggle only shown when text actually overflows). Filter bar: Period → Start → End (no Type filter, no Apply); `start_date`/`end_date` are URL params, default Last 28 days. Fetches `AnalyticsRow[]` from `/videos/{id}/analytics` and `TrafficSourceRow[]` from `/videos/{id}/traffic-sources` together live on filter change, regardless of active tab. Two tabs below the filter bar (`analytics` / `traffic-sources`, URL param `tab`): Analytics tab renders `AnalyticsChart`; Traffic Sources tab renders `TrafficSourceChart` + `TrafficSourcesTable`. Both tabs share the one filter bar/param set, so switching tabs clears nothing (unlike PlaylistAnalytics, which has a third Videos tab with its own separate params).

**Analytics.tsx** — channel-wide analytics. Two tabs (`analytics` / `traffic-sources`, URL param `tab`, no other param clearing needed since both tabs share the same filter set). Filter bar: Period → Start → End | Type | Privacy (no Apply); `start_date`/`end_date`/`content_type`/`privacy_status` are URL params, dates default Last 28 days. Fetches `VideoStats`, `AnalyticsRow[]`, `TopVideo[]`, `PublishedVideo[]`, `TrafficSourceRow[]` (via `GET /analytics/traffic-sources`), and the top-5-per-source map (via `GET /analytics/traffic-sources/top`) together live on filter change, regardless of which tab is active. Analytics tab renders `VideoStatsBar` below filter, then `.analytics-layout` splitting into a left `.analytics-main` column (`AnalyticsChart` with `uploadedVideos` prop, then `TopVideosList`) and a right `.analytics-sidebar` column (two `VideoCarouselCard`s — "Latest Videos" / "Latest Shorts" — sourced from `getVideos(1, 10, 'published_at', 'desc', ..., 'video'|'short', 'public')`, mapped into `TopVideo` shape via `toTopVideoShape()`; fetched once on mount, independent of the page's own filter bar). Traffic Sources tab renders `TrafficSourceChart` (with the same `uploadedVideos`/`publishedVideos`), then `TrafficSourcesTable`, then `TrafficSourceTopVideosPanel` instead.

**PlaylistAnalytics.tsx** — analytics tab also fetches `TopVideo[]` via `GET /analytics/playlists/{id}/top` and `PublishedVideo[]` via `GET /videos/published?playlist_id=` using the same `analytics_*` URL params; renders `<TopVideosList>` and `<AnalyticsChart uploadedVideos={...}>` below chart. Traffic Sources tab renders `<TrafficSourceChart uploadedVideos={...}>`, `<TrafficSourcesTable>`, and `<TrafficSourceTopVideosPanel>` instead, off the same fetched `TrafficSourceRow[]` and top-5-per-source map.

---

### Adding a new page

1. `frontend/src/pages/<PageName>.tsx` + colocated `<PageName>.css`
2. Import types from `@/types`, API calls from `@/api`
3. Add `<Route>` to `frontend/src/App.tsx`

### Adding a new backend route

1. Add handler in `backend/routes.py`
2. Add DB helper in `backend/database.py` if needed

---

### PR checklist
- run `python -m mypy <file>.py` on changed backend files
- run `npx eslint src/... --fix` on changed frontend files; no errors left
- run `npx tsc --noEmit` — no type errors
- no `console.log` in frontend
- no hardcoded colors or magic numbers

### When stuck
- ask a clarifying question or propose a short plan before making large speculative changes
- do not push wide refactors without confirmation
