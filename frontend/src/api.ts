import type {
  CommentsResponse,
  CommentSort,
  VideoStats,
  TopVideoSortBy,
  SyncStatusResponse,
  SyncPlan,
  SyncQueuedResponse,
  SyncRunsResponse,
} from '@/types'

const BASE = "http://localhost:8000"

function buildUrl(path: string, params?: Record<string, string>): string {
  const url = new URL(`${BASE}${path}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v) url.searchParams.set(k, v)
    })
  }
  return url.toString()
}

export const getVideoStats = (title?: string, startDate?: string, endDate?: string, contentType?: string, privacyStatus?: string): Promise<VideoStats> =>
  fetch(buildUrl("/videos/stats", { ...(title && { title }), ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }), ...(contentType && { content_type: contentType }), ...(privacyStatus && { privacy_status: privacyStatus }) })).then(r => r.json())

export const getPlaylistVideoStats = (id: string, title?: string, startDate?: string, endDate?: string, contentType?: string, privacyStatus?: string): Promise<VideoStats> =>
  fetch(buildUrl(`/playlists/${id}/videos/stats`, { ...(title && { title }), ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }), ...(contentType && { content_type: contentType }), ...(privacyStatus && { privacy_status: privacyStatus }) })).then(r => r.json())

export const getVideos = (page: number = 1, pageSize: number = 25, sortBy: string = 'published_at', sortDir: string = 'desc', title?: string, startDate?: string, endDate?: string, contentType?: string, privacyStatus?: string) =>
  fetch(buildUrl("/videos", { page: String(page), page_size: String(pageSize), sort_by: sortBy, sort_dir: sortDir, ...(title && { title }), ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }), ...(contentType && { content_type: contentType }), ...(privacyStatus && { privacy_status: privacyStatus }) })).then(r => r.json())

export const getVideo = (id: string) =>
  fetch(buildUrl(`/videos/${id}`)).then(r => r.json())

export const getVideoAnalytics = (id: string, startDate?: string, endDate?: string) =>
  fetch(buildUrl(`/videos/${id}/analytics`, { ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }) })).then(r => r.json())

export const getVideoTrafficSources = (id: string, startDate?: string, endDate?: string) =>
  fetch(buildUrl(`/videos/${id}/traffic-sources`, { ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }) })).then(r => r.json())

export const getPlaylists = (page: number = 1, pageSize: number = 25, sortBy: string = 'last_item_added', sortDir: string = 'desc', title?: string, startDate?: string, endDate?: string) =>
  fetch(buildUrl("/playlists", { page: String(page), page_size: String(pageSize), sort_by: sortBy, sort_dir: sortDir, ...(title && { title }), ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }) })).then(r => r.json())

export const getPlaylist = (id: string) =>
  fetch(buildUrl(`/playlists/${id}`)).then(r => r.json())

export const getPlaylistVideos = (id: string, page: number = 1, pageSize: number = 25, sortBy: string = 'published_at', sortDir: string = 'desc', title?: string, startDate?: string, endDate?: string, contentType?: string, privacyStatus?: string) =>
  fetch(buildUrl(`/playlists/${id}/videos`, { page: String(page), page_size: String(pageSize), sort_by: sortBy, sort_dir: sortDir, ...(title && { title }), ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }), ...(contentType && { content_type: contentType }), ...(privacyStatus && { privacy_status: privacyStatus }) })).then(r => r.json())

export const getChannelAnalytics = (params?: Record<string, string>) =>
  fetch(buildUrl("/analytics/videos", params)).then(r => r.json())

export const getTopVideosByViews = (sortBy: TopVideoSortBy, startDate?: string, endDate?: string, contentType?: string, privacyStatus?: string, title?: string) =>
  fetch(buildUrl("/analytics/videos/top", { sort_by: sortBy, ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }), ...(contentType && { content_type: contentType }), ...(privacyStatus && { privacy_status: privacyStatus }), ...(title && { title }) })).then(r => r.json())

export const getPlaylistTopVideosByViews = (id: string, sortBy: TopVideoSortBy, startDate?: string, endDate?: string, contentType?: string, privacyStatus?: string, title?: string) =>
  fetch(buildUrl(`/analytics/playlists/${id}/top`, { sort_by: sortBy, ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }), ...(contentType && { content_type: contentType }), ...(privacyStatus && { privacy_status: privacyStatus }), ...(title && { title }) })).then(r => r.json())

export const getPlaylistAnalytics = (id: string, params?: Record<string, string>) =>
  fetch(buildUrl(`/analytics/playlists/${id}`, params)).then(r => r.json())

export const getPlaylistAggregatedAnalytics = (id: string, params?: Record<string, string>) =>
  fetch(buildUrl(`/analytics/playlists/${id}`, params)).then(r => r.json())

export const getChannelTrafficSources = (params?: Record<string, string>) =>
  fetch(buildUrl("/analytics/traffic-sources", params)).then(r => r.json())

export const getPlaylistTrafficSources = (id: string, params?: Record<string, string>) =>
  fetch(buildUrl(`/analytics/playlists/${id}/traffic-sources`, params)).then(r => r.json())

export const getTopVideosByTrafficSource = (params?: Record<string, string>) =>
  fetch(buildUrl("/analytics/traffic-sources/top", params)).then(r => r.json())

export const getPlaylistTopVideosByTrafficSource = (id: string, params?: Record<string, string>) =>
  fetch(buildUrl(`/analytics/playlists/${id}/traffic-sources/top`, params)).then(r => r.json())

export const getVideosPublished = (startDate?: string, endDate?: string, contentType?: string, privacyStatus?: string, playlistId?: string, title?: string) =>
  fetch(buildUrl("/videos/published", { ...(startDate && { start_date: startDate }), ...(endDate && { end_date: endDate }), ...(contentType && { content_type: contentType }), ...(privacyStatus && { privacy_status: privacyStatus }), ...(playlistId && { playlist_id: playlistId }), ...(title && { title }) })).then(r => r.json())

/** Filters accepted by all three comment endpoints. Scope comes from the path, not here. */
export interface CommentQuery {
  page?: number
  pageSize?: number
  sortBy?: CommentSort
  text?: string
  videoTitle?: string
  author?: string
  startDate?: string
  endDate?: string
  contentType?: string
}

function commentParams(query: CommentQuery): Record<string, string> {
  return {
    ...(query.page && { page: String(query.page) }),
    ...(query.pageSize && { page_size: String(query.pageSize) }),
    ...(query.sortBy && { sort_by: query.sortBy }),
    ...(query.text && { text: query.text }),
    ...(query.videoTitle && { video_title: query.videoTitle }),
    ...(query.author && { author: query.author }),
    ...(query.startDate && { start_date: query.startDate }),
    ...(query.endDate && { end_date: query.endDate }),
    ...(query.contentType && { content_type: query.contentType }),
  }
}

async function fetchComments(path: string, query: CommentQuery): Promise<CommentsResponse> {
  const response = await fetch(buildUrl(path, commentParams(query)))
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
 * Fetch one page of sync history, grouped into batches — `page`/`pageSize` count batches,
 * not stage rows, and each item carries its own stages in `runs`. Failures reject with a
 * message derived only from the HTTP status, so a backend exception body can never reach
 * the history UI.
 */
export const getSyncRuns = async (page: number, pageSize: number): Promise<SyncRunsResponse> => {
  const response = await fetch(buildUrl("/sync/runs", {
    page: String(page),
    page_size: String(pageSize),
  }))
  if (!response.ok) throw new Error(`Sync history request failed (${response.status})`)
  return response.json() as Promise<SyncRunsResponse>
}
