# Database Reference

## Purpose

Persistence layer, schema, and query conventions. Owns everything about how data is stored, related, and aggregated. Sync-side write patterns (what calls these helpers and when) live in `sync.md`; HTTP-facing shapes live in `api.md`.

## Authoritative source files

- `backend/schema.sql`
- `backend/database/connection.py`, `backend/database/videos.py`, `backend/database/playlists.py`, `backend/database/analytics.py`, `backend/database/traffic_sources.py`, `backend/database/comments.py`, `backend/database/fx_rates.py`, `backend/database/sync_runs.py`

## Contents

- [Connection behavior](#connection-behavior)
- [Schema](#schema)
- [Relationships and deletion behavior](#relationships-and-deletion-behavior)
- [Timestamp behavior](#timestamp-behavior)
- [Query conventions](#query-conventions)
- [Aggregation and filtering semantics](#aggregation-and-filtering-semantics)
- [Compatibility constraints](#compatibility-constraints)

## Connection behavior

`get_connection()` (`database/connection.py:17-23`) returns a `sqlite3.Connection` with:

- `row_factory = sqlite3.Row`
- `PRAGMA foreign_keys = ON` — set on every connection, not just once at startup
- `PRAGMA journal_mode = WAL`
- `PRAGMA busy_timeout = 30000` (30s)

`init_db()` (`database/connection.py:27-31`) creates tables from `schema.sql` via `executescript()` if they don't already exist; it does not run migrations. Both the database and schema paths are resolved from the backend root (`Path(__file__).parent.parent`, i.e. one level above the `database/` package), so they always resolve to `backend/data/youtube.db` and `backend/schema.sql` regardless of which module inside the package imports them.

## Schema

Nine tables:

```sql
videos                  -- id, channel_id, title, description, published_at, duration_seconds, thumbnail_url,
                        --   content_type, privacy_status, view_count, like_count, comment_count, updated_at
                        --   channel_id is the owning YouTube channel ID, used by sync/stages.py::sync_videos()
                        --   to filter playlist-only candidates to this channel's own videos (see sync.md)
video_analytics         -- video_id, date, views, watch_time_minutes, estimated_revenue,
                        --   average_view_duration_seconds, average_view_percentage,
                        --   likes, subscribers_gained, subscribers_lost, updated_at
                        --   PRIMARY KEY (video_id, date)
video_traffic_sources   -- video_id, date, traffic_source_type, views, watch_time_minutes, updated_at
                        --   PRIMARY KEY (video_id, date, traffic_source_type)
playlists               -- id, title, description, published_at, thumbnail_url, item_count, updated_at
playlist_items          -- id, playlist_id, video_id, position, updated_at
comment_authors         -- id, youtube_channel_id, display_name, profile_image_url, channel_url, updated_at
                        --   id is namespace-prefixed: "channel:<youtube channel id>" when the commenter's
                        --   channel resolves, otherwise "comment:<top-level comment id>". The prefixes keep
                        --   the two key forms disjoint; youtube_channel_id holds the raw, unprefixed ID and
                        --   is NULL for the fallback form (see sync.md)
comments                -- id, thread_id, video_id, author_id, text, like_count, total_reply_count,
                        --   published_at, youtube_updated_at, updated_at
                        --   id is the top-level comment ID and thread_id is UNIQUE; only top-level comments
                        --   are stored, with total_reply_count as the thread's reply metadata
                        --   like_count and total_reply_count are NOT NULL DEFAULT 0 CHECK (... >= 0)
fx_rates                -- date, usd_to_sgd, updated_at  (daily USD→SGD close; weekends/holidays forward-filled)
sync_runs                -- id, batch_id, sync_type, scope, year, status, started_at, completed_at,
                        --   rows_fetched, rows_written, rows_deleted, error_message
```

Indexes: `idx_video_analytics_date`, `idx_video_analytics_video`, `idx_video_traffic_sources_date`, `idx_video_traffic_sources_video`, `idx_playlist_items_playlist`, `idx_comments_video`, `idx_comments_author`, `idx_comments_published_at`, `idx_comments_like_count`, `idx_comments_video_published_at`, `idx_sync_runs_started_at`, `idx_sync_runs_type_started`.

The comment-ID, thread-ID, and author-channel lookups are already covered by the primary-key and `UNIQUE` constraints and have no separate index.

There is no `sync_state` table — the scheduler derives its checkpoint from `sync_runs` directly (see [Query conventions](#query-conventions) below and `sync.md`), rather than from a separately persisted `last_synced_at` value.

## Relationships and deletion behavior

- `video_analytics.video_id → videos.id` **ON DELETE CASCADE**
- `video_traffic_sources.video_id → videos.id` **ON DELETE CASCADE**
- `playlist_items.playlist_id → playlists.id` **ON DELETE CASCADE**
- `playlist_items.video_id` has **no FK** — it's a raw YouTube video ID that may not exist in `videos` (e.g. a playlist item referencing a video not in the channel's own uploads)
- `comments.video_id → videos.id` **ON DELETE CASCADE**
- `comments.author_id → comment_authors.id` **ON DELETE RESTRICT** — a commenter row cannot be deleted while any comment still references it
- Cascades only take effect because `PRAGMA foreign_keys = ON` is set on every connection

Comments are never deleted to reflect their removal on YouTube. Both sync scopes only insert and update, so a comment deleted upstream keeps its stored row; the only comment deletions come from the cascade when the `pruning` stage removes its parent video. `delete_orphan_comment_authors()` (`database/comments.py`) is the one commenter-side delete: it removes only rows no comment references any more, which is how the authors left behind by that cascade are cleaned up on the next successful Comments run. Because `author_id` is `RESTRICT`, this can never orphan a live comment.

Deletion helpers report only rows they directly deleted via `cursor.rowcount` — cascaded child-row deletes (e.g. `video_analytics` rows removed when their parent `videos` row is deleted) are **not** included in that count. See `delete_videos_not_in()` (`database/videos.py:381-395`), `delete_playlists_not_in()` (`database/playlists.py:199-206`), `delete_playlist_items()` (`database/playlists.py:209-213`).

`delete_videos_not_in(ids)` has **no empty-list guard**: an empty `ids` deletes every video, not zero. Its only caller is the `pruning` sync stage (`sync/stages.py::sync_pruning()`), which is opt-in and never runs automatically — see `sync.md` for how the caller is expected to only pass an empty list when that genuinely reflects a channel with zero owned videos.

## Timestamp behavior

`_now()` (`database/connection.py:12-14`) returns a timezone-aware UTC ISO 8601 string, e.g. `2026-07-17T08:30:45.123456+00:00`.

Every upsert helper sets `updated_at = _now()` on the Python side before the query executes, and every `ON CONFLICT` clause sets `updated_at = excluded.updated_at` — so `updated_at` reflects "last successfully pulled and upserted," not "last changed." It updates even when a re-fetched row's values are identical to what's already stored.

`updated_at` is not present on `sync_runs` (has its own `started_at`/`completed_at`).

## Query conventions

- **Every** query uses parameterized `?` placeholders (or named `:param` placeholders for upserts) — never string-interpolated values. `f"..."` is used only to interpolate column names / `WHERE` clause fragments built from a fixed allow-list (e.g. `VIDEO_SORT_COLUMNS`, `_PLAYLIST_SORT_COLUMNS`), never raw user input.
- Sort columns are validated against an explicit set before being interpolated into `ORDER BY`:
  - `VIDEO_SORT_COLUMNS = {"published_at", "view_count", "comment_count", "total_revenue_sgd"}` (`database/videos.py:33`) — exported without a leading underscore because `database/playlists.py` imports it directly for `get_playlist_videos()`'s own sort validation.
  - `_PLAYLIST_SORT_COLUMNS = {"published_at", "item_count", "last_item_added", "total_views", "total_earnings_sgd"}` (`database/playlists.py:28`)
  - An invalid `sort_by` silently falls back to the default column rather than erroring.
- `COMMENT_SORT_CLAUSES` (`database/comments.py`) maps each public comment sort value to a full `ORDER BY` fragment rather than a bare column, each ending in `c.id` so equal timestamps or like counts cannot shuffle rows between pages: `"newest"` → `c.published_at DESC, c.id DESC`; `"oldest"` → `c.published_at ASC, c.id ASC`; `"likes"` → `c.like_count DESC, c.published_at DESC, c.id DESC`. An unrecognized value falls back to `DEFAULT_COMMENT_SORT` (`"newest"`); the HTTP layer rejects it first (see `api.md`).
- `get_top_videos_by_views()` (`database/analytics.py`) validates `sort_by` against `_TOP_VIDEO_SORT_ORDER_BY` (`database/analytics.py`), a mapping from public sort value to a full `ORDER BY` clause (aggregate plus deterministic tie-breakers), not a bare column name:
  - `"views"` → `period_views DESC, v.id ASC`
  - `"watch_time"` → `period_watch_time_hours DESC, period_views DESC, v.id ASC`
  - An unrecognized `sort_by` falls back to `"views"`. The helper defaults `sort_by="views"`.
- **Optional video scoping**: the four aggregate/top helpers — `get_aggregated_analytics()` and `get_top_videos_by_views()` (`database/analytics.py`), `get_aggregated_traffic_sources()` and `get_top_videos_by_traffic_source()` (`database/traffic_sources.py`) — each accept a trailing optional `video_ids: Collection[str] | None`, and there are no separate playlist-specific variants of them. The parameter has three distinct states, and the distinction between the last two is load-bearing:
  - `None` (the default, and what channel-wide routes pass): no video predicate at all, so the query stays channel-wide.
  - A populated collection: appends `v.id IN (?, ?, …)` with one bound `?` per ID. Only the placeholder count is interpolated; every ID is a bound parameter.
  - An explicitly empty collection: returns the helper's natural empty shape *before opening a connection* — `[]` for the three list-returning helpers, `{}` for `get_top_videos_by_traffic_source()`. A truthiness check such as `if video_ids:` would collapse this state into `None` and leak channel-wide data to an empty playlist, so each helper tests `video_ids is not None` separately from emptiness.

  Each helper materializes the argument once (`list(video_ids)`) before building placeholders, so sets and other non-sequence collections behave consistently. The scope predicate is appended to the same `conditions`/`params` pair as the other filters and composes with all of them via `AND`; the `LIMIT` parameter stays last.
- All multi-table queries qualify columns with table aliases (`v.`, `va.`, `vts.`, `pi.`, `fx.`, `p.`) since `video_analytics` and `fx_rates` both have a `date` column, and other tables share `content_type`/`privacy_status`-adjacent names.
- `get_all_video_ids()` (`database/videos.py:161-165`) has **no `ORDER BY`** — callers get SQLite's default row order (roughly insertion order), not anything meaningful.
- `get_video_stats()` (`database/videos.py:180-275`) and `get_playlist_video_stats()` (`database/videos.py:278-378`) each run several sequential queries against the same `get_connection()` connection rather than one combined statement — the multi-query split is deliberate (see below) and each function's queries stay self-contained; there is no shared stats helper between them. Both live in `database/videos.py` alongside the video catalog helpers, not in `database/analytics.py`, since they're keyed off the video catalog (Legacy/New classification, lifetime comments/privacy counts) with analytics as a secondary join.
- `get_sync_runs(page, page_size)` (`database/sync_runs.py`) returns `tuple[list[dict], int]` — one page of rows plus the unfiltered `COUNT(*)` — from two statements on the same connection, matching the other paginated helpers. It takes no filters, so there is no `WHERE` clause on either statement. `ORDER BY started_at DESC, id DESC` ends in the unique ID so that any rows sharing a `started_at` value have a total, stable order instead of an arbitrary one that could shuffle a row between pages. This is the same tie-breaker discipline as `COMMENT_SORT_CLAUSES`, though collisions are far less likely here: `_now()` (`database/connection.py`) stores microsecond-resolution ISO timestamps, so distinct inserts effectively never tie, whereas comment `published_at` values come from YouTube at second resolution and genuinely do. The tie-breaker is a correctness guarantee that does not depend on that resolution holding. `LIMIT ? OFFSET ?` are bound parameters with `offset = (page - 1) * page_size`; the HTTP layer validates the bounds first (see `api.md`). Offset paging can shift when a new stage row is inserted between page requests — acceptable for an append-only history with no snapshot requirement.
- `get_last_successful_run_completed_at()` (`database/sync_runs.py`) returns `MAX(completed_at)` across `sync_runs` rows with `status = 'success'`, or `None` when nothing has ever succeeded. It takes no arguments and does not group by `batch_id`: a single succeeded run qualifies regardless of its `sync_type`, scope, or which other stages ran alongside it. Because the `MAX` is taken over successful rows only, a later failed or still-running row cannot hide an earlier success. Used by `sync/scheduler.py`'s `synced_today()` to decide whether the startup sync should run, without a separate persisted checkpoint. A selective manual sync therefore does suppress that day's startup sync — see `sync.md`.

## Aggregation and filtering semantics

- **Lifetime vs. period totals**: `Video.total_revenue_sgd` / `total_watch_time_hours` (from `get_all_videos`, `get_video` in `database/videos.py`, and `get_playlist_videos` in `database/playlists.py`) are lifetime sums with no date filter applied, computed via `LEFT JOIN video_analytics` + `LEFT JOIN fx_rates`. Endpoints under `/analytics/*` (e.g. `get_top_videos_by_views`, `get_aggregated_analytics`, both in `database/analytics.py`) compute period-scoped sums bounded by `start_date`/`end_date` instead — same join pattern, but with date conditions applied.
- **Currency conversion**: `estimated_revenue_sgd` / `total_revenue_sgd` / `total_earnings_sgd` are always computed as `estimated_revenue * usd_to_sgd`, joined via `fx_rates.date = video_analytics.date` (or `DATE(va.date)` in the two `get_all_playlists`/`get_playlist` subqueries in `database/playlists.py` — same semantic result, slightly different SQL form). A missing FX row for a given date means that date's revenue contributes `NULL`, `COALESCE`d to `0`.
- **Date filters**: filters against `published_at` (`videos`, `playlists`) use `>= start_date` and `<= end_date + "T23:59:59"` since `published_at` is a full timestamp; filters against `date` columns (`video_analytics.date`, `video_traffic_sources.date`) use plain `>= start_date` / `<= end_date` since those are date-only strings. Mixing these up would silently exclude the final day of a range.
- **Title filter**: every analytics/traffic-source/published-videos helper (`get_aggregated_analytics`, `get_top_videos_by_views` in `database/analytics.py`; `get_aggregated_traffic_sources`, `get_top_videos_by_traffic_source` in `database/traffic_sources.py`; `get_videos_published` in `database/videos.py`) accepts an optional `title` parameter and, when non-empty, appends `v.title LIKE ?` bound to `f"%{title}%"` — the same case-insensitive partial-match semantics `get_all_videos()`/`get_video_stats()`/`get_playlist_video_stats()` already used, combined with any other supplied condition via `AND`. When a `video_ids` scope is also supplied, the title filter is additive to it, not a replacement — a title match outside the scoped set still yields no row. An omitted or empty title leaves the query unchanged from before this filter existed.
- **Grouping — analytics rows**: `get_aggregated_analytics()` (`database/analytics.py`) groups by `(date, content_type)` — a video-day and a short-day on the same date are two separate rows, never summed together. `get_video_analytics()` (single video, also `database/analytics.py`) doesn't need to group by `content_type` in SQL since a video only has one, but still tags every row with it.
- **Zero-filling — analytics**: `_zero_fill_analytics()` (`database/analytics.py:35-54`) inserts a `{date, content_type}` row with all-zero metric values for every day in `[start_date or min(dates), end_date or max(dates)]` not already present, for each `content_type` in the requested set (`[content_type]` if filtered, else `["video", "short"]`). It then trims trailing zero-only rows past the last date that actually has data, so a chart doesn't extend zero-filled into the future beyond real data. It lives in `database/analytics.py` and is shared by every caller in that same module (`get_video_analytics`, `get_aggregated_analytics`).
- **Zero-filling — traffic sources**: `_zero_fill_traffic_sources()` (`database/traffic_sources.py:37-60`) fills only the **1st of each month** with a zero row per traffic source type actually present in the result set, for months with no data at all — it does not zero-fill every missing day (contrast with analytics zero-fill, which is daily). Trims to the last real date, same as analytics. It lives in `database/traffic_sources.py`, self-contained from the analytics zero-fill helper.
- **Top-N per traffic source type**: `get_top_videos_by_traffic_source()` (`database/traffic_sources.py`) fetches rows ordered `(traffic_source_type, views DESC)` in SQL, then `_top_n_per_source()` (`database/traffic_sources.py`) truncates each group in Python — this only works correctly because the SQL `ORDER BY` guarantees each group arrives pre-sorted by views descending. The DB helper itself defaults `limit=3`; `routes/analytics.py` passes `limit=10` explicitly for both the channel-wide and the playlist-scoped endpoint.
- **Playlist membership resolution**: `get_playlist_video_ids(playlist_id)` (`database/playlists.py`) is the single source of a playlist's analytics scope. It returns `SELECT DISTINCT v.id` over `playlist_items pi JOIN videos v ON v.id = pi.video_id WHERE pi.playlist_id = ?`, which does three things at once: duplicate `playlist_items` rows for the same video collapse to one ID (only `playlist_items.id` is unique, so duplicate `(playlist_id, video_id)` pairs are possible and would otherwise multiply aggregates); a `NULL` `video_id` is dropped; and a dangling `video_id` with no `videos` row is dropped, since `playlist_items.video_id` has no FK (see above). A playlist with no valid members — and an unknown playlist ID — both yield `[]`, which is why callers must establish existence separately via `get_playlist()`. The four scoped query helpers never touch `playlist_items` themselves; they only see the resolved ID collection. `get_playlist_video_stats()` (`database/videos.py`) is independent of this helper and does its own dedup inline via `v.id IN (SELECT DISTINCT pi.video_id FROM playlist_items pi WHERE pi.playlist_id = ?)`.
- **Top videos — period metrics**: `get_top_videos_by_views()` (`database/analytics.py`) returns `period_views`, `period_earnings_sgd`, and `period_watch_time_hours` (`SUM(va.watch_time_minutes) / 60.0`) computed from the same filtered `video_analytics` rows, scoped by the optional `start_date`/`end_date`/`content_type`/`privacy_status`/`video_ids` filters (applied to `va.date` and `v.*`, not `v.published_at`). `LIMIT` is applied after the `ORDER BY`, so ranking always happens over the full filtered set before truncating to the top N.
- **Video stats — Legacy/New classification**: `get_video_stats()` (`database/videos.py:180-275`, plus the shared `_empty_video_stats()` default template at `database/videos.py:168-177`) and `get_playlist_video_stats()` (`database/videos.py:278-378`) classify each video as Legacy (`published_at` strictly before the effective start date) or New (`published_at` between the effective start and end dates, inclusive), or neither if published after the effective end date. Each function runs three queries against one `get_connection()` connection: (1) the available `video_analytics` date range plus the catalog's `published_at` range, used to derive the effective start/end when `start_date`/`end_date` are omitted; (2) a catalog query that counts Legacy/New videos per content type and computes lifetime comment/privacy-status totals directly from `videos` (no analytics join, so no multiplication risk); (3) a period-performance query that pre-aggregates `video_analytics` per `video_id` in a subquery (summing views and `estimated_revenue * fx_rates.usd_to_sgd`) before joining to `videos`, then groups by Legacy/New bucket and content type — the subquery pre-aggregation is what keeps the `fx_rates` join (1 row per `date`, per the `fx_rates` schema) from inflating sums. Effective start/end fall back, in order, to the `video_analytics` date range, then the catalog's `published_at` range (truncated to a date) if no analytics rows exist at all — in that fallback case period views/earnings are zero but Legacy/New classification and counts still work. A video with a `NULL` `published_at` is never classified Legacy or New but still contributes to comment/status totals. Lifetime comments and current privacy status are never restricted by date. Both functions live in `database/videos.py`, not `database/analytics.py`, since they're keyed off the video catalog with analytics as a secondary join.

- **Comment reads**: `get_comments()`, `get_video_comments()`, and `get_playlist_comments()` (`database/comments.py`) all delegate to one private `_query_comments()`, which joins `comments c` to `comment_authors ca` and `videos v` and returns the author snapshot (`author_youtube_channel_id`, `author_display_name`, `author_profile_image_url`, `author_channel_url`) plus `video_title`, `video_content_type`, and `video_thumbnail_url` alongside every comment column. Filters are `c.text`, `v.title`, and `ca.display_name` via `LIKE ?` bound to `f"%{value}%"`, `v.content_type`, and a `c.published_at` range using the full-timestamp convention above (`>= start_date`, `<= end_date + "T23:59:59"`). The video scope adds `c.video_id = ?`; the playlist scope adds `EXISTS (SELECT 1 FROM playlist_items pi WHERE pi.playlist_id = ? AND pi.video_id = c.video_id)`, so a video listed twice in a playlist still yields each of its comments once — the `EXISTS` is the comment-side equivalent of the `SELECT DISTINCT` dedup the playlist stats helpers use. Both scopes count and page over the same filtered set. The video-scoped helper accepts no `video_title` or `content_type` filter, since a fixed video determines both.

## Compatibility constraints

- Adding a new sortable column requires adding it to both the relevant `..._SORT_COLUMNS` set (`database/videos.py`'s `VIDEO_SORT_COLUMNS` or `database/playlists.py`'s `_PLAYLIST_SORT_COLUMNS`) *and* the frontend's `SortKey` type (see `frontend.md`) — the backend will silently ignore an unrecognized `sort_by` rather than reject it.
- `_zero_fill_analytics` assumes all rows passed in share the same set of non-`(date, content_type)` keys (it derives the "zero" template from `rows[0]`) — a query that ever returned heterogeneous column sets across rows would break this.
- Because every upsert always rewrites `updated_at`, this column cannot be used to detect "did the underlying value actually change since last sync" — only "was this row touched by the most recent sync."
- `database/playlists.py` imports `VIDEO_SORT_COLUMNS` from `database/videos.py` for `get_playlist_videos()`'s sort validation — the only cross-module dependency between `database/` submodules. All other submodules only depend on `database/connection.py`. In particular, `database/analytics.py` and `database/traffic_sources.py` do not import `database/playlists.py`: playlist membership is resolved by the route layer and passed in as `video_ids`, which is what keeps the scoped helpers usable with any caller-supplied set of videos.
- The `video_ids` parameter is appended **after** every existing parameter on all four scoped helpers, so current positional callers keep binding to the same arguments. Callers should still pass it by keyword. It binds one `?` per ID, so a scope is bounded by SQLite's parameter limit — practical for playlist-sized collections, not for arbitrarily large ID sets.
