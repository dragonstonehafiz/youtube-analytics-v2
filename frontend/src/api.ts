import type { VideoStats, TopVideoSortBy, SyncStatusResponse, SyncPlan, SyncQueuedResponse } from '@/types'

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
