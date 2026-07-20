# Database Reference

## Purpose

Persistence layer, schema, and query conventions. Owns everything about how data is stored, related, and aggregated. Sync-side write patterns (what calls these helpers and when) live in `sync.md`; HTTP-facing shapes live in `api.md`.

## Authoritative source files

- `backend/schema.sql`
- `backend/database.py`

## Contents

- [Connection behavior](#connection-behavior)
- [Schema](#schema)
- [Relationships and deletion behavior](#relationships-and-deletion-behavior)
- [Timestamp behavior](#timestamp-behavior)
- [Query conventions](#query-conventions)
- [Aggregation and filtering semantics](#aggregation-and-filtering-semantics)
- [Compatibility constraints](#compatibility-constraints)

## Connection behavior

`get_connection()` (`database.py:16-23`) returns a `sqlite3.Connection` with:

- `row_factory = sqlite3.Row`
- `PRAGMA foreign_keys = ON` — set on every connection, not just once at startup
- `PRAGMA journal_mode = WAL`
- `PRAGMA busy_timeout = 30000` (30s)

`init_db()` creates tables from `schema.sql` via `executescript()` if they don't already exist; it does not run migrations.

## Schema

Eight tables:

```sql
videos                  -- id, title, description, published_at, duration_seconds, thumbnail_url,
                        --   content_type, privacy_status, view_count, like_count, comment_count, updated_at
video_analytics         -- video_id, date, views, watch_time_minutes, estimated_revenue,
                        --   average_view_duration_seconds, average_view_percentage,
                        --   likes, subscribers_gained, subscribers_lost, updated_at
                        --   PRIMARY KEY (video_id, date)
video_traffic_sources   -- video_id, date, traffic_source_type, views, watch_time_minutes, updated_at
                        --   PRIMARY KEY (video_id, date, traffic_source_type)
playlists               -- id, title, description, published_at, thumbnail_url, item_count, updated_at
playlist_items          -- id, playlist_id, video_id, position, updated_at
sync_state              -- key, value  (persists last_synced_at across restarts)
fx_rates                -- date, usd_to_sgd, updated_at  (daily USD→SGD close; weekends/holidays forward-filled)
sync_runs                -- id, batch_id, sync_type, scope, year, status, started_at, completed_at,
                        --   rows_fetched, rows_written, rows_deleted, error_message
```

Indexes: `idx_video_analytics_date`, `idx_video_analytics_video`, `idx_video_traffic_sources_date`, `idx_video_traffic_sources_video`, `idx_playlist_items_playlist`, `idx_sync_runs_started_at`, `idx_sync_runs_type_started`.

## Relationships and deletion behavior

- `video_analytics.video_id → videos.id` **ON DELETE CASCADE**
- `video_traffic_sources.video_id → videos.id` **ON DELETE CASCADE**
- `playlist_items.playlist_id → playlists.id` **ON DELETE CASCADE**
- `playlist_items.video_id` has **no FK** — it's a raw YouTube video ID that may not exist in `videos` (e.g. a playlist item referencing a video not in the channel's own uploads)
- Cascades only take effect because `PRAGMA foreign_keys = ON` is set on every connection

Deletion helpers report only rows they directly deleted via `cursor.rowcount` — cascaded child-row deletes (e.g. `video_analytics` rows removed when their parent `videos` row is deleted) are **not** included in that count. See `delete_videos_not_in()` (`database.py:306-313`), `delete_playlists_not_in()` (`database.py:1079-1086`), `delete_playlist_items()` (`database.py:1089-1093`).

## Timestamp behavior

`_now()` (`database.py:11-13`) returns a timezone-aware UTC ISO 8601 string, e.g. `2026-07-17T08:30:45.123456+00:00`.

Every upsert helper sets `updated_at = _now()` on the Python side before the query executes, and every `ON CONFLICT` clause sets `updated_at = excluded.updated_at` — so `updated_at` reflects "last successfully pulled and upserted," not "last changed." It updates even when a re-fetched row's values are identical to what's already stored.

`updated_at` is not present on `sync_state` (a key/value store, not a synced record) or `sync_runs` (has its own `started_at`/`completed_at`).

## Query conventions

- **Every** query uses parameterized `?` placeholders (or named `:param` placeholders for upserts) — never string-interpolated values. `f"..."` is used only to interpolate column names / `WHERE` clause fragments built from a fixed allow-list (e.g. `_VIDEO_SORT_COLUMNS`, `_PLAYLIST_SORT_COLUMNS`), never raw user input.
- Sort columns are validated against an explicit set before being interpolated into `ORDER BY`:
  - `_VIDEO_SORT_COLUMNS = {"published_at", "view_count", "comment_count", "total_revenue_sgd"}`
  - `_PLAYLIST_SORT_COLUMNS = {"published_at", "item_count", "last_item_added", "total_views", "total_earnings_sgd"}`
  - An invalid `sort_by` silently falls back to the default column rather than erroring.
- All multi-table queries qualify columns with table aliases (`v.`, `va.`, `vts.`, `pi.`, `fx.`, `p.`) since `video_analytics` and `fx_rates` both have a `date` column, and other tables share `content_type`/`privacy_status`-adjacent names.
- `get_all_video_ids()` (`database.py:183-187`) has **no `ORDER BY`** — callers get SQLite's default row order (roughly insertion order), not anything meaningful.
- `get_video_stats()` and `get_playlist_video_stats()` each run several sequential queries against the same `get_connection()` connection rather than one combined statement — the multi-query split is deliberate (see below) and each function's queries stay self-contained; there is no shared stats helper between them.

## Aggregation and filtering semantics

- **Lifetime vs. period totals**: `Video.total_revenue_sgd` / `total_watch_time_hours` (from `get_all_videos`, `get_video`, `get_playlist_videos`) are lifetime sums with no date filter applied, computed via `LEFT JOIN video_analytics` + `LEFT JOIN fx_rates`. Endpoints under `/analytics/*` (e.g. `get_top_videos_by_views`, `get_aggregated_analytics`) compute period-scoped sums bounded by `start_date`/`end_date` instead — same join pattern, but with date conditions applied.
- **Currency conversion**: `estimated_revenue_sgd` / `total_revenue_sgd` / `total_earnings_sgd` are always computed as `estimated_revenue * usd_to_sgd`, joined via `fx_rates.date = video_analytics.date` (or `DATE(va.date)` in the two `get_all_playlists`/`get_playlist` subqueries — same semantic result, slightly different SQL form). A missing FX row for a given date means that date's revenue contributes `NULL`, `COALESCE`d to `0`.
- **Date filters**: filters against `published_at` (`videos`, `playlists`) use `>= start_date` and `<= end_date + "T23:59:59"` since `published_at` is a full timestamp; filters against `date` columns (`video_analytics.date`, `video_traffic_sources.date`) use plain `>= start_date` / `<= end_date` since those are date-only strings. Mixing these up would silently exclude the final day of a range.
- **Grouping — analytics rows**: `get_aggregated_analytics()` and `get_playlist_aggregated_analytics()` group by `(date, content_type)` — a video-day and a short-day on the same date are two separate rows, never summed together. `get_video_analytics()` (single video) doesn't need to group by `content_type` in SQL since a video only has one, but still tags every row with it.
- **Zero-filling — analytics**: `_zero_fill_analytics()` (`database.py:347-366`) inserts a `{date, content_type}` row with all-zero metric values for every day in `[start_date or min(dates), end_date or max(dates)]` not already present, for each `content_type` in the requested set (`[content_type]` if filtered, else `["video", "short"]`). It then trims trailing zero-only rows past the last date that actually has data, so a chart doesn't extend zero-filled into the future beyond real data.
- **Zero-filling — traffic sources**: `_zero_fill_traffic_sources()` (`database.py:440-463`) fills only the **1st of each month** with a zero row per traffic source type actually present in the result set, for months with no data at all — it does not zero-fill every missing day (contrast with analytics zero-fill, which is daily). Trims to the last real date, same as analytics.
- **Top-N per traffic source type**: `get_top_videos_by_traffic_source()` / `get_playlist_top_videos_by_traffic_source()` fetch rows ordered `(traffic_source_type, views DESC)` in SQL, then `_top_n_per_source()` (`database.py:769-778`) truncates each group in Python — this only works correctly because the SQL `ORDER BY` guarantees each group arrives pre-sorted by views descending. The DB helper itself defaults `limit=3`; `routes.py` passes `limit=10` explicitly for both channel-wide and playlist-scoped endpoints.
- **Playlist stats join**: `get_playlist_video_stats()` and the playlist-scoped analytics helpers join through `playlist_items` — `playlist_items.video_id` has no FK (see above), so a stale/dangling `video_id` in a playlist item simply produces no match in the `JOIN videos v ON v.id = pi.video_id`, silently excluding that item rather than erroring. `get_playlist_video_stats()` further deduplicates membership via `v.id IN (SELECT DISTINCT pi.video_id FROM playlist_items pi WHERE pi.playlist_id = ?)` before any counting or aggregation, so a duplicate `playlist_items` row for the same video cannot double-count it.
- **Video stats — Legacy/New classification**: `get_video_stats()` (`database.py:202-297`, plus the shared `_empty_video_stats()` default template at `database.py:190-199`) and `get_playlist_video_stats()` (`database.py:300-397`) classify each video as Legacy (`published_at` strictly before the effective start date) or New (`published_at` between the effective start and end dates, inclusive), or neither if published after the effective end date. Each function runs three queries against one `get_connection()` connection: (1) the available `video_analytics` date range plus the catalog's `published_at` range, used to derive the effective start/end when `start_date`/`end_date` are omitted; (2) a catalog query that counts Legacy/New videos per content type and computes lifetime comment/privacy-status totals directly from `videos` (no analytics join, so no multiplication risk); (3) a period-performance query that pre-aggregates `video_analytics` per `video_id` in a subquery (summing views and `estimated_revenue * fx_rates.usd_to_sgd`) before joining to `videos`, then groups by Legacy/New bucket and content type — the subquery pre-aggregation is what keeps the `fx_rates` join (1 row per `date`, per the `fx_rates` schema) from inflating sums. Effective start/end fall back, in order, to the `video_analytics` date range, then the catalog's `published_at` range (truncated to a date) if no analytics rows exist at all — in that fallback case period views/earnings are zero but Legacy/New classification and counts still work. A video with a `NULL` `published_at` is never classified Legacy or New but still contributes to comment/status totals. Lifetime comments and current privacy status are never restricted by date.

## Compatibility constraints

- Adding a new sortable column requires adding it to both the relevant `_..._SORT_COLUMNS` set *and* the frontend's `SortKey` type (see `frontend.md`) — the backend will silently ignore an unrecognized `sort_by` rather than reject it.
- `_zero_fill_analytics` assumes all rows passed in share the same set of non-`(date, content_type)` keys (it derives the "zero" template from `rows[0]`) — a query that ever returned heterogeneous column sets across rows would break this.
- Because every upsert always rewrites `updated_at`, this column cannot be used to detect "did the underlying value actually change since last sync" — only "was this row touched by the most recent sync."
