# Database Reference

## Purpose

Persistence layer, schema, row dataclasses, the shared reader and writer, and query conventions. Owns everything about how data is stored, read, written, related, and aggregated. Sync-side write patterns (what sync writes and when) live in `sync.md`; HTTP-facing shapes live in `api.md`.

## Authoritative source files

- `backend/schema.sql`
- `backend/database/dataclasses/` (one row dataclass per table), `backend/database/tables.py`, `backend/database/filters.py`, `backend/database/reader.py`, `backend/database/writer.py`, `backend/database/queries.py`, `backend/database/video_statistics.py`
- `backend/database/connection.py`, `backend/database/analytics.py`, `backend/database/traffic_sources.py`, `backend/database/sync_runs.py`, `backend/database/related_videos.py`
- `backend/scripts/issue-48-migration.py`, `backend/scripts/issue-62-migration.py` — standalone, one-time migrations for pre-existing databases (see [Compatibility constraints](#compatibility-constraints)); neither is run by `init_db()`

## Contents

- [Connection behavior](#connection-behavior)
- [Schema](#schema)
- [Row dataclasses, reader, and writer](#row-dataclasses-reader-and-writer)
- [Ownership boundary](#ownership-boundary)
- [Sync coverage](#sync-coverage)
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

Twelve tables:

```sql
videos                  -- id, channel_id, title, description, published_at, duration_seconds, thumbnail_url,
                        --   content_type, privacy_status, view_count, like_count, comment_count, own, updated_at
                        --   channel_id is the owning YouTube channel ID, used by sync/stages.py::sync_videos()
                        --   to filter playlist-only candidates to this channel's own videos (see sync.md)
                        --   own is INTEGER NOT NULL DEFAULT 1 CHECK (own IN (0, 1)) — the ownership boundary
                        --   (see below); the reader's registered converter turns every selected own into a
                        --   Python bool (see Row dataclasses, reader, and writer)
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
search_terms            -- video_id, month, search_term, views, updated_at
                        --   PRIMARY KEY (video_id, month, search_term); month is validated "YYYY-MM"
                        --   views is CHECK (views > 0) — a term is never stored at zero or negative views
related_videos          -- target_video_id, month, referrer_video_id, views, updated_at
                        --   PRIMARY KEY (target_video_id, month, referrer_video_id); month is validated "YYYY-MM"
                        --   views is CHECK (views > 0) — a referrer is never stored at zero or negative views
                        --   FK only on target_video_id -> videos(id) ON DELETE CASCADE; referrer_video_id is a
                        --   raw YouTube ID with no FK, so an unresolved/unavailable referrer needs no placeholder
                        --   video row (mirrors playlist_items.video_id's own no-FK precedent)
sync_runs                -- id, batch_id, sync_type, scope, year, status, started_at, completed_at,
                        --   rows_fetched, rows_written, rows_deleted, error_message
sync_coverage           -- collector, video_id, period_key, completed_at
                        --   PRIMARY KEY (collector, video_id, period_key); period_key is "YYYY-MM" for
                        --   every collector — see Sync coverage below
```

Indexes: `idx_video_analytics_date`, `idx_video_analytics_video`, `idx_video_traffic_sources_date`, `idx_video_traffic_sources_video`, `idx_playlist_items_playlist`, `idx_comments_video`, `idx_comments_author`, `idx_comments_published_at`, `idx_comments_like_count`, `idx_comments_video_published_at`, `idx_search_terms_month`, `idx_related_videos_month`, `idx_sync_runs_started_at`, `idx_sync_runs_type_started`.

The comment-ID, thread-ID, and author-channel lookups are already covered by the primary-key and `UNIQUE` constraints and have no separate index.

There is no `sync_state` table — the scheduler derives its checkpoint from `sync_runs` directly (see [Query conventions](#query-conventions) below and `sync.md`), rather than from a separately persisted `last_synced_at` value.

## Row dataclasses, reader, and writer

Reads go through `database/reader.py`; inserts, updates, and deletes go through `database/writer.py`. Both use the table registry in `database/tables.py` and the WHERE compiler in `database/filters.py`, and neither imports the other. The sync-run lifecycle functions (`create_sync_run`, `complete_sync_run`, `fail_sync_run`, `cancel_sync_run`, `mark_incomplete_sync_runs`) keep their own SQL in `database/sync_runs.py`.

### Row dataclasses

`database/dataclasses/` defines one plain `@dataclass` per table: `Video`, `Playlist`, `PlaylistItem`, `VideoAnalytics`, `VideoTrafficSource`, `Comment`, `CommentAuthor`, `SearchTerm`, `RelatedVideo`, `FxRate`, `SyncCoverage`, `SyncRun`. Field names and order match `schema.sql` exactly, including keys and `updated_at`. Every field is optional and defaults to `None`, because a read may select only some columns.

- `None` means either SQL `NULL` or a column the read did not select. `0`, `0.0`, `False`, and `""` are kept as they are, never turned into `None`.
- Dates and timestamps stay as their stored text. `Video.own` is the only converted column: `bool` when present, `None` when not selected or when a `LEFT JOIN` found no row.
- The classes hold data only. They know nothing about tables, connections, or queries, and share only the `Row` mixin (`database/dataclasses/base.py`).
- `Model.from_dict(mapping)` builds a row from a dictionary, e.g. `Video.from_dict({**fetched, "own": True, "updated_at": now()})`. Absent keys stay `None`, supplied `None`/falsy values are kept, an unknown key raises `ValueError`, and the mapping is not modified. It converts only; it does not check value types.
- `to_dict(fields=None, *, prefix="")` returns a plain dictionary for FastAPI to encode. With no `fields` it returns every declared field, including `None` values. With `fields` it returns exactly those keys, including selected `None`s, and raises `ValueError` for an unknown name. `prefix` renames keys, e.g. `to_dict(("display_name",), prefix="author_")` → `{"author_display_name": ...}`.

The same classes also hold grouped results when the aliases match their fields, e.g. `SearchTerm(search_term=..., views=SUM(...))`. Such an instance is a computed value, not a stored row.

### Registry

`database/tables.py` holds the shared metadata:
- `TABLES` maps each row class to its table explicitly; class names are never used to guess table names. `reader.TABLES` is the same object.
- `KEYS` lists the primary-key columns the writer matches on: `id` for `Video`, `Playlist`, `PlaylistItem`, `Comment`, `CommentAuthor` and `SyncRun`; `video_id + date` for `VideoAnalytics`; `video_id + date + traffic_source_type` for `VideoTrafficSource`; `video_id + month + search_term` for `SearchTerm`; `target_video_id + month + referrer_video_id` for `RelatedVideo`; `date` for `FxRate`; `collector + video_id + period_key` for `SyncCoverage`.
- `GENERATED_KEYS` marks `SyncRun`, whose `id` SQLite generates when an insert omits it.
- `NON_DECREASING` marks `Video.own`, which an update may raise but never lower.

Column names come from the dataclass fields. `tests/test_database_reader.py` checks the table set and each class's fields against `PRAGMA table_info`, and `tests/test_database_writer.py` checks `KEYS` against each table's primary key.

### Filters

`database/filters.py::where_clause(Model, where)` builds the `WHERE` clause for `reader.select()`, `select_one()`, `scalar()`, and `writer.delete()`. `where` is a sequence of predicates combined with `AND`; an empty sequence produces no clause. Every column is qualified with the registry table name (`videos."id"`), every value is a bound parameter, and an unregistered class, unknown column, or unsupported operator raises `ValueError`.

A predicate is either a tuple condition or a `NotExists` value (exported as `database.NotExists`):

| Predicate | SQL |
|---|---|
| `(column, op, value)` with `=`, `!=`, `<`, `<=`, `>`, `>=`, `LIKE` | `table."column" op ?` |
| `(column, "=", None)` / `(column, "!=", None)` | `IS NULL` / `IS NOT NULL`. This is a SQL `NULL` comparison, unrelated to the writer leaving `None` fields out of upserts. |
| `(column, "IN", values)` | `IN (?, …)`; an empty collection becomes the always-false `0` |
| `(column, "NOT IN", values)` | `NOT IN (?, …)`; an empty collection becomes the always-true `1`, and the other predicates still apply. A `None` member raises `ValueError`, since SQL `NOT IN` with a `NULL` member matches nothing. |
| `NotExists(Inner, ((inner_column, outer_column), …))` | `NOT EXISTS (SELECT 1 FROM inner_table AS _innerN WHERE _innerN."inner_column" = table."outer_column" AND …)` |

`IN`/`NOT IN` values must be a collection; a bare string raises `ValueError` instead of matching its characters. `NotExists` needs at least one correlation, validates each inner column against `Inner` and each outer column against the filtered class, and gives its subquery a compiler-generated alias, so a class can be correlated against its own table. There is no raw-SQL predicate.

### Reads

 Identifiers that reach SQL come from the registry or from code-owned SQL; request strings never do, and every value is a bound parameter. An unregistered class, unknown field, unsupported operator, or unsupported aggregate raises `ValueError`.

| Call | Use |
|---|---|
| `select(Model, fields=None, *, where=(), order_by=(), limit=None, offset=None, distinct=False, conn=None) -> list[Model]` | One table. `SELECT` names only the requested columns; omitting `fields` selects all of them, and an empty tuple is rejected. `where` takes the predicates described in [Filters](#filters). `order_by` takes field names, with a leading `-` for descending. |
| `select_one(...) -> Model \| None` | `select()` with `LIMIT 1`. |
| `scalar(Model, aggregate, column, *, where=(), conn=None)` | `MIN`/`MAX`/`SUM`/`COUNT` of one column; `None` when `MIN`/`MAX`/`SUM` see no rows. |
| `fetch(Model, query, *, conn=None) -> list[Model]` | A code-owned `Query` whose result columns are all fields of one class. An alias that is not a field raises and names the alias. |
| `fetch_joined(query, models=(), values=(), *, conn=None) -> list[Joined]` | A code-owned `Query` returning several table components plus computed values. A column aliased `<table>__<field>` (built with `joined_columns(Model, alias, fields)`) goes to that class's instance; a column named in `values` goes to `Joined.values`. Any other column raises. `row[Video]` returns the typed component; a declared component with no selected columns is all `None`. |
| `fetch_scalar(query, *, conn=None)` | First column of the first row, or `None`, e.g. a page's `COUNT(*)`. |
| `connect(conn=None)` | Context manager that lends out one connection for several reads. |

`Query(sql, params)` is a frozen SQL-plus-parameters pair. Each read builds its objects from a single statement; there is no lazy relationship loading and no per-row follow-up query.

Connection ownership: a read given `conn=` uses it and never commits, rolls back, or closes it. A read without `conn` opens one through `get_connection()` and closes it afterwards. Reads that must share one connection (a page and its `COUNT`, or the statistics report's four queries) open it with `reader.connect()` and pass it to each call.

### Writes

| Call | Returns |
|---|---|
| `writer.write(row, *, conn=None) -> int` | `1` when the row was inserted or updated; `0` when a row holding only its key already exists |
| `writer.write_many(rows, *, conn=None) -> int` | The number of rows processed. All rows must be one class; mixing classes raises `ValueError`. Empty input returns `0` without opening a connection |
| `writer.delete(Model, *, where, conn=None) -> int` | The number of `Model` rows the one `DELETE` removed (`cursor.rowcount`), excluding rows removed by `ON DELETE CASCADE`; `0` when nothing matches |

Each row is written by matching its `KEYS` columns:
- **Update first:** an `UPDATE` sets every non-`None` field that is not a key. `Video.own` is set with `MAX(own, ?)`, so an owned video is never demoted. If no row matched, an `INSERT` follows with the same non-`None` fields.
- **Key-only rows:** a row with nothing but its key only checks whether the key exists, and inserts only if it doesn't.
- **`None` never overwrites:** a `None` field is left out of both statements, so an incoming `None` keeps the stored value, and on insert the column takes its schema default or `NULL`. `0`, `False` and `""` are written like any other value. There is no way to write SQL `NULL` over a stored value through the writer.
- **Partial rows:** a partial row can update an existing row even if it lacks fields required to insert one. A partial row for a new key fails the table's `NOT NULL`/`CHECK`/foreign-key constraints with `sqlite3.IntegrityError`, and the writer never invents values for it.
- **Keys:** a key field that is `None` raises `ValueError`. The one exception is a `SyncRun` with no `id`, which is inserted and gets a generated one. Other `UNIQUE` columns such as `comments.thread_id` and `comment_authors.youtube_channel_id` are not keys, so a clash on them raises `IntegrityError`.
- **Timestamps:** the writer never fills in timestamps. Callers set `updated_at`/`completed_at` themselves, normally from `database.now()`. A timestamp left `None` stays unchanged like any other field.
- **Order:** rows in one `write_many()` are applied in input order, so two rows for the same key end with the later one's non-`None` fields.
- **No `INSERT OR REPLACE`:** it would delete and re-insert the row and fire cascades.

Deletes:
- **Filter required:** `where` is keyword-only and takes the predicates in [Filters](#filters). An empty `where` raises `ValueError` before any connection opens, even on an empty table; there is no delete-all call.
- **One statement:** the matching set is removed by a single `DELETE FROM table WHERE …`, never by selecting IDs and deleting row by row.
- **Constraints stay on:** foreign-key cascades run as the schema defines them, and a `RESTRICT` violation (a referenced `comment_authors` row) raises `sqlite3.IntegrityError` and deletes nothing in that call.
- **Parameter limit:** an `IN`/`NOT IN` list longer than SQLite's bound-parameter limit fails with `sqlite3.OperationalError` and deletes nothing. The list is never split into several deletes, since splitting a `NOT IN` retention list would delete retained rows.

Transactions (upserts and deletes alike):
- **Owned connection (no `conn`):** each call opens a connection and starts `BEGIN IMMEDIATE`, so the update-or-insert decision holds the write lock and two writers can't both insert the same key. It commits on success, rolls back the whole call on any error, and closes the connection.
- **Materialized batch:** `write_many()` reads its whole input before opening the connection. An error while producing the rows therefore writes nothing.
- **Borrowed connection (`conn`):** the caller must already be inside a transaction (`ValueError` otherwise). The writer wraps its work in `SAVEPOINT writer`, rolls back to it on error, and never commits, rolls back, or closes the caller's transaction.

### Query specifications and reports

`database/queries.py` holds reusable SQL for joins, grouping, and ranking. Each function only builds and returns a `Query`, or a `(count, page)` pair for paged lists, plus the field and value-name tuples its callers serialize with. Routes and sync run those queries through the reader themselves, so no `queries.py` function reads the database.

| Specification | Result mapping |
|---|---|
| `owned_video_worklist(published_through=None)` | `fetch(Video, …)` → `id`, `title`, `published_at` |
| `playlist_owned_video_ids(playlist_id)` | `fetch(Video, …)` → `id` |
| `video_catalog(..., video_ids=None)` | `fetch_joined(…, (Video,), VIDEO_TOTAL_VALUES)` — the video list, one video (`video_ids=[id]`), and a playlist's videos (`video_ids=` its members) |
| `videos_published(..., video_ids=None)` | `fetch(Video, …)` → `PUBLISHED_VIDEO_FIELDS` |
| `playlist_catalog(..., playlist_id=None)` | `fetch_joined(…, (Playlist,), PLAYLIST_TOTAL_VALUES)` — the playlist list, or one playlist |
| `comment_feed(...)` | `fetch_joined(…, (Comment, CommentAuthor, Video))` |
| `top_videos_by_views(...)` | `fetch_joined(…, (Video,), TOP_VIDEO_VALUES)` |
| `search_term_totals(...)` | `fetch(SearchTerm, …)` → `search_term`, `views` |
| `videos_by_search_term(search_term, ...)` | `fetch_joined(…, (Video,), ("views",))` |
| `related_video_destinations(referrer_video_id, ...)` | `fetch_joined(…, (RelatedVideo, Video))` |

Functions that still do real calculation work stay in the domain modules and return report dictionaries:
- `get_video_stats()` in `database/video_statistics.py` (see *Video stats*), which runs its four queries through the reader on one borrowed connection.
- The analytics and traffic-source zero-fill reports.
- `get_top_videos_by_traffic_source()`, which takes the top N per source.
- `get_related_video_referrers()`, which adds the unfiltered total and nullable referrer metadata.
- `get_sync_runs()`, which pages by batch, assembles child runs, and picks the worst status.

These last four run their SQL through `get_connection()` directly.

## Ownership boundary

`videos.own` distinguishes a video the authenticated channel actually uploaded (confirmed via uploads-playlist membership or an exact `channel_id` match) from an external video whose metadata was only pulled in because it appeared as a Related Video referrer. Existing databases pick up the column via the standalone `backend/scripts/issue-48-migration.py` script (not part of `init_db()`); a fresh database gets it from `schema.sql` directly.

Videos are written through `writer.write()`, whose `NON_DECREASING` rule updates `own` as `MAX(own, ?)`. An existing `own=1` is never downgraded, and a row first written as `own=0` can later be promoted:

- `sync_videos()` writes confirmed-owned videos with `own=True`.
- Related referrer metadata resolution writes each referrer with `own` set to whether its `channel_id` matches this channel (see `sync.md`).

Owned-only reads:

- `routes/video_scope.py::require_owned_video(video_id)` — `reader.select_one(Video, ("id",), where=[("id", "=", video_id), ("own", "=", True)])`, raising 404 when nothing matches, so an external (`own=0`) video 404s exactly like a nonexistent one. `GET /videos/{video_id}` runs `video_catalog(video_ids=[video_id])`, which applies the same `v.own = 1` condition.
- `queries.owned_video_worklist(published_through=None)` — the worklist for Comments, Video Analytics, Video Traffic Sources, Search Insights, and Related Video Insights, fetched once per stage as `Video(id, title, published_at)` rows in processing order: dated rows by `published_at` ascending, then `id` ascending, and undated rows last by `id`. Stages read each video's title and publish date from these rows, so they make no per-video lookup.

  `published_through`, when given, is an inclusive date-only (`YYYY-MM-DD`) upper bound on `published_at`: a video published anywhere on that date or earlier is included. The comparison is a strictly-less-than bound against the *next* calendar day's midnight (`published_at < (published_through + 1 day) + "T00:00:00"`), not `<= published_through + "T23:59:59"` — the latter would wrongly exclude a same-day timestamp carrying a trailing `Z` (real `published_at` values from the YouTube API always do), since `"...T23:59:59Z"` sorts lexically after the literal string `"...T23:59:59"`. A video with no known `published_at` is always included regardless of this bound — a missing publish date is not evidence the video was uploaded after the range, so callers keep their own existing skip/fallback handling for it. Omitting the argument (the default) returns the complete owned worklist, unchanged — this is what Comments continues to use, since it has no period/year selection to bound against. The four period-aware sync stages (Video Analytics, Video Traffic Sources, Search Insights, Related Video Insights) pass their own effective range end here, before per-video progress or processing begins — see `sync.md`.
- `reader.select(Video, ("id",))` in `sync/stages.py::_resolve_related_video_metadata()` — deliberately unfiltered by ownership. It only checks whether an ID is already known at all (owned or external) before fetching fresh metadata for it; it is never a sync worklist.

Every other video-scoped read carries a `v.own = 1` (or joined-alias equivalent) condition: every `queries.py` video specification (through its shared `_video_conditions()`), the earliest-year `reader.scalar(Video, "MIN", "published_at", where=[("own", "=", True)])` in `routes/metadata.py` and `sync/plans.py`, `get_video_stats()`, and the reports in `database/analytics.py`, `database/traffic_sources.py`, and `database/related_videos.py`. As a result, so an external referrer's metadata row never leaks into channel-wide reporting. The `pruning` stage's delete carries `("own", "=", True)` alongside its `NOT IN` retention list, so it only ever deletes `own = 1` rows — an external row is never touched regardless of whether its ID appears in the retention set.

## Related Videos

`database/related_videos.py` stores and reports monthly Related Video referrer data, upsert-only (no delete-and-replace), matching `search_terms`'s own retention precedent — a referrer omitted or zeroed in a later sync is left untouched, not deleted.

- Writes: `sync/write_preparation.py::related_video_rows(target_video_id, month, referrers, *, updated_at)` validates the whole payload (month format, referrer ID/views shape), sums duplicate referrer IDs, drops non-positive totals, and returns `RelatedVideo` rows without touching the database. `sync_related_video_insights()` then checks the target is an owned video (Related rows only ever describe traffic *into* an owned target) and raises `ValueError` if not, before passing the rows to `writer.write_many()`. An empty prepared batch skips the check and writes nothing. A target with no `videos` row at all is also rejected by the foreign key.
- `get_related_video_referrers(start_date=None, end_date=None, content_type=None, privacy_status=None, title=None, video_ids=None, own=None, limit=None) -> {"items": [...], "total_named_views": int}` — referrers aggregated across owned target videos, summed across the months overlapping `start_date`/`end_date` (a missing bound is unbounded on that side, via the shared `_month_bound_conditions()` below), ordered by views descending then referrer ID ascending. `video_ids`/`content_type`/`privacy_status`/`title` all filter the *target* side (`title` matching the target's title or ID, never a referrer's — see the Title filter note below), with the same three-state `video_ids` scoping convention as the other aggregate helpers (`None` = every owned video, populated = that set, empty = no rows). `own` filters the *referrer* side: `True` matches only a referrer confirmed as this channel's own video; `False` matches everything else, including a referrer with no resolved metadata at all (`COALESCE(ref.own, 0) = 0` — an unresolved referrer is "not confirmed ours," so it belongs in the non-owned bucket, never in neither bucket); `None` (the default) returns every referrer regardless of ownership. `limit=None` returns every referrer. `total_named_views` is a second, independent query in the same call: the scope's unfiltered `SUM(views)` across every real referrer regardless of the `own`/`limit` filters, so a caller never has to fetch an unranked/uncapped row set just to total it.
- `queries.related_video_destinations(referrer_video_id, start_date=None, end_date=None, limit=None, video_ids=None)` — the top owned destination (target) videos for one given referrer, summed across the overlapping months, ordered by views descending then target ID ascending. It returns `RelatedVideo(target_video_id, views)` plus `Video(title, thumbnail_url, content_type)` components, which routes flatten to `{target_video_id, title, thumbnail_url, content_type, views}`. The referrer's own ownership is irrelevant to this query — any video, owned or external, can be a referrer. `video_ids` scopes the destination set the same three-state way.
- There is no persisted residual, no `period_start`/`period_end` columns on `related_videos` itself, and no read-time "unattributed" figure computed against aggregate Traffic Sources — the backend returns only real, stored `related_videos` rows, the same discipline `search_terms` follows (see [Search terms](#aggregation-and-filtering-semantics) below). `sync_coverage` (below) tracks *completion*, separately from this table, and is never read by any reporting/aggregation query.

A shared `_month_bound_conditions(alias, start_date, end_date)` (`database/connection.py`) builds independent `<alias>.month >= ?` / `<alias>.month <= ?` conditions from each date's `YYYY-MM` prefix; `queries.py` (`st` for search terms, `rv` for destinations) and `related_videos.py` (`rv`) use it with their own table alias.

## Sync coverage

The `sync_coverage` table persists, independently of any reporting table, which calendar months the four Analytics API stages (`video_analytics`, `video_traffic_sources`, `search_insights`, `related_video_insights` — these four strings are also the `collector` values) have successfully finished checking. It exists because a successful Analytics API response with zero reportable rows (e.g. a video with no views that month) leaves no reporting row anywhere, so a reporting table's `MAX(date)`/`MAX(month)` cannot distinguish "not checked yet" from "checked and genuinely empty." See `sync.md` for how the sync stages use this to select work; this section covers only the storage.

- Schema: `sync_coverage(collector, video_id, period_key, completed_at)`, `PRIMARY KEY (collector, video_id, period_key)`, `video_id REFERENCES videos(id) ON DELETE CASCADE`. `period_key` is always `"YYYY-MM"` — there is no daily or yearly granularity, and no `granularity` column: every collector uses the same month-shaped key, so a column that never varies would be dead weight. Video Analytics/Traffic Sources track completion by calendar month the same as Search/Related Insights do, even though their own API requests can span many months or years in one call (see `sync.md`) — the granularity of *what gets marked done* is independent of the granularity of *what gets requested*.
- Covered months are read in `sync/stages.py::_incremental_monthly_windows()` with `reader.select(SyncCoverage, ("period_key",), where=[collector =, video_id =, period_key >= start, period_key <= end])`, giving the `period_key`s already marked complete for one video/collector within an inclusive range.
- Months are marked complete by writing `SyncCoverage(collector, video_id, period_key, completed_at)` rows with `writer.write_many()`; `sync/stages.py::_coverage_rows()` builds one row per month with a shared `database.now()` timestamp. An already-complete month gets its `completed_at` refreshed. Callers must only pass periods whose request/response fully succeeded — the writer can't tell a genuine empty result from an unfinished one, so that guarantee is the caller's (`sync/stages.py`'s) responsibility.
- The coverage rows and the coverage read take `collector`/`video_id`/`period_key` as plain strings with no format or enum validation — every caller is sync-stage or migration code in this same codebase, not external input, so a typo'd collector name is a bug caught by tests/mypy, not a runtime input to defend against.
- `sync_coverage` is written and read exclusively by the sync stages (`sync/stages.py`) and the manual initializer (`scripts/issue-62-migration.py`, below) — no reporting/aggregation query anywhere joins against it or reads it, and it has no HTTP-facing shape in `api.md`.
- Comments and FX rates have no equivalent table: they keep boundaries derived from their own stored rows (the stored comment IDs from `reader.select(Comment, ("id",), where=[("video_id", "=", ...)])` for the overlap window, and the latest `reader.select_one(FxRate, ("date", "usd_to_sgd"), order_by=("-date",))`), since they're sourced from the Data API and Yahoo Finance respectively, outside this table's Analytics-API-only scope.

### Existing-database migration

`backend/scripts/issue-62-migration.py` is a standalone, one-time, idempotent script for an existing database: it reads only `videos.id`/`videos.own`/`videos.published_at` for `own = 1` rows and the local current date, then marks every calendar month from each owned video's publish month through the current month complete for all four collectors — with its own `INSERT … ON CONFLICT … DO UPDATE` statement executed against one connection, so the whole run commits as a single transaction. It never reads or writes any Analytics reporting table. This is an explicit operator baseline assertion, not an evidence backfill: unlike the runtime sync rule above, it declares a month done whether or not a corresponding reporting row exists, since a pre-existing database's Analytics history is trusted as already synced. It calls `init_db()` first so `sync_coverage` exists even on a pre-Issue-62 database, and is safe to rerun (identical resulting rows each time). See `backend/README.md` for when to run it.

## Relationships and deletion behavior

- `video_analytics.video_id → videos.id` **ON DELETE CASCADE**
- `video_traffic_sources.video_id → videos.id` **ON DELETE CASCADE**
- `playlist_items.playlist_id → playlists.id` **ON DELETE CASCADE**
- `playlist_items.video_id` has **no FK** — it's a raw YouTube video ID that may not exist in `videos` (e.g. a playlist item referencing a video not in the channel's own uploads)
- `comments.video_id → videos.id` **ON DELETE CASCADE**
- `search_terms.video_id → videos.id` **ON DELETE CASCADE**
- `related_videos.target_video_id → videos.id` **ON DELETE CASCADE**; `related_videos.referrer_video_id` has **no FK** — it's a raw YouTube video ID that may describe an external channel's video with no row in `videos` at all until metadata resolution runs (see [Related Videos](#related-videos))
- `sync_coverage.video_id → videos.id` **ON DELETE CASCADE** — deleting a video (via pruning) naturally cascades away its coverage state along with its reporting rows; there is no orphaned-coverage cleanup step
- `comments.author_id → comment_authors.id` **ON DELETE RESTRICT** — a commenter row cannot be deleted while any comment still references it
- Cascades only take effect because `PRAGMA foreign_keys = ON` is set on every connection

Comments are never deleted to reflect their removal on YouTube. Both sync scopes only insert and update, so a comment deleted upstream keeps its stored row; the only comment deletions come from the cascade when the `pruning` stage removes its parent video. The Comments stage's `writer.delete(CommentAuthor, where=[NotExists(Comment, (("author_id", "id"),))])` is the one commenter-side delete: it removes only rows no comment references any more, which is how the authors left behind by that cascade are cleaned up on the next successful Comments run. Because `author_id` is `RESTRICT`, this can never orphan a live comment.

`writer.delete()` reports only rows it directly deleted via `cursor.rowcount` — cascaded child-row deletes (e.g. `video_analytics` rows removed when their parent `videos` row is deleted) are **not** included in that count.

All application deletes are `writer.delete()` calls in `sync/stages.py`:

| Stage | Delete | Empty retention list |
|---|---|---|
| `playlists` | `writer.delete(PlaylistItem, where=[("playlist_id", "=", id)])` per playlist before its items are re-written | — |
| `playlists` | `writer.delete(Playlist, where=[("id", "NOT IN", ids)])` | skipped by the stage: an empty listing never clears stored playlists |
| `comments` | `writer.delete(CommentAuthor, where=[NotExists(Comment, (("author_id", "id"),))])` | — |
| `pruning` | `writer.delete(Video, where=[("own", "=", True), ("id", "NOT IN", ids)])` | runs: deletes every owned video, never an external one |

The `pruning` delete has **no empty-list guard**. It is opt-in and never runs automatically — see `sync.md` for how the caller is expected to only pass an empty list when that genuinely reflects a channel with zero owned videos.

## Timestamp behavior

`now()` (`database/connection.py`, exported as `database.now`) returns a timezone-aware UTC ISO 8601 string, e.g. `2026-07-17T08:30:45.123456+00:00`.

The writer never sets timestamps. Sync supplies `updated_at = now()` on every row it writes, and `completed_at = now()` on coverage rows; one timestamp is shared by all rows of one monthly insight batch and of one coverage call. `updated_at` therefore reflects "last successfully pulled and written," not "last changed." It updates even when a re-fetched row's values are identical to what's already stored. The sync-run lifecycle functions call `now()` for `started_at`/`completed_at` themselves.

`updated_at` is not present on `sync_runs` (has its own `started_at`/`completed_at`).

## Query conventions

- **Every** query uses parameterized `?` placeholders — never string-interpolated values. `f"..."` is used only to interpolate registry table and column names (reader, writer, and `filters.py`), compiler-generated subquery aliases, `queries.py` SQL fragments, or `ORDER BY` fragments looked up from a fixed mapping, never raw user input.
- Sort keys are looked up in explicit mappings in `database/queries.py` before being interpolated into `ORDER BY`:
  - `_VIDEO_SORT_COLUMNS` maps `published_at`, `view_count`, `comment_count`, `total_revenue_sgd` to `v.published_at`, `v.view_count`, `v.comment_count`, `total_revenue_sgd`; `video_catalog()` uses it for both the channel and playlist video lists.
  - `_PLAYLIST_SORT_COLUMNS` maps `published_at`/`item_count` to the aliased `playlists__published_at`/`playlists__item_count` result columns and `last_item_added`, `total_views`, `total_earnings_sgd` to themselves, since `playlist_catalog()` sorts the outer `SELECT * FROM (…)`.
  - An invalid `sort_by` silently falls back to the default column rather than erroring.
- `COMMENT_SORT_CLAUSES` (`database/queries.py`) maps each public comment sort value to a full `ORDER BY` fragment rather than a bare column, each ending in `c.id` so equal timestamps or like counts cannot shuffle rows between pages: `"newest"` → `c.published_at DESC, c.id DESC`; `"oldest"` → `c.published_at ASC, c.id ASC`; `"likes"` → `c.like_count DESC, c.published_at DESC, c.id DESC`. An unrecognized value falls back to `"newest"`; the HTTP layer rejects it first (see `api.md`).
- `queries.top_videos_by_views()` looks `sort_by` up in `_TOP_VIDEO_SORT_ORDER_BY` (`database/queries.py`), a mapping from public sort value to a full `ORDER BY` clause (aggregate plus deterministic tie-breakers), not a bare column name:
  - `"views"` → `period_views DESC, v.id ASC`
  - `"watch_time"` → `period_watch_time_hours DESC, period_views DESC, v.id ASC`
  - An unrecognized `sort_by` falls back to `"views"`, which is also the default.
- **Optional video scoping**: `video_ids: Collection[str] | None` scopes the retained reports `get_aggregated_analytics()`, `get_aggregated_traffic_sources()`, `get_top_videos_by_traffic_source()`, `get_related_video_referrers()`, and `get_video_stats()`, and the `queries.py` specifications `top_videos_by_views()`, `search_term_totals()`, `videos_by_search_term()`, and `related_video_destinations()`. There are no playlist-specific variants. The parameter has three distinct states, and the distinction between the last two is load-bearing:
  - `None` (the default, and what channel-wide routes pass): no video predicate at all, so the query stays channel-wide.
  - A populated collection: appends `v.id IN (?, ?, …)` with one bound `?` per ID. Only the placeholder count is interpolated; every ID is a bound parameter.
  - An explicitly empty collection: the retained reports return their natural empty shape *before opening a connection* — `[]`, `{}` for `get_top_videos_by_traffic_source()`, `{"items": [], "total_named_views": 0}` for referrers. The `queries.py` specifications append the always-false condition `0` instead (via `_video_conditions()`), so their query returns no rows. A truthiness check such as `if video_ids:` would collapse this state into `None` and leak channel-wide data to an empty playlist, so every caller tests `video_ids is not None` separately from emptiness.

  The argument is materialized once before placeholders are built (`queries._video_conditions()` also de-duplicates it with `dict.fromkeys`), so sets and other non-sequence collections behave consistently. The scope predicate composes with every other filter via `AND`; the `LIMIT` parameter stays last.

  `get_video_stats()` (`database/video_statistics.py`) accepts the same trailing `video_ids` with the same three states; its empty shape is `_empty_video_stats()`. It de-duplicates the collection (`list(dict.fromkeys(video_ids))`) before building placeholders and keeps its scope predicate (`v.own = 1` plus the `v.id IN (…)` list) separate from the title/content-type/privacy filters, because the analytics date-range query uses the scope alone — see *Video stats* below.
- All multi-table queries qualify columns with table aliases (`v.`, `va.`, `vts.`, `pi.`, `fx.`, `p.`) since `video_analytics` and `fx_rates` both have a `date` column, and other tables share `content_type`/`privacy_status`-adjacent names. Joined result columns are aliased `<table>__<field>`, so identical column names from different tables (`id`, `updated_at`) never collide.
- The known-IDs read in `_resolve_related_video_metadata()` has **no `ORDER BY`**; it is only used as a set.
- `get_video_stats()` (`database/video_statistics.py`) serves both channel and playlist statistics and runs several sequential queries on one connection opened with `reader.connect()` rather than one combined statement — the multi-query split is deliberate (see below). It has its own module, not `database/analytics.py`, since it's keyed off the video catalog (Legacy/New classification, lifetime comments/privacy counts) with analytics as a secondary join.
- `get_sync_runs(page, page_size)` (`database/sync_runs.py`) returns `tuple[list[dict], int]` — one page of **sync batches** plus the distinct-batch total. A batch is one `batch_id`, the ID `execute_plan()` generates once per submitted plan and shares across every stage that starts, so paging counts submitted syncs rather than stage rows. Each group is `{batch_id, started_at, status, run_count, rows_fetched, rows_written, rows_deleted, runs}`, where `status` comes from `_batch_status()` — the worst stage status by `_BATCH_STATUS_PRECEDENCE`, **failed > incomplete > running > cancelled > success**, falling back to an actual child status rather than `success` if an unrecognized value is ever stored. It takes no filters, so no statement has a `WHERE` clause other than the batch-ID lookup. Three statements run on one connection:
  - `SELECT COUNT(DISTINCT sr.batch_id)` — `total` is distinct batches, **not** stage rows, so `page_size` is a batch count.
  - The batch page: `SELECT sr.batch_id, MIN(sr.started_at) AS started_at … GROUP BY sr.batch_id ORDER BY started_at DESC, sr.batch_id DESC LIMIT ? OFFSET ?`. Ordering by the aggregate means a batch is placed by its *earliest* stage, so a long-running batch cannot jump ahead of one submitted later. `batch_id DESC` breaks ties between batches whose earliest stages share a timestamp.
  - The children: explicit columns for the paged batch IDs via a parameterized `IN (?, …)` list, `ORDER BY sr.started_at DESC, sr.id DESC`. Only the placeholder *count* is interpolated — every UUID stays a bound parameter, the same rule as the `video_ids` scoping helpers above. When the requested page selects no batches the helper returns early with the total rather than emitting an invalid empty `IN ()`.

  Paging over batch IDs before fetching children is what keeps a batch from being split across two pages, which a stage-row `LIMIT` could not guarantee. `run_count` and the three counters are then summed in Python from exactly the child rows placed in that response, so a group's parent totals always equal its own detail even if another sync starts mid-request. The `sr.id DESC` child tie-breaker gives rows sharing a `started_at` a total, stable order — the same discipline as `COMMENT_SORT_CLAUSES`, though collisions are far less likely here: `now()` (`database/connection.py`) stores microsecond-resolution ISO timestamps, so distinct inserts effectively never tie, whereas comment `published_at` values come from YouTube at second resolution and genuinely do. Offset paging can still shift when a new batch starts between page requests — acceptable for an append-only history with no snapshot requirement. `sync_runs.batch_id` has no dedicated index; the grouping and child lookup scan history, which current volume does not justify migrating.
- `cancel_sync_run(sync_run_id, rows_fetched, rows_written, rows_deleted)` (`database/sync_runs.py`) mirrors `complete_sync_run()`/`fail_sync_run()`: sets `status = 'cancelled'`, `completed_at`, and the three partial counters, but leaves `error_message` `NULL` — cancellation is not an error and carries no exception text. Called by `sync/orchestration.py`'s `_run_stage()` when a cooperative-cancellation checkpoint raises `SyncCancelled` (see `sync.md`); `status` needed no schema migration since it is plain `TEXT NOT NULL`.
- `mark_incomplete_sync_runs()` (`database/sync_runs.py`) is a startup-only sweep: `UPDATE sync_runs SET status = 'incomplete' WHERE status = 'running'`, returning `cursor.rowcount`. A row is created just before its stage begins and only leaves `running` when the stage completes or fails, so a killed process strands one forever — and `completed_at = null` cannot tell a stranded stage from a live one, since both have it. What makes the sweep sound is *when* it runs: `server.py`'s `lifespan` calls it right after `init_db()`, and at that moment the in-memory reservation guarding a real sync (`sync/status.py`) has died with the previous process, so no stage can legitimately still be running. **Calling it at any other time would mislabel active work.** `completed_at` is deliberately left null — the stage never completed — so `incomplete` rows still render an em dash in that column. A nonzero result is logged as a lifecycle WARNING. `status` is plain `TEXT NOT NULL` with no CHECK constraint, so the fourth value needed no migration; nothing else in the backend reads `sync_runs.status = 'running'` (`sync/status.py`'s `running` is the unrelated in-memory lifecycle state).
- `sync/scheduler.py::synced_today()` reads `reader.scalar(SyncRun, "MAX", "completed_at", where=[("status", "=", "success")])` — `MAX(completed_at)` across `sync_runs` rows with `status = 'success'`, or `None` when nothing has ever succeeded. It does not group by `batch_id`: a single succeeded run qualifies regardless of its `sync_type`, scope, or which other stages ran alongside it. Because the `MAX` is taken over successful rows only, a later failed or still-running row cannot hide an earlier success. `synced_today()` is itself used only by the uncalled `start_background_scheduler()` — see `sync.md`.

## Aggregation and filtering semantics

- **Lifetime vs. period totals**: the `total_revenue_sgd` / `total_watch_time_hours` values from `queries.video_catalog()` are lifetime sums with no date filter applied, computed via `LEFT JOIN video_analytics` + `LEFT JOIN fx_rates`. Endpoints under `/analytics/*` (e.g. `queries.top_videos_by_views()`, `get_aggregated_analytics()`) compute period-scoped sums bounded by `start_date`/`end_date` instead — same join pattern, but with date conditions applied.
- **Currency conversion**: `estimated_revenue_sgd` / `total_revenue_sgd` / `total_earnings_sgd` are always computed as `estimated_revenue * usd_to_sgd`, joined via `fx_rates.date = video_analytics.date` (or `DATE(va.date)` in the playlist-earnings subquery in `queries.playlist_catalog()` — same semantic result, slightly different SQL form). A missing FX row for a given date means that date's revenue contributes `NULL`, `COALESCE`d to `0`.
- **Date filters**: filters against `published_at` (`videos`, `playlists`) use `>= start_date` and `<= end_date + "T23:59:59"` since `published_at` is a full timestamp; filters against `date` columns (`video_analytics.date`, `video_traffic_sources.date`) use plain `>= start_date` / `<= end_date` since those are date-only strings. Mixing these up would silently exclude the final day of a range.
- **Title filter**: every video-title `title`/`video_title` parameter across the backend — the `queries.py` specifications through their shared `_video_conditions()` (`video_catalog`, `videos_published`, `top_videos_by_views`, `search_term_totals`, `videos_by_search_term`, and `video_title` in `comment_feed`); `get_video_stats()`; `get_aggregated_analytics()`; `get_aggregated_traffic_sources()`, `get_top_videos_by_traffic_source()`; and the target-video filter in `get_related_video_referrers()` — matches the corresponding video's **title or ID**: when non-empty, it appends the grouped condition `(v.title LIKE ? OR v.id LIKE ?)`, binding `f"%{title}%"` twice, combined with any other supplied condition via `AND`. `get_related_video_referrers()`'s `title` matches only the *target* video's ID, never a referrer's. The playlist-catalog `title` filter in `queries.playlist_catalog()` matches `(p.title LIKE ? OR p.id LIKE ?)` the same way, against the playlist's own ID. When a `video_ids` scope is also supplied, the filter is additive to it, not a replacement — a match outside the scoped set still yields no row. An omitted or empty value leaves the query unchanged from before this filter existed.
- **Grouping — analytics rows**: `get_aggregated_analytics()` (`database/analytics.py`) groups by `(date, content_type)` — a video-day and a short-day on the same date are two separate rows, never summed together. `get_video_analytics()` (single video, also `database/analytics.py`) doesn't need to group by `content_type` in SQL since a video only has one, but still tags every row with it.
- **Zero-filling — analytics**: `_zero_fill_analytics()` (`database/analytics.py:35-54`) inserts a `{date, content_type}` row with all-zero metric values for every day in `[start_date or min(dates), end_date or max(dates)]` not already present, for each `content_type` in the requested set (`[content_type]` if filtered, else `["video", "short"]`). It then trims trailing zero-only rows past the last date that actually has data, so a chart doesn't extend zero-filled into the future beyond real data. It lives in `database/analytics.py` and is shared by every caller in that same module (`get_video_analytics`, `get_aggregated_analytics`).
- **Zero-filling — traffic sources**: `_zero_fill_traffic_sources()` (`database/traffic_sources.py`) inserts a `{date, traffic_source_type}` row with all-zero metric values for every day in `[start_date or min(dates), end_date or max(dates)]` not already present, for each traffic source type actually present in the result set. It then trims trailing zero-only rows past the last date that actually has data, the same daily-fill contract as `_zero_fill_analytics()`. It lives in `database/traffic_sources.py`, self-contained from the analytics zero-fill helper.
- **Top-N per traffic source type**: `get_top_videos_by_traffic_source()` (`database/traffic_sources.py`) fetches rows ordered `(traffic_source_type, views DESC)` in SQL, then `_top_n_per_source()` (`database/traffic_sources.py`) truncates each group in Python — this only works correctly because the SQL `ORDER BY` guarantees each group arrives pre-sorted by views descending. The DB helper itself defaults `limit=3`; `routes/analytics.py` passes `limit=10` explicitly for both the channel-wide and the playlist-scoped endpoint.
- **Playlist membership resolution**: `queries.playlist_owned_video_ids(playlist_id)`, run by `routes/video_scope.py::resolve_playlist_video_ids()`, is the single source of a playlist's scope for statistics, the playlist video list, analytics, and `/videos/published?playlist_id=`. It selects `DISTINCT v.id` over `playlist_items pi JOIN videos v ON v.id = pi.video_id WHERE pi.playlist_id = ?`, which does three things at once: duplicate `playlist_items` rows for the same video collapse to one ID (only `playlist_items.id` is unique, so duplicate `(playlist_id, video_id)` pairs are possible and would otherwise multiply aggregates); a `NULL` `video_id` is dropped; and a dangling `video_id` with no `videos` row is dropped, since `playlist_items.video_id` has no FK (see above). A playlist with no valid members — and an unknown playlist ID — both yield `[]`, which is why the resolver establishes existence first via `require_playlist(playlist_id)`, a `reader.select_one(Playlist, ("id",), where=[("id", "=", playlist_id)])` that computes no aggregates. The scoped query helpers, including `get_video_stats()`, never touch `playlist_items` themselves; they only see the resolved ID collection.
- **Top videos — period metrics**: `queries.top_videos_by_views()` returns `Video(id, title, published_at, thumbnail_url, content_type)` plus `period_views`, `period_earnings_sgd`, and `period_watch_time_hours` (`SUM(va.watch_time_minutes) / 60.0`) computed from the same filtered `video_analytics` rows, scoped by the optional `start_date`/`end_date`/`content_type`/`privacy_status`/`video_ids` filters (applied to `va.date` and `v.*`, not `v.published_at`). `LIMIT` is applied after the `ORDER BY`, so ranking always happens over the full filtered set before truncating to the top N.
- **Video stats — Legacy/New classification**: `get_video_stats()` (`database/video_statistics.py`, plus the `_empty_video_stats()` default template that is also its empty-scope result) classifies each video as Legacy (`published_at` strictly before the effective start date) or New (`published_at` between the effective start and end dates, inclusive), or neither if published after the effective end date. It runs four queries on one connection opened with `reader.connect()`, each through `reader.fetch_joined()` with named `values`: (1) the available `video_analytics` date range and (2) the catalog's `published_at` range, together used to derive the effective start/end when `start_date`/`end_date` are omitted; (3) a catalog query that counts Legacy/New videos per content type and computes lifetime comment/privacy-status totals directly from `videos` (no analytics join, so no multiplication risk); (4) a period-performance query that pre-aggregates `video_analytics` per `video_id` in a subquery (summing views and `estimated_revenue * fx_rates.usd_to_sgd`) before joining to `videos`, then groups by Legacy/New bucket and content type — the subquery pre-aggregation is what keeps the `fx_rates` join (1 row per `date`, per the `fx_rates` schema) from inflating sums. Each omitted bound falls back independently, in order, to the `video_analytics` date range, then the catalog's `published_at` range (truncated to a date) if no analytics rows exist at all — in that fallback case period views/earnings are zero but Legacy/New classification and counts still work. The `video_analytics` range covers every owned video in the base scope (the whole channel, or the `video_ids` set) and ignores the title/content-type/privacy filters, so filtering never moves a default date taken from analytics; the `published_at` fallback range, the catalog query, and the period query all apply those filters, so when the scope has no analytics rows the filters can change the fallback dates. A video with a `NULL` `published_at` is never classified Legacy or New but still contributes to comment/status totals. Lifetime comments and current privacy status are never restricted by date.

- **Comment reads**: the three comment routes share `queries.comment_feed()`, which joins `comments c` to `comment_authors ca` and `videos v` (restricted to `v.own = 1`) and selects every `Comment` column plus `CommentAuthor(youtube_channel_id, display_name, profile_image_url, channel_url)` and `Video(title, content_type, thumbnail_url)`. `routes/comments.py` flattens these with `to_dict(..., prefix="author_")`/`prefix="video_"` into `author_youtube_channel_id`, `author_display_name`, `author_profile_image_url`, `author_channel_url`, `video_title`, `video_content_type`, and `video_thumbnail_url` alongside every comment column. Filters are `c.text` and `ca.display_name` via `LIKE ?` bound to `f"%{value}%"`, `video_title` matching the parent video's title or ID (see the Title filter note above), `v.content_type`, and a `c.published_at` range using the full-timestamp convention above (`>= start_date`, `<= end_date + "T23:59:59"`). The video scope adds `c.video_id = ?`; the playlist scope adds `EXISTS (SELECT 1 FROM playlist_items pi WHERE pi.playlist_id = ? AND pi.video_id = c.video_id)`, so a video listed twice in a playlist still yields each of its comments once — the `EXISTS` is the comment-side equivalent of the `SELECT DISTINCT` dedup `playlist_owned_video_ids()` performs for the scoped queries. Both scopes count and page over the same filtered set. The video-scoped route passes no `video_title` or `content_type` filter, since a fixed video determines both.

- **Search terms**: `sync/write_preparation.py::search_term_rows(video_id, month, terms, *, updated_at)` turns one month's `{"search_term": str, "views": int}` response rows into `SearchTerm` rows, and `sync_search_insights()` writes them with one `writer.write_many()` call. Duplicate exact term keys are summed, non-positive totals are dropped, and a malformed row (empty/non-string term, non-int views) or a `month` not matching `^\d{4}-(0[1-9]|1[0-2])$` raises `ValueError` before anything is written. A term omitted or zeroed by a later call is left untouched, never deleted — the only deletion path is the `videos` cascade. The write returns the number of rows processed, including unchanged refreshed rows.

  Two `queries.py` specifications share `_month_bound_conditions("st", start_date, end_date)` (`database/connection.py`), which builds independent `st.month >= ?` / `st.month <= ?` conditions from each date's `YYYY-MM` prefix — a missing bound is unbounded on that side (same convention as `traffic_sources.py`/`analytics.py`'s own date filters), and `start_date > end_date` yields no rows since no month satisfies both:
  - `search_term_totals(start_date=None, end_date=None, content_type=None, privacy_status=None, title=None, video_ids=None, limit=None)` — terms summed across owned videos and mapped onto `SearchTerm(search_term, views)`, with the same `video_ids` three-state scoping convention as above. One video's own terms are the same query with `video_ids=[video_id]`. `limit=None` (the default) returns every term; a caller wanting a capped "top N" list passes `limit` explicitly — there is no separate top-terms specification, since the only difference is a `LIMIT` clause.
  - `videos_by_search_term(search_term, start_date=None, end_date=None, content_type=None, privacy_status=None, title=None, limit=10, video_ids=None)` — the top videos for **one specific term**, not a grouped-by-every-term query: `Video(id, title, thumbnail_url, content_type)` plus the summed `views` value. It adds `st.search_term = ?` to the same conditions.

  Both order by views descending (ties by ascending term text or video id), and none compute a read-time "unattributed" residual against `video_traffic_sources` — that concept was considered during planning and explicitly rejected; the backend returns only real, stored `search_terms` rows.

## Compatibility constraints

- Adding a new sortable column requires adding it to both the relevant sort mapping (`database/queries.py`'s `_VIDEO_SORT_COLUMNS` or `_PLAYLIST_SORT_COLUMNS`) *and* the frontend's `SortKey` type (see `frontend.md`) — the backend will silently ignore an unrecognized `sort_by` rather than reject it.
- `_zero_fill_analytics` assumes all rows passed in share the same set of non-`(date, content_type)` keys (it derives the "zero" template from `rows[0]`) — a query that ever returned heterogeneous column sets across rows would break this.
- Because every sync write supplies a fresh `updated_at`, this column cannot be used to detect "did the underlying value actually change since last sync" — only "was this row touched by the most recent sync."
- Imports inside `database/` flow one way: `reader.py` imports `connection.py` and `dataclasses/`; `queries.py` imports `reader.py`, `dataclasses/`, and `connection.py`; `video_statistics.py` imports `reader.py`. The domain modules depend only on `connection.py`, and nothing imports back through the package facade (`database/__init__.py`). Playlist membership is resolved by the route layer and passed in as `video_ids`, which keeps the scoped reports and specifications usable with any caller-supplied set of videos.
- The retained reports take `video_ids` **after** every other parameter, and the `queries.py` specifications take it keyword-only; callers pass it by keyword. It binds one `?` per ID, so a scope is bounded by SQLite's parameter limit — practical for playlist-sized collections, not for arbitrarily large ID sets.
- `backend/scripts/issue-48-migration.py` is a standalone, one-time script for adding `videos.own` to a pre-existing database (idempotent — checks `PRAGMA table_info(videos)` before altering). It is intentionally not wired into `init_db()`: a one-time fixup doesn't belong in code that runs on every app start.
- The writer's `MAX(own, ?)` rule for `Video.own` means `own` can only ever move from `0` to `1` over a row's lifetime, never back — there is no code path that demotes a confirmed-owned video to external.
- Since the writer leaves `None` fields out, a value that later comes back empty from the API (say, a description removed on YouTube) keeps its previously stored value rather than being cleared.
- `backend/scripts/issue-62-migration.py` (see [Sync coverage](#sync-coverage)) is likewise standalone and not wired into `init_db()`, but unlike `issue-48-migration.py` it doesn't alter the schema — `sync_coverage` already exists on any database via `CREATE TABLE IF NOT EXISTS`, so this script only inserts baseline completion rows. It raises `ValueError` and writes nothing if any owned video lacks a `published_at`, rather than guessing a start date for it.
