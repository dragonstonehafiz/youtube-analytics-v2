# Database Reference

## Purpose

Persistence layer, schema, row dataclasses, the shared reader and writer, and query conventions. Owns everything about how data is stored, read, written, related, and aggregated. Sync-side write patterns (what sync writes and when) live in `sync.md`; HTTP-facing shapes live in `api.md`.

## Authoritative source files

- `backend/schema.sql`
- `backend/database/dataclasses/` (one row dataclass per table), `backend/database/tables.py`, `backend/database/filters.py`, `backend/database/reader.py`, `backend/database/writer.py`, `backend/database/reports/`
- `backend/database/connection.py`
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

`get_connection()` (`database/connection.py:17-24`) returns a `sqlite3.Connection` with:

- `row_factory = sqlite3.Row`
- `PRAGMA foreign_keys = ON` — set on every connection, not just once at startup
- `PRAGMA journal_mode = WAL`
- `PRAGMA busy_timeout = 30000` (30s)

`init_db()` (`database/connection.py:27-32`) creates tables from `schema.sql` via `executescript()` if they don't already exist; it does not run migrations. Both the database and schema paths are resolved from the backend root (`Path(__file__).parent.parent`, i.e. one level above the `database/` package), so they always resolve to `backend/data/youtube.db` and `backend/schema.sql` regardless of which module inside the package imports them.

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

Reads go through `database/reader.py`; inserts, updates, and deletes go through `database/writer.py`. Both use the table registry in `database/tables.py` and the WHERE compiler in `database/filters.py`. The writer imports the reader only to read back `returning` fields on its own connection; the reader never imports the writer. Sync-run lifecycle rows are written through the writer like any other row (see `sync.md`).

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

`database/filters.py::where_clause(Model, where)` builds the `WHERE` clause for `reader.select()`, `select_one()`, `scalar()`, `writer.update()`, and `writer.delete()`. `where` is a sequence of predicates combined with `AND`; an empty sequence produces no clause. Every column is qualified with the registry table name (`videos."id"`), every value is a bound parameter, and an unregistered class, unknown column, or unsupported operator raises `ValueError`.

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
| `select(Model, fields=None, *, where=(), order_by=(), limit=None, offset=None, distinct=False, fill_dates=None, conn=None) -> list[Model]` | One table. `SELECT` names only the requested columns; omitting `fields` selects all of them, and an empty tuple is rejected. `where` takes the predicates described in [Filters](#filters). `order_by` takes field names, with a leading `-` for descending. |
| `select_one(...) -> Model \| None` | `select()` with `LIMIT 1`. |
| `scalar(Model, aggregate, column, *, where=(), conn=None)` | `MIN`/`MAX`/`SUM`/`COUNT` of one column; `None` when `MIN`/`MAX`/`SUM` see no rows. |
| `fetch(Model, query, *, fill_dates=None, conn=None) -> list[Model]` | A code-owned `Query` whose result columns are all fields of one class. An alias that is not a field raises and names the alias. |
| `fetch_joined(query, models=(), values=(), *, fill_dates=None, conn=None) -> list[Joined]` | A code-owned `Query` returning several table components plus computed values. A column aliased `<table>__<field>` (built with `joined_columns(Model, alias, fields)`) goes to that class's instance; a column named in `values` goes to `Joined.values`. Any other column raises. `row[Video]` returns the typed component; a declared component with no selected columns is all `None`. |
| `fetch_scalar(query, *, conn=None)` | First column of the first row, or `None`, e.g. a page's `COUNT(*)`. |
| `connect(conn=None)` | Context manager that lends out one connection for several reads. |
| `group_by(results, field, *, limit=None) -> dict[value, list]` | Groups already-ordered read results by one field's value, in first-seen order, keeping at most `limit` results per group. It returns the original objects, unmodified, in input order; it runs no SQL. |

`Query(sql, params)` is a frozen SQL-plus-parameters pair. Each read builds its objects from a single statement; there is no lazy relationship loading and no per-row follow-up query.

A field reference (`reader.FieldRef`) names a result field: a column name for `select()`/`fetch()` results, and on `fetch_joined()` results either `(RowClass, field)` for a component or a computed value name.

#### Date filling

`fill_dates=DateFill(...)` makes `select()`, `fetch()`, or `fetch_joined()` add a synthetic row for every missing day of a daily series. Reads without it are unchanged, and no paginated read uses it. Filling runs in Python over the one statement's results and never writes anything back.

| `DateFill` field | Meaning |
|---|---|
| `date` | The `YYYY-MM-DD` date field. |
| `metrics` | Mapping of field → default value. Only these fields get a default on synthetic rows. |
| `start_date` | The requested start. Filling starts here (or at the series' first observed date) and ends at the series' last observed date, across all its breakdown values, so days after the last observation are never filled up to the requested end. |
| `identifiers` | Fields that identify one series, e.g. `video_id`. Empty means the whole result is one series (a query already fixed to one video, or an aggregate that has no video identity). |
| `breakdown`, `breakdown_values` | Optional field filled once per value on each day, e.g. content type or traffic-source type. `breakdown_values=None` uses the values observed for that identifier, sorted. Explicit values come first and may include values with no rows; any other observed values follow, sorted. |
| `constants` | Fields copied into a series' synthetic rows from its first observed row, e.g. the video's content type. |

Rules:
- An empty result stays empty.
- Each series is filled independently: breakdown values observed for one identifier are never added to another.
- Output is ordered by identifier (first-seen order), date, then breakdown order. Real rows are returned as they were read, including `NULL` metrics.
- A synthetic row holds the date, identifiers, breakdown value, constants, and metric defaults. Every other component field is `None`, and on joined results every declared computed value not listed in `metrics` or `constants` is `None`.
- Two results with the same identifier, date, and breakdown value raise `ValueError`, as does any reference to a field outside the result's projection (checked before rows are built).

Connection ownership: a read given `conn=` uses it and never commits, rolls back, or closes it. A read without `conn` opens one through `get_connection()` and closes it afterwards. Reads that must share one connection (a page and its `COUNT`, or the statistics report's four queries) open it with `reader.connect()` and pass it to each call.

### Writes

| Call | Returns |
|---|---|
| `writer.write(row, *, conn=None) -> int` | `1` when the row was inserted or updated; `0` when a row holding only its key already exists |
| `writer.write(row, *, returning=(fields…), conn=None) -> Row` | A new instance of the row's class holding the named fields as stored after the write; every other field is `None`, and the input row is not changed. See [Returned fields](#returned-fields) |
| `writer.write_many(rows, *, conn=None) -> int` | The number of rows processed. All rows must be one class; mixing classes raises `ValueError`. Empty input returns `0` without opening a connection |
| `writer.update(row, *, where, conn=None) -> int` | The number of rows the one `UPDATE` changed; `0` when nothing matches. See [Filtered updates](#filtered-updates) |
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

#### Filtered updates

`writer.update(row, where=...)` sets the row's non-`None`, non-key fields on every row matching `where`, in one `UPDATE … SET … WHERE …`. It never inserts, so a missing key changes nothing and returns `0`.
- `where` takes the predicates in [Filters](#filters) and must not be empty (`ValueError`).
- Setting a key field raises `ValueError`; name the row to change in `where` instead.
- Assignments follow the upsert rules: `None` fields are left out, falsy values are written, `Video.own` is set with `MAX(own, ?)`, and timestamps are whatever the caller supplies.
- A row with no assignable fields returns `0` after the class and predicates are checked, without opening a connection.

#### Returned fields

`write(row, returning=(…))` writes the row exactly as `write()` does, then reads the named fields back by the resolved primary key on the same connection, before the transaction ends. For a `SyncRun` inserted without an `id`, the key comes from the insert cursor's `lastrowid`, never from `MAX(id)`. The returned values are what is stored: schema defaults, a `Video.own` that stayed `True`, or the existing values after a key-only no-op. The field names are checked (unknown or empty → `ValueError`) before anything is written. On a borrowed connection the returned row is still subject to the caller's later rollback. `write_many()` has no `returning` option.

Deletes:
- **Filter required:** `where` is keyword-only and takes the predicates in [Filters](#filters). An empty `where` raises `ValueError` before any connection opens, even on an empty table; there is no delete-all call.
- **One statement:** the matching set is removed by a single `DELETE FROM table WHERE …`, never by selecting IDs and deleting row by row.
- **Constraints stay on:** foreign-key cascades run as the schema defines them, and a `RESTRICT` violation (a referenced `comment_authors` row) raises `sqlite3.IntegrityError` and deletes nothing in that call.
- **Parameter limit:** an `IN`/`NOT IN` list longer than SQLite's bound-parameter limit fails with `sqlite3.OperationalError` and deletes nothing. The list is never split into several deletes, since splitting a `NOT IN` retention list would delete retained rows.

Transactions (upserts, updates, and deletes alike):
- **Owned connection (no `conn`):** each call opens a connection and starts `BEGIN IMMEDIATE`, so the update-or-insert decision holds the write lock and two writers can't both insert the same key. It commits on success, rolls back the whole call on any error, and closes the connection.
- **Materialized batch:** `write_many()` reads its whole input before opening the connection. An error while producing the rows therefore writes nothing.
- **Borrowed connection (`conn`):** the caller must already be inside a transaction (`ValueError` otherwise). The writer wraps its work in `SAVEPOINT writer`, rolls back to it on error, and never commits, rolls back, or closes the caller's transaction.

### Reports

`database/reports/` holds every read that joins, groups, ranks, or pages. Each report function takes filters and scope, keeps its SQL next to its reader calls, date filling, grouping, and serialization, and returns a finished result. Callers never receive a `Query` or `Joined`. Routes add only an `{items: …}` or `{item: …}` envelope, validation, and 404s. Simple one-table checks (`reader.select_one()`, `reader.scalar()`) stay with their callers.

| Module | Function | Returns |
|---|---|---|
| `analytics.py` | `daily_analytics(..., video_ids=None, fill_content_types=("video", "short"))` | `list[dict]` of `date`, `content_type`, the eight metrics, and `estimated_revenue_sgd` per date and content type, date-filled |
| | `top_videos(..., sort_by="views", limit=10, video_ids=None)` | `list[dict]` of `id`, `title`, `published_at`, `thumbnail_url`, `content_type`, `period_views`, `period_earnings_sgd`, `period_watch_time_hours` |
| `traffic.py` | `daily_traffic_sources(..., video_ids=None)` | `list[dict]` of `date`, `traffic_source_type`, `views`, `watch_time_minutes`, date-filled |
| | `top_videos_by_traffic_source(..., video_ids=None)` | `dict[source, list[dict]]`, at most ten videos per source |
| | `search_terms(..., video_ids=None, limit=None)` | `list[dict]` of `search_term`, `views` |
| | `videos_by_search_term(search_term, ..., limit=10, video_ids=None)` | `list[dict]` of `id`, `title`, `thumbnail_url`, `content_type`, `views` |
| | `related_video_referrers(..., video_ids=None, own=None, limit=None)` | `{items, total_named_views}` |
| | `related_video_destinations(referrer_video_id, ..., limit=None, video_ids=None)` | `list[dict]` of `target_video_id`, `title`, `thumbnail_url`, `content_type`, `views` |
| `catalog.py` | `video_listing(*, fields=None, page=1, page_size=50, ..., video_ids=None)` | Owned videos as the chosen `fields` (see [Video listing fields](#video-listing-fields)): `{items, total, page, page_size}` for a page, or `{items}` with every match and no count when `page_size=None` |
| | `playlist_listing(...)` | `{items, total, page, page_size}` of playlists with membership totals |
| | `video_detail(video_id)` / `playlist_detail(playlist_id)` | the item `dict`, or `None` |
| | `playlist_video_ids(playlist_id)` | `list[str]` |
| | `owned_video_worklist(published_through=None)` | `list[Video]` holding `id`, `title`, `published_at` |
| `comments.py` | `comment_feed(*, page, page_size, sort_by, ..., video_id=None, playlist_id=None)` | `{items, total, page, page_size}` |
| `video_statistics.py` | `get_video_stats(title, start_date, end_date, content_type, privacy_status, video_ids=None)` | the Legacy/New statistics `dict` (see *Video stats*) |
| `sync_history.py` | `sync_batches(*, page, page_size)` | `{items, total, page, page_size}` of batches with their runs |

`reports/_conditions.py` holds the shared SQL fragments: `video_conditions()` (owned-video scope and filters on alias `v`), `published_bounds()`, `date_bounds()`, `month_bounds()`, and `limit_clause()`. It builds no complete query and reads nothing.

A report with a page and its count, or several reads, runs them on one `reader.connect()` connection. Details run no count query. Callers import report modules explicitly (`from database.reports import catalog`); the reports import only `database` modules, never `routes` or `sync`.

#### Video listing fields

`catalog.video_listing(fields=...)` returns items with exactly the named keys, in the given order. A name is either a `Video` column or one of the two lifetime totals: `total_revenue_sgd` (`SUM(estimated_revenue * usd_to_sgd)`, needing the `video_analytics` and `fx_rates` joins) and `total_watch_time_hours` (`SUM(watch_time_minutes) / 60.0`, needing only `video_analytics`). `fields=None` selects every `Video` column plus both totals. The query joins and groups only when a selected total, or a `sort_by="total_revenue_sgd"`, needs it, so a read of plain columns touches `videos` alone; a total used only for sorting is computed but not returned. An unknown name raises `ValueError` from the reader's field check. The count query always reads `videos` alone. `GET /videos/published` uses `fields=("id", "title", "published_at", "thumbnail_url", "content_type")`, `page_size=None`, and ascending `published_at`; `video_detail()` shares the same query builder with the full default projection and no count.

## Ownership boundary

`videos.own` distinguishes a video the authenticated channel actually uploaded (confirmed via uploads-playlist membership or an exact `channel_id` match) from an external video whose metadata was only pulled in because it appeared as a Related Video referrer. Existing databases pick up the column via the standalone `backend/scripts/issue-48-migration.py` script (not part of `init_db()`); a fresh database gets it from `schema.sql` directly.

Videos are written through `writer.write()`, whose `NON_DECREASING` rule updates `own` as `MAX(own, ?)`. An existing `own=1` is never downgraded, and a row first written as `own=0` can later be promoted:

- `sync_videos()` writes confirmed-owned videos with `own=True`.
- Related referrer metadata resolution writes each referrer with `own` set to whether its `channel_id` matches this channel (see `sync.md`).

Owned-only reads:

- `routes/video_scope.py::require_owned_video(video_id)` — `reader.select_one(Video, ("id",), where=[("id", "=", video_id), ("own", "=", True)])`, raising 404 when nothing matches, so an external (`own=0`) video 404s exactly like a nonexistent one. `GET /videos/{video_id}` calls `catalog.video_detail(video_id)`, which applies the same `v.own = 1` condition.
- `catalog.owned_video_worklist(published_through=None)` — the worklist for Comments, Video Analytics, Video Traffic Sources, Search Insights, and Related Video Insights, returned once per stage as `Video(id, title, published_at)` rows in processing order: dated rows by `published_at` ascending, then `id` ascending, and undated rows last by `id`. Stages read each video's title and publish date from these rows, so they make no per-video lookup.

  `published_through`, when given, is an inclusive date-only (`YYYY-MM-DD`) upper bound on `published_at`: a video published anywhere on that date or earlier is included. The comparison is a strictly-less-than bound against the *next* calendar day's midnight (`published_at < (published_through + 1 day) + "T00:00:00"`), not `<= published_through + "T23:59:59"` — the latter would wrongly exclude a same-day timestamp carrying a trailing `Z` (real `published_at` values from the YouTube API always do), since `"...T23:59:59Z"` sorts lexically after the literal string `"...T23:59:59"`. A video with no known `published_at` is always included regardless of this bound — a missing publish date is not evidence the video was uploaded after the range, so callers keep their own existing skip/fallback handling for it. Omitting the argument (the default) returns the complete owned worklist, unchanged — this is what Comments continues to use, since it has no period/year selection to bound against. The four period-aware sync stages (Video Analytics, Video Traffic Sources, Search Insights, Related Video Insights) pass their own effective range end here, before per-video progress or processing begins — see `sync.md`.
- `reader.select(Video, ("id",))` in `sync/stages.py::_resolve_related_video_metadata()` — deliberately unfiltered by ownership. It only checks whether an ID is already known at all (owned or external) before fetching fresh metadata for it; it is never a sync worklist.

Every other video-scoped read carries a `v.own = 1` (or joined-alias equivalent) condition: every report video query (through the shared `_conditions.video_conditions()`), including the daily analytics and traffic-source reports, the earliest-year `reader.scalar(Video, "MIN", "published_at", where=[("own", "=", True)])` in `routes/metadata.py` and `sync/plans.py`, `get_video_stats()`, and the target side of `traffic.related_video_referrers()`. As a result, an external referrer's metadata row never leaks into channel-wide reporting. The `pruning` stage's delete carries `("own", "=", True)` alongside its `NOT IN` retention list, so it only ever deletes `own = 1` rows — an external row is never touched regardless of whether its ID appears in the retention set.

## Related Videos

Monthly Related Video referrer data is stored upsert-only (no delete-and-replace), matching `search_terms`'s own retention precedent — a referrer omitted or zeroed in a later sync is left untouched, not deleted.

- Writes: `sync/write_preparation.py::related_video_rows(target_video_id, month, referrers, *, updated_at)` validates the whole payload (month format, referrer ID/views shape), sums duplicate referrer IDs, drops non-positive totals, and returns `RelatedVideo` rows without touching the database. `sync_related_video_insights()` then checks the target is an owned video (Related rows only ever describe traffic *into* an owned target) and raises `ValueError` if not, before passing the rows to `writer.write_many()`. An empty prepared batch skips the check and writes nothing. A target with no `videos` row at all is also rejected by the foreign key.
- `traffic.related_video_referrers(start_date=None, end_date=None, content_type=None, privacy_status=None, title=None, video_ids=None, own=None, limit=None)` runs a total query and a ranked-referrer query on one `reader.connect()` connection and returns `{"items": [...], "total_named_views": int}`. `items` is referrers aggregated across owned target videos, summed across the months overlapping `start_date`/`end_date` (a missing bound is unbounded on that side, via the shared `month_bounds()` below), ordered by views descending then referrer ID ascending. `video_ids`/`content_type`/`privacy_status`/`title` all filter the *target* side (`title` matching the target's title or ID, never a referrer's — see the Title filter note below), with the same three-state `video_ids` scoping convention as the other aggregate helpers (`None` = every owned video, populated = that set, empty = no rows). `own` filters the *referrer* side: `True` matches only a referrer confirmed as this channel's own video; `False` matches everything else, including a referrer with no resolved metadata at all (`COALESCE(ref.own, 0) = 0` — an unresolved referrer is "not confirmed ours," so it belongs in the non-owned bucket, never in neither bucket); `None` (the default) returns every referrer regardless of ownership. `limit=None` returns every referrer. Referrer metadata comes from a `LEFT JOIN videos ref`, so an unresolved referrer has `None` title, thumbnail, and `own`; each item carries it as `referrer_own` (`True`, `False`, or `null`). `total_named_views` is the scope's unfiltered `SUM(views)` across every real referrer regardless of the `own`/`limit` filters, so a caller never has to fetch an unranked/uncapped row set just to total it.
- `traffic.related_video_destinations(referrer_video_id, start_date=None, end_date=None, limit=None, video_ids=None)` — the top owned destination (target) videos for one given referrer, summed across the overlapping months, ordered by views descending then target ID ascending, as `{target_video_id, title, thumbnail_url, content_type, views}` items. The referrer's own ownership is irrelevant to this query — any video, owned or external, can be a referrer. `video_ids` scopes the destination set the same three-state way.
- There is no persisted residual, no `period_start`/`period_end` columns on `related_videos` itself, and no read-time "unattributed" figure computed against aggregate Traffic Sources — the backend returns only real, stored `related_videos` rows, the same discipline `search_terms` follows (see [Search terms](#aggregation-and-filtering-semantics) below). `sync_coverage` (below) tracks *completion*, separately from this table, and is never read by any reporting/aggregation query.

A shared `month_bounds(alias, start_date, end_date)` (`database/reports/_conditions.py`) builds independent `<alias>.month >= ?` / `<alias>.month <= ?` conditions from each date's `YYYY-MM` prefix, with a malformed bound becoming the always-false `0`; `reports/traffic.py` uses it with `st` for search terms and `rv` for Related Video referrers and destinations.

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

The writer never sets timestamps. Sync supplies `updated_at = now()` on every row it writes, and `completed_at = now()` on coverage rows; one timestamp is shared by all rows of one monthly insight batch and of one coverage call. `updated_at` therefore reflects "last successfully pulled and written," not "last changed." It updates even when a re-fetched row's values are identical to what's already stored. `sync/orchestration.py` supplies `started_at`/`completed_at = now()` on the `SyncRun` rows it writes; the startup sweep sets no timestamp.

`updated_at` is not present on `sync_runs` (has its own `started_at`/`completed_at`).

## Query conventions

- **Every** query uses parameterized `?` placeholders — never string-interpolated values. `f"..."` is used only to interpolate registry table and column names (reader, writer, and `filters.py`), compiler-generated subquery aliases, report SQL fragments, or `ORDER BY` fragments looked up from a fixed mapping, never raw user input.
- Sort keys are looked up in explicit mappings in `database/reports/catalog.py` before being interpolated into `ORDER BY`:
  - `_VIDEO_SORT_COLUMNS` maps `published_at`, `view_count`, `comment_count`, `total_revenue_sgd` to `v.published_at`, `v.view_count`, `v.comment_count`, and the lifetime-revenue `SUM` expression; `video_listing()` uses it for both the channel and playlist video lists.
  - `_PLAYLIST_SORT_COLUMNS` maps `published_at`/`item_count` to the aliased `playlists__published_at`/`playlists__item_count` result columns and `last_item_added`, `total_views`, `total_earnings_sgd` to themselves, since `playlist_listing()` sorts the outer `SELECT * FROM (…)`.
  - An invalid `sort_by` silently falls back to the default column rather than erroring.
- `_SORT_CLAUSES` (`database/reports/comments.py`) maps each public comment sort value to a full `ORDER BY` fragment rather than a bare column, each ending in `c.id` so equal timestamps or like counts cannot shuffle rows between pages: `"newest"` → `c.published_at DESC, c.id DESC`; `"oldest"` → `c.published_at ASC, c.id ASC`; `"likes"` → `c.like_count DESC, c.published_at DESC, c.id DESC`. An unrecognized value falls back to `"newest"`; the HTTP layer rejects it first (see `api.md`).
- `analytics.top_videos()` looks `sort_by` up in `_TOP_VIDEO_ORDER_BY` (`database/reports/analytics.py`), a mapping from public sort value to a full `ORDER BY` clause (aggregate plus deterministic tie-breakers), not a bare column name:
  - `"views"` → `period_views DESC, v.id ASC`
  - `"watch_time"` → `period_watch_time_hours DESC, period_views DESC, v.id ASC`
  - An unrecognized `sort_by` falls back to `"views"`, which is also the default.
- **Optional video scoping**: `video_ids: Collection[str] | None` scopes `get_video_stats()`, `catalog.video_listing()`, and every `analytics.py` and `traffic.py` report. There are no playlist-specific variants; a single video is the one-element scope `video_ids=[video_id]`. The parameter has three distinct states, and the distinction between the last two is load-bearing:
  - `None` (the default, and what channel-wide routes pass): no video predicate at all, so the query stays channel-wide.
  - A populated collection: appends `v.id IN (?, ?, …)` with one bound `?` per ID. Only the placeholder count is interpolated; every ID is a bound parameter.
  - An explicitly empty collection: `get_video_stats()` returns `_empty_video_stats()` *before opening a connection*. The other reports append the always-false condition `0` instead (via `_conditions.video_conditions()`), so their query returns no rows; the daily series are then `[]`, the traffic-source ranking `{}`, and the referrer total `0`. A truthiness check such as `if video_ids:` would collapse this state into `None` and leak channel-wide data to an empty playlist, so every caller tests `video_ids is not None` separately from emptiness.

  The argument is materialized once before placeholders are built (`video_conditions()` also de-duplicates it with `dict.fromkeys`), so sets and other non-sequence collections behave consistently. The scope predicate composes with every other filter via `AND`; the `LIMIT` parameter stays last.

  `get_video_stats()` (`database/reports/video_statistics.py`) accepts the same trailing `video_ids` with the same three states; its empty shape is `_empty_video_stats()`. It de-duplicates the collection (`list(dict.fromkeys(video_ids))`) to return the empty shape early, then calls `_conditions.video_conditions()` twice: once with `video_ids` alone for the scope predicate (`v.own = 1` plus the `v.id IN (…)` list), and once with the title/content-type/privacy filters added. The two condition sets stay separate because the analytics date-range query uses the scope alone — see *Video stats* below.
- All multi-table queries qualify columns with table aliases (`v.`, `va.`, `vts.`, `pi.`, `fx.`, `p.`) since `video_analytics` and `fx_rates` both have a `date` column, and other tables share `content_type`/`privacy_status`-adjacent names. Joined result columns are aliased `<table>__<field>`, so identical column names from different tables (`id`, `updated_at`) never collide.
- The known-IDs read in `_resolve_related_video_metadata()` has **no `ORDER BY`**; it is only used as a set.
- `get_video_stats()` (`database/reports/video_statistics.py`) serves both channel and playlist statistics and runs several sequential queries on one connection opened with `reader.connect()` rather than one combined statement — the multi-query split is deliberate (see below). It has its own module since it's keyed off the video catalog (Legacy/New classification, lifetime comments/privacy counts) with analytics as a secondary join.
- `sync_history.sync_batches()` (`database/reports/sync_history.py`), served by `GET /sync/runs`, returns one page of **sync batches** plus the distinct-batch total. A batch is one `batch_id`, the ID `execute_plan()` generates once per submitted plan and shares across every stage that starts, so paging counts submitted syncs rather than stage rows. Three reads run on one `reader.connect()` connection:
  - Count: `SELECT COUNT(DISTINCT batch_id)` — `total` is distinct batches, **not** stage rows, so `page_size` is a batch count.
  - Page: `SELECT batch_id, MIN(started_at) AS started_at … GROUP BY batch_id ORDER BY started_at DESC, batch_id DESC LIMIT ? OFFSET ?`. A batch is placed by its *earliest* stage, so a long-running batch cannot jump ahead of one submitted later; `batch_id DESC` breaks ties.
  - The page's stages: `reader.select(SyncRun, where=[("batch_id", "IN", batch_ids)], order_by=("-started_at", "-id"))`. An empty page skips this read.

  Paging over batch IDs before fetching stages keeps a batch from being split across two pages. The report groups the stages with `reader.group_by(runs, "batch_id")` and builds each item in batch-page order as `{batch_id, started_at, run_count, rows_fetched, rows_written, rows_deleted, runs, status}`, summing the counters from exactly the stages in that response. `status` is the worst stage status, **failed > incomplete > running > cancelled > success**, `success` for no stages, and an actual stored status rather than `success` if only unrecognized values are present. Offset paging can shift when a new batch starts between page requests. `sync_runs.batch_id` has no dedicated index.
- `sync_runs.status` is plain `TEXT NOT NULL` with no CHECK constraint; the values written are `running`, `success`, `failed`, `cancelled`, and `incomplete`. Each stage's row is inserted and finalized through the writer by `sync/orchestration.py` (see `sync.md`). A cancelled row keeps its partial counters and a `NULL` `error_message`.
- The startup sweep in `server.py`'s `lifespan` is `writer.update(SyncRun(status="incomplete"), where=(("status", "=", "running"),))`, one `UPDATE` whose count is logged as a lifecycle WARNING when nonzero. A row only leaves `running` when its stage completes, fails, or is cancelled, so a killed process strands one forever — and `completed_at = null` cannot tell a stranded stage from a live one. The sweep is sound because it runs right after `init_db()`, when the in-memory reservation guarding a real sync (`sync/status.py`) has died with the previous process, so no stage can legitimately still be running. **Running it at any other time would mislabel active work.** `completed_at` is left null — the stage never completed — so `incomplete` rows still render an em dash in that column. Nothing else in the backend reads `sync_runs.status = 'running'` (`sync/status.py`'s `running` is the unrelated in-memory lifecycle state).
- `sync/scheduler.py::synced_today()` reads `reader.scalar(SyncRun, "MAX", "completed_at", where=[("status", "=", "success")])` — `MAX(completed_at)` across `sync_runs` rows with `status = 'success'`, or `None` when nothing has ever succeeded. It does not group by `batch_id`: a single succeeded run qualifies regardless of its `sync_type`, scope, or which other stages ran alongside it. Because the `MAX` is taken over successful rows only, a later failed or still-running row cannot hide an earlier success. `synced_today()` is itself used only by the uncalled `start_background_scheduler()` — see `sync.md`.

## Aggregation and filtering semantics

- **Lifetime vs. period totals**: the `total_revenue_sgd` / `total_watch_time_hours` values from `catalog.video_listing()` and `catalog.video_detail()` are lifetime sums with no date filter applied, computed via `LEFT JOIN video_analytics` + `LEFT JOIN fx_rates`. Endpoints under `/analytics/*` (e.g. `analytics.top_videos()`, `analytics.daily_analytics()`) compute period-scoped sums bounded by `start_date`/`end_date` instead — same join pattern, but with date conditions applied.
- **Currency conversion**: `estimated_revenue_sgd` / `total_revenue_sgd` / `total_earnings_sgd` are always computed as `estimated_revenue * usd_to_sgd`, joined via `fx_rates.date = video_analytics.date` (or `DATE(va.date)` in the playlist-earnings subquery in `reports/catalog.py` — same semantic result, slightly different SQL form). A missing FX row for a given date means that date's revenue contributes `NULL`, `COALESCE`d to `0`.
- **Date filters**: filters against `published_at` (`videos`, `playlists`) use `>= start_date` and `<= end_date + "T23:59:59"` since `published_at` is a full timestamp; filters against `date` columns (`video_analytics.date`, `video_traffic_sources.date`) use plain `>= start_date` / `<= end_date` since those are date-only strings. Mixing these up would silently exclude the final day of a range.
- **Title filter**: every video-title `title`/`video_title` parameter across the backend — the reports through their shared `video_conditions()` (`video_listing`, `top_videos`, `search_terms`, `videos_by_search_term`, `daily_analytics`, `daily_traffic_sources`, `top_videos_by_traffic_source`, the target side of `related_video_referrers`, and `video_title` in `comment_feed`) and `get_video_stats()` — matches the corresponding video's **title or ID**: when non-empty, it appends the grouped condition `(v.title LIKE ? OR v.id LIKE ?)`, binding `f"%{title}%"` twice, combined with any other supplied condition via `AND`. `related_video_referrers()`'s `title` matches only the *target* video, never a referrer. The playlist `title` filter in `catalog.playlist_listing()` matches `(p.title LIKE ? OR p.id LIKE ?)` the same way, against the playlist's own ID. When a `video_ids` scope is also supplied, the filter is additive to it, not a replacement — a match outside the scoped set still yields no row. An omitted or empty value leaves the query unchanged from before this filter existed.
- **Grouping — analytics rows**: `analytics.daily_analytics()` groups by `(date, content_type)` — a video-day and a short-day on the same date are two separate rows, never summed together. Views, watch time, revenue, likes, and subscriber counts are `SUM`s; average view duration and percentage are `AVG`s. A single video's series is the same query with `video_ids=[video_id]`, where each group holds that video's one row, so its values equal the stored ones (including `NULL` metrics). Rows carry `date`, `content_type`, the metrics, and `estimated_revenue_sgd`; there is no `video_id` or `updated_at`.
- **Daily filling**: the two daily reports fill missing days with the reader's `DateFill` (see [Date filling](#date-filling)) over the whole filtered scope, starting at `start_date` (or the first observed date) and ending at the last observed date, so a chart doesn't extend zero-filled past real data:

  | Report | Breakdown | Synthetic rows |
  |---|---|---|
  | `analytics.daily_analytics()` | `fill_content_types` (default `("video", "short")`), narrowed to `[content_type]` when that filter is set; a requested type with no rows is still filled. `fill_content_types=None` fills only the observed types, which the single-video route uses | every metric and `estimated_revenue_sgd` are `0` |
  | `traffic.daily_traffic_sources()` | traffic-source types observed in the filtered result, sorted | `views` and `watch_time_minutes` are `0` |

  The content types to fill are an explicit argument rather than inferred from the scope size, so a one-member playlist still fills both types.
- **Top-N per traffic source type**: `traffic.top_videos_by_traffic_source()` orders rows `(traffic_source_type, views DESC)` in SQL, then `reader.group_by(rows, (VideoTrafficSource, "traffic_source_type"), limit=10)` keeps the first ten per source in Python. This only works because the SQL `ORDER BY` delivers each group pre-sorted by views descending. Every ranked row is still fetched; the limit is applied after the read. The channel-wide and playlist-scoped endpoints share the same limit.
- **Playlist membership resolution**: `catalog.playlist_video_ids(playlist_id)`, called by `routes/video_scope.py::scope_video_ids()` and `GET /videos/published`, is the single source of a playlist's scope for statistics, the playlist video list, analytics, and `/videos/published?playlist_id=`. It selects `DISTINCT v.id` over `playlist_items pi JOIN videos v ON v.id = pi.video_id WHERE pi.playlist_id = ?`, which does three things at once: duplicate `playlist_items` rows for the same video collapse to one ID (only `playlist_items.id` is unique, so duplicate `(playlist_id, video_id)` pairs are possible and would otherwise multiply aggregates); a `NULL` `video_id` is dropped; and a dangling `video_id` with no `videos` row is dropped, since `playlist_items.video_id` has no FK (see above). A playlist with no valid members — and an unknown playlist ID — both yield `[]`, which is why both callers establish existence first via `require_playlist(playlist_id)`, a `reader.select_one(Playlist, ("id",), where=[("id", "=", playlist_id)])` that computes no aggregates. The scoped query helpers, including `get_video_stats()`, never touch `playlist_items` themselves; they only see the resolved ID collection.
- **Top videos — period metrics**: `analytics.top_videos()` returns `id`, `title`, `published_at`, `thumbnail_url`, `content_type` plus `period_views`, `period_earnings_sgd`, and `period_watch_time_hours` (`SUM(va.watch_time_minutes) / 60.0`) computed from the same filtered `video_analytics` rows, scoped by the optional `start_date`/`end_date`/`content_type`/`privacy_status`/`video_ids` filters (applied to `va.date` and `v.*`, not `v.published_at`). `LIMIT` is applied after the `ORDER BY`, so ranking always happens over the full filtered set before truncating to the top N.
- **Video stats — Legacy/New classification**: `get_video_stats()` (`database/reports/video_statistics.py`, plus the `_empty_video_stats()` default template that is also its empty-scope result) classifies each video as Legacy (`published_at` strictly before the effective start date) or New (`published_at` between the effective start and end dates, inclusive), or neither if published after the effective end date. It runs four queries on one connection opened with `reader.connect()`, each through `reader.fetch_joined()` with named `values`: (1) the available `video_analytics` date range and (2) the catalog's `published_at` range, together used to derive the effective start/end when `start_date`/`end_date` are omitted; (3) a catalog query that counts Legacy/New videos per content type and computes lifetime comment/privacy-status totals directly from `videos` (no analytics join, so no multiplication risk); (4) a period-performance query that pre-aggregates `video_analytics` per `video_id` in a subquery (summing views and `estimated_revenue * fx_rates.usd_to_sgd`) before joining to `videos`, then groups by Legacy/New bucket and content type — the subquery pre-aggregation is what keeps the `fx_rates` join (1 row per `date`, per the `fx_rates` schema) from inflating sums. Each omitted bound falls back independently, in order, to the `video_analytics` date range, then the catalog's `published_at` range (truncated to a date) if no analytics rows exist at all — in that fallback case period views/earnings are zero but Legacy/New classification and counts still work. The `video_analytics` range covers every owned video in the base scope (the whole channel, or the `video_ids` set) and ignores the title/content-type/privacy filters, so filtering never moves a default date taken from analytics; the `published_at` fallback range, the catalog query, and the period query all apply those filters, so when the scope has no analytics rows the filters can change the fallback dates. A video with a `NULL` `published_at` is never classified Legacy or New but still contributes to comment/status totals. Lifetime comments and current privacy status are never restricted by date.

- **Comment reads**: the three comment routes share `comments.comment_feed()`, which joins `comments c` to `comment_authors ca` and `videos v` (restricted to `v.own = 1`) and selects every `Comment` column plus `CommentAuthor(youtube_channel_id, display_name, profile_image_url, channel_url)` and `Video(title, content_type, thumbnail_url)`. It flattens these with `to_dict(..., prefix="author_")`/`prefix="video_"` into `author_youtube_channel_id`, `author_display_name`, `author_profile_image_url`, `author_channel_url`, `video_title`, `video_content_type`, and `video_thumbnail_url` alongside every comment column. Filters are `c.text` and `ca.display_name` via `LIKE ?` bound to `f"%{value}%"`, `video_title` matching the parent video's title or ID (see the Title filter note above), `v.content_type`, and a `c.published_at` range using the full-timestamp convention above (`>= start_date`, `<= end_date + "T23:59:59"`). The video scope adds `c.video_id = ?`; the playlist scope adds `EXISTS (SELECT 1 FROM playlist_items pi WHERE pi.playlist_id = ? AND pi.video_id = c.video_id)`, so a video listed twice in a playlist still yields each of its comments once — the `EXISTS` is the comment-side equivalent of the `SELECT DISTINCT` dedup `playlist_video_ids()` performs for the scoped reports. Both scopes count and page over the same filtered set. The video-scoped route passes no `video_title` or `content_type` filter, since a fixed video determines both.

- **Search terms**: `sync/write_preparation.py::search_term_rows(video_id, month, terms, *, updated_at)` turns one month's `{"search_term": str, "views": int}` response rows into `SearchTerm` rows, and `sync_search_insights()` writes them with one `writer.write_many()` call. Duplicate exact term keys are summed, non-positive totals are dropped, and a malformed row (empty/non-string term, non-int views) or a `month` not matching `^\d{4}-(0[1-9]|1[0-2])$` raises `ValueError` before anything is written. A term omitted or zeroed by a later call is left untouched, never deleted — the only deletion path is the `videos` cascade. The write returns the number of rows processed, including unchanged refreshed rows.

  Two `traffic.py` reports share `month_bounds("st", start_date, end_date)` (`database/reports/_conditions.py`), which builds independent `st.month >= ?` / `st.month <= ?` conditions from each date's `YYYY-MM` prefix — a missing bound is unbounded on that side (same convention as the daily analytics and traffic-source date filters), and `start_date > end_date` yields no rows since no month satisfies both:
  - `search_terms(start_date=None, end_date=None, content_type=None, privacy_status=None, title=None, video_ids=None, limit=None)` — terms summed across owned videos as `{search_term, views}` items, with the same `video_ids` three-state scoping convention as above. One video's own terms are the same query with `video_ids=[video_id]`. `limit=None` (the default) returns every term; a caller wanting a capped "top N" list passes `limit` explicitly — there is no separate top-terms report, since the only difference is a `LIMIT` clause.
  - `videos_by_search_term(search_term, start_date=None, end_date=None, content_type=None, privacy_status=None, title=None, limit=10, video_ids=None)` — the top videos for **one specific term**, not a grouped-by-every-term query: `id`, `title`, `thumbnail_url`, `content_type` plus the summed `views`. It adds `st.search_term = ?` to the same conditions.

  Both order by views descending (ties by ascending term text or video id), and none compute a read-time "unattributed" residual against `video_traffic_sources` — that concept was considered during planning and explicitly rejected; the backend returns only real, stored `search_terms` rows.

## Compatibility constraints

- Adding a new sortable column requires adding it to both the relevant sort mapping (`database/reports/catalog.py`'s `_VIDEO_SORT_COLUMNS` or `_PLAYLIST_SORT_COLUMNS`) *and* the frontend's `SortKey` type (see `frontend.md`) — the backend will silently ignore an unrecognized `sort_by` rather than reject it.
- Because every sync write supplies a fresh `updated_at`, this column cannot be used to detect "did the underlying value actually change since last sync" — only "was this row touched by the most recent sync."
- Imports inside `database/` flow one way: `reader.py` imports `connection.py` and `dataclasses/`; `writer.py` imports `reader.py`; the `reports/` modules import `reader.py`, `dataclasses/`, and `reports/_conditions.py`. Nothing imports back through the package facade (`database/__init__.py`), and no report imports `routes` or `sync`. Playlist membership is resolved by the route layer (`scope_video_ids()`, and `GET /videos/published` directly) and passed in as `video_ids`, which keeps the scoped reports usable with any caller-supplied set of videos.
- `get_video_stats()` takes `video_ids` **after** every other parameter, and the other reports take it keyword-only; callers pass it by keyword. It binds one `?` per ID, so a scope is bounded by SQLite's parameter limit — practical for playlist-sized collections, not for arbitrarily large ID sets.
- `backend/scripts/issue-48-migration.py` is a standalone, one-time script for adding `videos.own` to a pre-existing database (idempotent — checks `PRAGMA table_info(videos)` before altering). It is intentionally not wired into `init_db()`: a one-time fixup doesn't belong in code that runs on every app start.
- The writer's `MAX(own, ?)` rule for `Video.own` means `own` can only ever move from `0` to `1` over a row's lifetime, never back — there is no code path that demotes a confirmed-owned video to external.
- Since the writer leaves `None` fields out, a value that later comes back empty from the API (say, a description removed on YouTube) keeps its previously stored value rather than being cleared.
- `backend/scripts/issue-62-migration.py` (see [Sync coverage](#sync-coverage)) is likewise standalone and not wired into `init_db()`, but unlike `issue-48-migration.py` it doesn't alter the schema — `sync_coverage` already exists on any database via `CREATE TABLE IF NOT EXISTS`, so this script only inserts baseline completion rows. It raises `ValueError` and writes nothing if any owned video lacks a `published_at`, rather than guessing a start date for it.
