import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getChannelTrafficSources,
  getComments,
  getPlaylistRelatedVideoDestinations,
  getPlaylistVideos,
  getRelatedVideoReferrers,
  getSyncRuns,
  getVideoAnalytics,
  getVideoRelatedVideoReferrers,
  getVideosBySearchTerm,
  getVideosPublished,
} from '@/api'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockImplementation(async () => new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

/** The requested path and query of the most recent fetch, with query keys sorted. */
function lastRequest(): { path: string; query: Record<string, string> } {
  const url = new URL(fetchMock.mock.calls.at(-1)![0] as string)
  const query = Object.fromEntries([...url.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b)))
  return { path: url.pathname, query }
}

describe('query serialization', () => {
  it('maps channel catalog filters to snake_case and omits empty values', async () => {
    await getChannelTrafficSources({ startDate: '2024-01-01', endDate: '', title: 'cats', contentType: '', privacyStatus: 'public' })
    expect(lastRequest()).toEqual({
      path: '/analytics/traffic-sources',
      query: { privacy_status: 'public', start_date: '2024-01-01', title: 'cats' },
    })
  })

  it('sends no query string for empty filters', async () => {
    await getChannelTrafficSources({})
    expect(fetchMock.mock.calls.at(-1)![0]).toBe('http://localhost:8000/analytics/traffic-sources')
  })

  it('keeps the playlist id in the path and listing options in the query', async () => {
    await getPlaylistVideos('pl1', { page: 2, pageSize: 25, sortBy: 'published_at', sortDir: 'asc', contentType: 'short' })
    expect(lastRequest()).toEqual({
      path: '/playlists/pl1/videos',
      query: { content_type: 'short', page: '2', page_size: '25', sort_by: 'published_at', sort_dir: 'asc' },
    })
  })

  it('maps playlistId on the published-videos query', async () => {
    await getVideosPublished({ startDate: '2024-01-01', playlistId: 'pl1' })
    expect(lastRequest().query).toEqual({ playlist_id: 'pl1', start_date: '2024-01-01' })
  })

  it('sends only date filters for a single-video endpoint', async () => {
    await getVideoAnalytics('v1', { startDate: '2024-01-01', endDate: '2024-01-31' })
    expect(lastRequest()).toEqual({
      path: '/videos/v1/analytics',
      query: { end_date: '2024-01-31', start_date: '2024-01-01' },
    })
  })

  it('sends the selected search term and limit', async () => {
    await getVideosBySearchTerm({ searchTerm: 'cats', privacyStatus: 'public', limit: 1000 })
    expect(lastRequest().query).toEqual({ limit: '1000', privacy_status: 'public', search_term: 'cats' })
  })

  it('sends own=false rather than omitting it', async () => {
    await getRelatedVideoReferrers({ own: false, title: '', limit: 1000 })
    expect(lastRequest()).toEqual({
      path: '/analytics/related-videos/referrers',
      query: { limit: '1000', own: 'false' },
    })
    await getVideoRelatedVideoReferrers('v1', { own: true })
    expect(lastRequest()).toEqual({ path: '/analytics/videos/v1/related-videos/referrers', query: { own: 'true' } })
  })

  it('maps the referrer id on playlist destinations', async () => {
    await getPlaylistRelatedVideoDestinations('pl1', { referrerVideoId: 'ref1', startDate: '2024-01-01' })
    expect(lastRequest()).toEqual({
      path: '/analytics/playlists/pl1/related-videos/destinations',
      query: { referrer_video_id: 'ref1', start_date: '2024-01-01' },
    })
  })

  it('maps comment filters and omits empty text', async () => {
    await getComments({ page: 1, pageSize: 25, sortBy: 'likes', text: '', videoTitle: 'cat', author: 'a' })
    expect(lastRequest()).toEqual({
      path: '/comments',
      query: { author: 'a', page: '1', page_size: '25', sort_by: 'likes', video_title: 'cat' },
    })
  })

  it('rejects unsupported and missing options at compile time', async () => {
    // @ts-expect-error single-video endpoints accept only date filters
    await getVideoAnalytics('v1', { title: 'cats' })
    // @ts-expect-error ownership is required
    await getRelatedVideoReferrers({ limit: 10 })
    // @ts-expect-error the search term is required
    await getVideosBySearchTerm({ startDate: '2024-01-01' })
  })

  it('serializes sync history paging', async () => {
    await getSyncRuns(3, 25)
    expect(lastRequest()).toEqual({ path: '/sync/runs', query: { page: '3', page_size: '25' } })
  })
})
