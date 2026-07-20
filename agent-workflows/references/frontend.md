# Frontend Reference

## Purpose

Client-side behavior: shared types, API client, shared libraries, components, pages, URL/filter-state conventions, and styling. Route/HTTP contracts live in `api.md`; this file describes how the frontend consumes them.

## Authoritative source files

- `frontend/src/types/index.ts`
- `frontend/src/api.ts`
- `frontend/src/lib/trafficSources.ts`, `frontend/src/lib/topVideos.ts`
- `frontend/src/hooks/useReplaceSearchParams.ts`
- `frontend/src/pages/*.tsx` and colocated `.css`
- `frontend/src/components/*.tsx` and colocated `.css`
- `frontend/src/index.css`
- `frontend/vite.config.ts`, `frontend/tsconfig.app.json`

## Contents

- [Application structure and routing](#application-structure-and-routing)
- [Shared types](#shared-types)
- [API client](#api-client)
- [Shared libraries](#shared-libraries)
- [Shared components](#shared-components)
- [Pages](#pages)
- [URL and filter state](#url-and-filter-state)
- [Styling and responsive behavior](#styling-and-responsive-behavior)
- [Compatibility conventions](#compatibility-conventions)

## Application structure and routing

See `architecture.md` for the full route table and entry-point layout. `TopNav` renders outside `<Routes>` in `App.tsx`, so it persists across every page.

## Shared types (`src/types/index.ts`)

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
  legacy_video_count: number; legacy_video_views: number; legacy_video_earnings_sgd: number
  legacy_short_count: number; legacy_short_views: number; legacy_short_earnings_sgd: number
  new_video_count: number; new_video_views: number; new_video_earnings_sgd: number
  new_short_count: number; new_short_views: number; new_short_earnings_sgd: number
  total_comments: number; video_comments: number; short_comments: number
  total_public: number; total_private: number; total_unlisted: number
}
```

## API client (`src/api.ts`)

Thin `fetch` wrappers, one per backend route (see `api.md` for what each endpoint does). All go through `buildUrl(path, params?)`, which sets a query param only when its value is truthy — an empty string or `undefined` is simply omitted, not sent as `key=`.

Notable naming quirks (source of truth is the function body, not the name):

- `getPlaylistAnalytics(id, params)` and `getPlaylistAggregatedAnalytics(id, params)` are identical — both hit `GET /analytics/playlists/{id}`. Only `getPlaylistAnalytics` is actually called (from `PlaylistAnalytics.tsx`).
- Functions taking a generic `params?: Record<string, string>` bag (`getChannelAnalytics`, `getPlaylistAnalytics`, `getChannelTrafficSources`, `getPlaylistTrafficSources`, `getTopVideosByTrafficSource`, `getPlaylistTopVideosByTrafficSource`) differ stylistically from the rest of the file, which take named positional params — both patterns exist side by side; there is no in-progress migration between them documented anywhere.

## Shared libraries (`src/lib/`)

**`trafficSources.ts`**
- `formatTrafficSource(type)` — raw API enum → human label (e.g. `YT_SEARCH` → "YouTube Search"); falls back to a generic title-cased version of the raw string for unmapped types.
- `getTrafficSourceColor(type)` — fixed `Record<type, hex>` lookup of 16 explicit colors; every traffic source type keeps the same color everywhere it's rendered (table bars, chart lines, donut slices), regardless of its rank in any particular filtered view. Falls back to `TRAFFIC_SOURCE_OTHER_COLOR` (grey, `#898781`) for unmapped types.
- `aggregateTrafficSourceTotals(rows)` — sums `views`/`watch_time_minutes` per traffic source type across all rows, sorted by views descending.

**`topVideos.ts`**
- `toTopVideoShape(video: Video): TopVideo` — maps a lifetime `Video` record into the `TopVideo` shape used by ranked/carousel components (`period_views = view_count`, `period_watch_time_hours = total_watch_time_hours`, `period_earnings_sgd = total_revenue_sgd`).
- `last7Dates()` — `[start, end]` ISO dates for the rolling last-7-days window (inclusive of today).
- Used by `Analytics.tsx` and `PlaylistAnalytics.tsx`. `Home.tsx` does not import this module — it defines its own local, functionally-identical copies of both `toTopVideoShape` and a `last28Dates`-equivalent inline instead. If `topVideos.ts` or `PeriodSelect.tsx`'s date helpers change, `Home.tsx`'s inline copies won't pick up the change automatically.

## Shared components (`src/components/`)

| Component | Behavior |
|---|---|
| `TopNav.tsx` | Sticky nav. No "Home" link — the "YouTube Analytics" brand text is itself a `<button>` navigating to `/`. Back arrow shown only on detail pages (`/analytics/videos/:id`, `/analytics/playlists/:id`, matched via regex `^\/analytics\/(videos|playlists)\/`). Brand and nav-link clicks compare the target pathname against `location.pathname`: an exact match is a no-op (no navigation, no history change, current query state untouched); a different pathname calls plain `navigate(to)`, pushing a history entry. Active-link highlighting still uses prefix matching (`/analytics` stays highlighted on `/analytics/videos/:id`), independent of this exact-match check. `SyncStatus` renders in the right side of the nav on every page. |
| `SyncStatus.tsx` | Polls `/sync/status` every 5s. Syncing: animated blue dot + message. Idle: last-synced text, a scope `<select>` ("New data only" = incremental default / "Full resync" = all / each year back to `earliest_year`), and a "Sync now" button — all as plain inline items (no bordered pill). Select and button are both 28px tall / 12px font (`.sync-scope-select`/`.sync-trigger-btn`) so they align. `triggerSync(scope, year)` derives scope from the select value: `'incremental'`/`'all'` pass straight through, anything else is treated as a year string and sent as `scope=year`. |
| `PeriodSelect.tsx` | Shared quick-select: Custom (clears dates — no filter) / Last 365 days / Last 90 days / Last 28 days / then years from earliest `published_at` down to current year (via `/meta/date-range`). Exports `last365Dates()`, `last90Dates()`, `last28Dates()`. Component default is Custom; pages wanting a non-Custom default set their own initial URL param state. |
| `VideoTable.tsx` | Shared table + filter bar + pagination for Videos.tsx and PlaylistAnalytics.tsx's Videos tab. Exports `PAGE_SIZE = 25`, `SortKey` (`published_at`\|`view_count`\|`comment_count`\|`total_revenue_sgd`), `SortDir`. Filter bar order: Period → From → To \| Title \| Type \| Privacy. Parents own all URL param / fetch / stats-fetch state; this component is presentational plus local sort-arrow rendering. |
| `VideoStatsBar.tsx` | Standalone stats bar, one `VideoStats` prop shape, 6 columns: Legacy Videos (count / period views / period earnings) \| New Videos (same three) \| Legacy Shorts (same three) \| New Shorts (same three) \| Lifetime Comments (total / video / short) \| Current Status (public / private / unlisted) — Legacy/New pairs sit next to each other per content type. Used unchanged by `Videos.tsx`, `Analytics.tsx`, and `PlaylistAnalytics.tsx` — no page-specific variants. Legacy/New counts and period views/earnings are date-scoped (see `database.md`); Lifetime Comments and Current Status are never date-restricted. Parents own the fetch and placement; responsive via CSS grid (`VideoStatsBar.css`), wrapping from 6 columns down to 3 at ≤1024px and 2 at ≤640px. |
| `AnalyticsChart.tsx` | Recharts `AreaChart` (`type="linear"`, no curve smoothing) over `AnalyticsRow[]`. Renders one `Area` per `content_type` actually present in the input rows (`video` = `var(--blue)`, `short` = `#f59e0b`) — a single-video page's rows are all one `content_type` so exactly one line renders; a channel/playlist view with no `content_type` filter gets both (zero-filled independently per type by the backend). Legend renders only when more than one series is present. Fill is solid 10% opacity down to the axis, no gradient. Control rows, top to bottom: "Chart Type" (Per Bucket / Cumulative Total) → "Bucket Size" (Daily / Weekly / Monthly) → metric buttons (Views / Watch Time hours / Estimated Earnings SGD, each showing the Video+Shorts combined total for the period, computed from unaggregated rows regardless of bucket size or chart type). Weekly buckets start Monday UTC; monthly buckets key on the 1st. Cumulative mode runs independent running sums per `content_type` over already-bucketed rows. X-axis hidden; quarterly `ReferenceLine` labels when the data spans ≤8 quarters, else yearly (see `UploadStrip.tsx` below — this threshold lives there, not in this file). Optional `uploadedVideos` prop renders an `UploadStrip` below the chart. `ResizeObserver` on the card div is always mounted. Used by `Analytics.tsx` and `PlaylistAnalytics.tsx` (not `VideoAnalytics.tsx`, which has no `uploadedVideos` to pass). |
| `UploadStrip.tsx` | Shared infra used by both `AnalyticsChart` and `TrafficSourceChart`: `formatCompact()` (y-axis tick formatter: plain number <1,000, `"1.5K"`-style ≥1,000, `"1.1M"`-style ≥1,000,000), `getMarks()` (quarterly/yearly `ReferenceLine` labels — **yearly kicks in once the row set spans strictly more than 8 distinct quarters** (`quarters.size > 8`); quarterly still applies at exactly 8), `computeUploadBuckets()` (buckets `PublishedVideo[]` into pixel-width-derived groups along the chart's date range), and `<UploadStrip>` (renders the badge row + hover popover). `YAXIS_WIDTH`/`CHART_RIGHT`/`BUCKET_WIDTH` constants also live here. |
| `TrafficSourceChart.tsx` | Recharts `LineChart` (not `Area`) for `TrafficSourceRow[]`. Mirrors `AnalyticsChart`'s Chart Type / Bucket Size control rows (local `toCumulative()`/`bucketKey()`, since `AnalyticsChart`'s versions are hardcoded to its own fixed fields). Metric buttons: Views / Watch Time (hours) only — no earnings. Top 6 traffic source types by total views each become their own colored `Line` (via `getTrafficSourceColor()`); everything else is summed into one grey "Other" line (`TRAFFIC_SOURCE_OTHER_COLOR`). Custom legend row above the chart (not recharts' built-in `Legend`). Reuses `YAXIS_WIDTH`/`CHART_RIGHT`/`formatCompact`/`getMarks`/`computeUploadBuckets`/`UploadStrip` and the `.analytics-chart`/`.chart-metric-*` classes from `AnalyticsChart.css`. Optional `uploadedVideos` prop renders the same upload strip. |
| `TrafficSourcesTable.tsx` | Aggregates `TrafficSourceRow[]` via `aggregateTrafficSourceTotals()` into one row per source type, sorted by views desc. Columns: Source \| relative bar (width scaled to the max-views source, colored via `getTrafficSourceColor()`) \| Views \| Watch Time (hrs) \| % (share of total views). Renders `chart-placeholder` fallback when `rows` is empty. |
| `TrafficSourceTopVideosPanel.tsx` | Pill-button switcher (color dot + label, one pill per traffic source type present, ordered via `aggregateTrafficSourceTotals(rows)`) above a top-10-by-views table for the selected type. Takes `rows: TrafficSourceRow[]` (for ordering) and `bySource: Record<type, TrafficSourceTopVideo[]>` (fetched data). Internal `useState` selection, defaults to the highest-views type. Renders nothing when `rows` is empty. |
| `TopVideosList.tsx` | Shared top-10-by-views table. Columns: thumbnail (rank shown as a placeholder number if no thumbnail) \| title (links to `/analytics/videos/:id`) \| upload date \| views \| earnings (SGD). Renders nothing when `videos` is empty. Used by `Analytics.tsx` and `PlaylistAnalytics.tsx`. |
| `VideoCarouselCard.tsx` | Single-video-at-a-time card: thumbnail with bottom-gradient title overlay (links to `/analytics/videos/:id`), "Uploaded `<years/months/days>` ago" (`timeSincePublished()`, calendar-based diff), then Views / Watch Time (hours) / Earnings (SGD) stat rows, then Previous/Next arrows + "X/N" page indicator. Takes `title` and `videos: TopVideo[]` (deliberately reuses `TopVideo`'s shape rather than defining its own). Renders nothing when `videos` is empty. Self-contained carousel index via `useState`. Used by `Home.tsx`, `Analytics.tsx`, and `PlaylistAnalytics.tsx`. |
| `TopPerformersCard.tsx` | Ranked list card: rank number \| thumbnail \| title \| period views, one row per video, no pagination/carousel (just a static list). Takes `title` and `videos: TopVideo[]`; renders nothing when `videos` is empty. Used by `Analytics.tsx` and `PlaylistAnalytics.tsx` sidebars as "Top Videos (Last 7 Days)" / "Top Shorts (Last 7 Days)", fed by `getTopVideosByViews`/`getPlaylistTopVideosByViews` over `last7Dates()` from `lib/topVideos.ts`. |
| `TrafficSourceDonutCard.tsx` | Recharts donut (`Pie` with `innerRadius`/`outerRadius`, no gradient) of aggregated views per traffic source type; center label = total views. Top 6 types by views get their own colored slice; everything else rolled into one grey "Other" slice. Legend below the donut lists the top 6 **with each type's raw view count** (not a percentage, despite the CSS class being named `traffic-donut-legend-pct` — `TrafficSourceDonutCard.tsx` renders `t.views.toLocaleString()`, not a computed share), then — if any rows were rolled up — an "Other includes:" divider followed by each rolled-up type's own name + raw view count. Takes `title` and `rows: TrafficSourceRow[]` (no fetch of its own). Renders nothing when `rows` is empty or total views is 0. Used only by `Home.tsx`. |

## Pages

**`Home.tsx`** — 3-card nav grid (Videos/Playlists/Analytics) plus a 3-column `.home-carousels` grid: "Top Videos (Last 28 Days)" and "Top Shorts (Last 28 Days)" via `getTopVideosByViews(last28Dates(), 'video'|'short', 'public')`, "Latest Uploads" via `getVideos(1, 10, 'published_at', 'desc', ..., 'public')` (no content-type filter, so mixes videos/shorts) mapped into `TopVideo` shape via a **locally-defined** `toTopVideoShape()` (see the `lib/topVideos.ts` note above), and a `TrafficSourceDonutCard` ("Traffic Sources (Last 28 Days)") which wraps to its own row since the grid stays 3 columns. All four always public-only, independent of any page filter — Home has no filter bar.

**`Videos.tsx`** — Paginated, server-side sorted/filtered table via `VideoTable`. URL params: `page`, `sort_by`, `sort_dir`, `title`, `start_date`, `end_date`, `content_type`, `privacy_status`. Page size 25 (`VideoTable.PAGE_SIZE`). Only `initialLoading` shows a spinner — subsequent page/sort/filter changes swap rows in place. `VideoStatsBar` rendered above `VideoTable`, fetched separately with the same `start_date`/`end_date` values, but each endpoint applies them to a different column: `getVideos()` filters table rows by `videos.published_at`, while `getVideoStats()` uses the same two dates as the Legacy/New publication split *and* the `video_analytics.date` window for period views/earnings (see `database.md`).

**`Playlists.tsx`** — Same pagination/sort/URL-param pattern, implemented as its own inline table (does not reuse `VideoTable`, since that component is video-row-shaped). Filter bar has title search only — no date or type filter. Sortable columns: `last_item_added` (default desc), `published_at`, `item_count`, `total_views`, `total_earnings_sgd`. Column order: Thumbnail \| Title \| Last Added \| Created \| Views \| Earnings (SGD) \| Videos.

**`VideoAnalytics.tsx`** — Meta card (thumbnail, truncated single-line title, badge, stats row — views/likes/comments/published/length/earnings SGD — with dividers, then collapsible description). Filter bar: Period → Start → End only (no Type filter, no Apply); `start_date`/`end_date` are URL params defaulting to Last 28 days. Fetches `AnalyticsRow[]` (`/videos/{id}/analytics`) and `TrafficSourceRow[]` (`/videos/{id}/traffic-sources`) together on every filter change regardless of active tab. Two tabs (`analytics` / `traffic-sources`, URL param `tab`): Analytics renders `AnalyticsChart` (no `uploadedVideos` prop — this page has none to pass); Traffic Sources renders `TrafficSourceChart` + `TrafficSourcesTable`. Both tabs share one filter bar/param set, so switching tabs clears nothing.

**`Analytics.tsx`** — Channel-wide. Two tabs (`analytics` / `traffic-sources`, URL param `tab`, both sharing the same filter set). Filter bar: Period → Start → End \| Type \| Privacy; dates default to Last 28 days. Fetches `VideoStats`, `AnalyticsRow[]`, `TopVideo[]` (top-10), `PublishedVideo[]`, `TrafficSourceRow[]`, and the top-per-source map together on every filter change. Also fetches, **independent of the filter bar** (empty-deps effect): "Latest Videos"/"Latest Shorts" via `getVideos(1, 10, ..., 'video'|'short', 'public')` mapped through the shared `toTopVideoShape()` from `lib/topVideos.ts`, and "Top Videos (Last 7 Days)"/"Top Shorts (Last 7 Days)" via `getTopVideosByViews(last7Dates(), 'video'|'short', 'public')`. Analytics tab renders `VideoStatsBar`, then a two-column `.analytics-layout`: left `.analytics-main` (`AnalyticsChart` with `uploadedVideos`, then `TopVideosList`), right `.analytics-sidebar` — **four** cards in this order: `TopPerformersCard` "Top Videos (Last 7 Days)", `TopPerformersCard` "Top Shorts (Last 7 Days)", `VideoCarouselCard` "Latest Videos", `VideoCarouselCard` "Latest Shorts". Traffic Sources tab renders `TrafficSourceChart` (with `uploadedVideos`), `TrafficSourcesTable`, `TrafficSourceTopVideosPanel` instead of the two-column layout.

**`PlaylistAnalytics.tsx`** — Playlist meta card (thumbnail, title, stats: Views/Earnings/Videos/Last Added/Created) via `GET /playlists/{id}`. Three tabs in button order: `analytics`, `traffic-sources`, `videos`, driven by a `tab` URL param (defaulting to `analytics`) rather than component state — direct/bookmarked/refreshed tab URLs work. Videos tab renders `VideoTable` with its own URL params (`page`, `sort_by`, `sort_dir`, `title`, `start_date`, `end_date`, `content_type`, `privacy_status`). Analytics and Traffic Sources tabs share one filter bar/param set, prefixed `analytics_` (`analytics_start_date`, `analytics_end_date`, `analytics_content_type`, `analytics_privacy_status`) to avoid colliding with the Videos tab's own params; default Last 28 days. Fetches the same set as `Analytics.tsx` but playlist-scoped, plus the same independent (empty-deps) "Latest Videos"/"Latest Shorts" and "Top Videos/Shorts (Last 7 Days)" pattern via `getPlaylistVideos`/`getPlaylistTopVideosByViews`. Analytics tab layout mirrors `Analytics.tsx`'s two-column `.analytics-layout` with the same four-card sidebar (`TopPerformersCard` ×2, `VideoCarouselCard` ×2). Traffic Sources tab mirrors `Analytics.tsx`'s traffic-sources tab. `handleTabChange` sets `tab` and performs the cross-tab param cleanup in one search-param update: switching to Videos clears all `analytics_*` params; switching to Analytics or Traffic Sources clears all video-tab params; switching between Analytics and Traffic Sources clears nothing (shared params).

## URL and filter state

- Filter state lives in URL search params on every page, never component state — filters survive reloads/back-forward navigation and are shareable links.
- On `Videos.tsx` and `PlaylistAnalytics.tsx`'s Videos tab, the default for `start_date`/`end_date` is `''` — an absent param and an explicit empty string mean the same thing ("all data"), so there's no ambiguity to handle.
- On `Analytics.tsx`, `VideoAnalytics.tsx`, and `PlaylistAnalytics.tsx`'s Analytics/Traffic-Sources tabs, the default is **Last 28 days** instead — which makes an *absent* param mean something different from an *explicit empty string* (Custom/all data). Reading these must use `searchParams.has(key)` to distinguish the two states, and any handler writing an empty date must call `.set(key, '')` rather than `.delete(key)` — otherwise selecting "Custom" immediately snaps back to Last 28 days on the next render.
- Filter bar order is consistent everywhere it appears: Period → From/Start → To/End \| Title (where present) \| Type (where present) \| Privacy (where present), with `.filter-bar-sep` dividers between logical groups. No Apply button anywhere — every filter change triggers a live fetch.
- Every query-driven page uses `useReplaceSearchParams()` (`src/hooks/useReplaceSearchParams.ts`) instead of React Router's `useSearchParams()` directly. It wraps the same `[searchParams, setSearchParams]` pair but forces every update to `{ replace: true }`, so filter/sort/page/tab changes update the URL without growing browser history — the current pathname keeps a single history entry no matter how many query changes happen on it. Pathname navigation (`<Link>`, `TopNav`'s `navigate(to)`) is unrelated to this hook and continues to push history normally. Any new query-driven page must use this hook rather than calling `useSearchParams()` directly.

## Styling and responsive behavior

Global tokens and shared classes live in `src/index.css`:

- Colors: `--blue: #1a73e8`, `--blue-dark: #1557b0`, `--blue-light: #e8f0fe`, `--blue-mid: #d2e3fc`; `--surface: #ffffff`, `--surface-glass: rgba(255,255,255,0.75)`; `--border: #e2e8f0`, `--border-light`; `--text: #3c4149`, `--text-secondary: #6b7280`, `--text-heading: #111827`.
- Shape: `--radius: 12px`, `--radius-sm: 8px`, `--radius-lg: 16px`; `--shadow-sm/md/lg`.
- Font: Plus Jakarta Sans (Google Fonts import at the top of `index.css`).
- `.page` — 80% viewport width, `2rem` padding (mirrored by `.home` in `Home.css` and `.topnav-inner` in `TopNav.css` — keep all three in sync if this changes).
- `.card` — glass card (`backdrop-filter: blur(12px)`, `--surface-glass` background, `--border-light` border).
- `.data-table` — `table-layout: fixed`, sortable headers via `.sortable` + hover highlight.
- `.filter-bar` / `.filter-bar-sep` — inline filter row; 1px vertical divider between logical groups.
- `.tabs` / `.tab` / `.tab.active` — underline tab strip, blue underline when active.
- `.chart-placeholder` — dashed 280px-tall placeholder box.
- `.badge` / `.badge.short` — pill badge, blue for Video, amber (`#fef3c7` bg / `#92400e` text) for Short.
- `.btn-primary` / `.btn-ghost` — blue gradient / outlined-blue buttons.
- `.loading`, `.pagination` / `.pagination-info`, `.section-header` (small-caps label, symmetric `0.5rem` top/bottom margin).
- Every `h1` gets gradient text (dark → blue) globally.

## Compatibility conventions

- `@/` alias maps to `src/`, configured in both `vite.config.ts` (`resolve.alias`) and `tsconfig.app.json` — a path change must be kept in sync across both files or the build and the editor's type-checking will disagree.
- Adding a new sortable column anywhere requires updating the frontend's `SortKey` union *and* the backend's `_..._SORT_COLUMNS` allow-list (see `api.md`/`database.md`) — the two are not generated from a shared source.
- `Home.tsx`'s locally-duplicated `toTopVideoShape`/date-window logic (see `lib/topVideos.ts` above) means a fix or change to the shared versions in `lib/topVideos.ts` or `PeriodSelect.tsx` will not automatically propagate to `Home.tsx` — check it explicitly when touching either shared helper.
