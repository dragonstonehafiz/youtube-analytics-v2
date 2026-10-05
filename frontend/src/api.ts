import type {
  CommentsResponse,
  CommentSort,
  VideoStats,
  TopVideoSortBy,
  SyncStatusResponse,
  SyncStopResponse,
  SyncPlan,
  SyncQueuedResponse,
  SyncRunsResponse,
  DatabaseStatsResponse,
  SearchTermRow,
  SearchTermVideo,
  RelatedReferrersResponse,
  RelatedDestinationRow,
} from '@/types'

const BASE = "http://localhost:8000"

/** Date window accepted by every analytics endpoint. */
export interface DateFilters {
  startDate?: string
  endDate?: string
}

/** Catalog filters accepted by the channel/playlist listing, stats, and analytics endpoints. */
export interface CatalogFilters extends DateFilters {
  title?: string
  contentType?: string
  privacyStatus?: string
}

export interface PageOptions {
  page: number
  pageSize: number
}

export interface VideoListQuery extends CatalogFilters, PageOptions {
  sortBy: string
  sortDir: string
}

export interface PlaylistListQuery extends DateFilters, PageOptions {
  sortBy: string
  sortDir: string
  title?: string
}

export interface TopVideosQuery extends CatalogFilters {
  sortBy: TopVideoSortBy
}

export interface PublishedVideosQuery extends CatalogFilters {
  playlistId?: string
}

export interface SearchTermVideosQuery extends CatalogFilters {
  searchTerm: string
  limit?: number
}

export interface RelatedReferrersQuery extends CatalogFilters {
  own: boolean
  limit?: number
}

export interface VideoRelatedReferrersQuery extends DateFilters {
  own: boolean
  limit?: number
}

export interface RelatedDestinationsQuery extends DateFilters {
  referrerVideoId: string
  limit?: number
}

/** Filters accepted by all three comment endpoints. Scope comes from the path, not here. */
export interface CommentQuery extends DateFilters, Partial<PageOptions> {
  sortBy?: CommentSort
  text?: string
  videoTitle?: string
  author?: string
  contentType?: string
}

const QUERY_NAMES = {
  startDate: "start_date",
  endDate: "end_date",
  title: "title",
  contentType: "content_type",
  privacyStatus: "privacy_status",
  playlistId: "playlist_id",
  page: "page",
  pageSize: "page_size",
  sortBy: "sort_by",
  sortDir: "sort_dir",
  searchTerm: "search_term",
  own: "own",
  limit: "limit",
  referrerVideoId: "referrer_video_id",
  text: "text",
  videoTitle: "video_title",
  author: "author",
} as const

type Query = { [K in keyof typeof QUERY_NAMES]?: string | number | boolean }

/** Absent and empty-string values are omitted; `false` and `0` are sent. */
function buildUrl(path: string, query: Query = {}): string {
  const url = new URL(`${BASE}${path}`)
  for (const [key, value] of Object.entries(query) as [keyof Query, Query[keyof Query]][]) {
    if (value === undefined || value === "") continue
    url.searchParams.set(QUERY_NAMES[key], String(value))
  }
  return url.toString()
}

export const getVideoStats = (filters: CatalogFilters = {}): Promise<VideoStats> =>
  fetch(buildUrl("/videos/stats", filters)).then(r => r.json())

export const getPlaylistVideoStats = (id: string, filters: CatalogFilters = {}): Promise<VideoStats> =>
  fetch(buildUrl(`/playlists/${id}/videos/stats`, filters)).then(r => r.json())

export const getVideos = (query: VideoListQuery) =>
  fetch(buildUrl("/videos", query)).then(r => r.json())

export const getVideo = (id: string) =>
  fetch(buildUrl(`/videos/${id}`)).then(r => r.json())

export const getVideoAnalytics = (id: string, filters: DateFilters = {}) =>
  fetch(buildUrl(`/videos/${id}/analytics`, filters)).then(r => r.json())

export const getVideoTrafficSources = (id: string, filters: DateFilters = {}) =>
  fetch(buildUrl(`/videos/${id}/traffic-sources`, filters)).then(r => r.json())

export const getPlaylists = (query: PlaylistListQuery) =>
  fetch(buildUrl("/playlists", query)).then(r => r.json())

export const getPlaylist = (id: string) =>
  fetch(buildUrl(`/playlists/${id}`)).then(r => r.json())

export const getPlaylistVideos = (id: string, query: VideoListQuery) =>
  fetch(buildUrl(`/playlists/${id}/videos`, query)).then(r => r.json())

export const getChannelAnalytics = (filters: CatalogFilters = {}) =>
  fetch(buildUrl("/analytics/videos", filters)).then(r => r.json())

export const getTopVideosByViews = (query: TopVideosQuery) =>
  fetch(buildUrl("/analytics/videos/top", query)).then(r => r.json())

export const getPlaylistTopVideosByViews = (id: string, query: TopVideosQuery) =>
  fetch(buildUrl(`/analytics/playlists/${id}/top`, query)).then(r => r.json())

export const getPlaylistAnalytics = (id: string, filters: CatalogFilters = {}) =>
  fetch(buildUrl(`/analytics/playlists/${id}`, filters)).then(r => r.json())

export const getChannelTrafficSources = (filters: CatalogFilters = {}) =>
  fetch(buildUrl("/analytics/traffic-sources", filters)).then(r => r.json())

export const getPlaylistTrafficSources = (id: string, filters: CatalogFilters = {}) =>
  fetch(buildUrl(`/analytics/playlists/${id}/traffic-sources`, filters)).then(r => r.json())

export const getTopVideosByTrafficSource = (filters: CatalogFilters = {}) =>
  fetch(buildUrl("/analytics/traffic-sources/top", filters)).then(r => r.json())

export const getPlaylistTopVideosByTrafficSource = (id: string, filters: CatalogFilters = {}) =>
  fetch(buildUrl(`/analytics/playlists/${id}/traffic-sources/top`, filters)).then(r => r.json())

async function fetchJson<T>(path: string, query: Query): Promise<T> {
  const response = await fetch(buildUrl(path, query))
  if (!response.ok) throw new Error(`Search insights request failed (${response.status})`)
  return response.json() as Promise<T>
}

export const getSearchTerms = (filters: CatalogFilters = {}): Promise<{ items: SearchTermRow[] }> =>
  fetchJson("/analytics/search-insights", filters)

export const getVideosBySearchTerm = (query: SearchTermVideosQuery): Promise<{ items: SearchTermVideo[] }> =>
  fetchJson("/analytics/search-insights/videos", query)

export const getPlaylistSearchTerms = (id: string, filters: CatalogFilters = {}): Promise<{ items: SearchTermRow[] }> =>
  fetchJson(`/analytics/playlists/${id}/search-insights`, filters)

export const getPlaylistVideosBySearchTerm = (id: string, query: SearchTermVideosQuery): Promise<{ items: SearchTermVideo[] }> =>
  fetchJson(`/analytics/playlists/${id}/search-insights/videos`, query)

export const getVideoSearchTerms = (id: string, filters: DateFilters = {}): Promise<{ items: SearchTermRow[] }> =>
  fetchJson(`/analytics/videos/${id}/search-insights`, filters)

export const getRelatedVideoReferrers = (query: RelatedReferrersQuery): Promise<RelatedReferrersResponse> =>
  fetchJson("/analytics/related-videos/referrers", query)

export const getRelatedVideoDestinations = (query: RelatedDestinationsQuery): Promise<{ items: RelatedDestinationRow[] }> =>
  fetchJson("/analytics/related-videos/destinations", query)

export const getPlaylistRelatedVideoReferrers = (id: string, query: RelatedReferrersQuery): Promise<RelatedReferrersResponse> =>
  fetchJson(`/analytics/playlists/${id}/related-videos/referrers`, query)

export const getPlaylistRelatedVideoDestinations = (id: string, query: RelatedDestinationsQuery): Promise<{ items: RelatedDestinationRow[] }> =>
  fetchJson(`/analytics/playlists/${id}/related-videos/destinations`, query)

export const getVideoRelatedVideoReferrers = (id: string, query: VideoRelatedReferrersQuery): Promise<RelatedReferrersResponse> =>
  fetchJson(`/analytics/videos/${id}/related-videos/referrers`, query)

export const getVideosPublished = (query: PublishedVideosQuery = {}) =>
  fetch(buildUrl("/videos/published", query)).then(r => r.json())

async function fetchComments(path: string, query: CommentQuery): Promise<CommentsResponse> {
  const response = await fetch(buildUrl(path, query))
  if (!response.ok) throw new Error(`Comments request failed (${response.status})`)
  return response.json() as Promise<CommentsResponse>
}

export const getComments = (query: CommentQuery = {}): Promise<CommentsResponse> =>
  fetchComments("/comments", query)

export const getVideoComments = (id: string, query: CommentQuery = {}): Promise<CommentsResponse> =>
  fetchComments(`/comments/videos/${id}`, query)

export const getPlaylistComments = (id: string, query: CommentQuery = {}): Promise<CommentsResponse> =>
  fetchComments(`/comments/playlists/${id}`, query)

export const getDateRange = () =>
  fetch(buildUrl("/meta/date-range")).then(r => r.json())

export const getSyncStatus = async (): Promise<SyncStatusResponse> => {
  const response = await fetch(buildUrl("/sync/status"))
  if (!response.ok) throw new Error(`Sync status request failed (${response.status})`)
  return response.json() as Promise<SyncStatusResponse>
}

async function syncErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    const detail = (body as { detail?: unknown }).detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined
      if (first?.msg) return first.msg
    }
  } catch {
    // Non-JSON error body; fall through to the status code.
  }
  return `Sync request failed (${response.status})`
}

export const triggerSync = async (plan: SyncPlan): Promise<SyncQueuedResponse> => {
  const response = await fetch(buildUrl("/sync/trigger"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  })
  if (!response.ok) throw new Error(await syncErrorMessage(response))
  return response.json() as Promise<SyncQueuedResponse>
}

/**
 * Request cancellation of the active sync, manual or startup-origin. Idempotent while
 * already stopping. Rejects with a safe message (derived only from the HTTP status or
 * `detail` text, never a raw exception body) on 409 when no sync is active.
 */
export const stopSync = async (): Promise<SyncStopResponse> => {
  const response = await fetch(buildUrl("/sync/stop"), { method: "POST" })
  if (!response.ok) throw new Error(await syncErrorMessage(response))
  return response.json() as Promise<SyncStopResponse>
}

/**
 * Fetch one page of sync history, grouped into batches — `page`/`pageSize` count batches,
 * not stage rows, and each item carries its own stages in `runs`. Failures reject with a
 * message derived only from the HTTP status, so a backend exception body can never reach
 * the history UI.
 */
export const getSyncRuns = async (page: number, pageSize: number): Promise<SyncRunsResponse> => {
  const response = await fetch(buildUrl("/sync/runs", { page, pageSize }))
  if (!response.ok) throw new Error(`Sync history request failed (${response.status})`)
  return response.json() as Promise<SyncRunsResponse>
}

export const getDatabaseStats = async (): Promise<DatabaseStatsResponse> => {
  const response = await fetch(buildUrl("/sync/database"))
  if (!response.ok) throw new Error(`Database statistics request failed (${response.status})`)
  return response.json() as Promise<DatabaseStatsResponse>
}
