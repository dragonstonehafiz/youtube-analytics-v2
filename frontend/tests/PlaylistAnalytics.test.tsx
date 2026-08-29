// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

vi.mock('@/api', () => ({
  getPlaylist: vi.fn(),
  getPlaylistVideos: vi.fn(),
  getPlaylistVideoStats: vi.fn(),
  getPlaylistAnalytics: vi.fn(),
  getPlaylistTopVideosByViews: vi.fn(),
  getVideosPublished: vi.fn(),
  getPlaylistTrafficSources: vi.fn(),
  getPlaylistTopVideosByTrafficSource: vi.fn(),
  getDateRange: vi.fn(),
}))

import {
  getDateRange,
  getPlaylist,
  getPlaylistAnalytics,
  getPlaylistTopVideosByTrafficSource,
  getPlaylistTopVideosByViews,
  getPlaylistTrafficSources,
  getPlaylistVideoStats,
  getPlaylistVideos,
  getVideosPublished,
} from '@/api'
import PlaylistAnalytics from '@/pages/PlaylistAnalytics'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useDebouncedInput'

const mockGetPlaylist = vi.mocked(getPlaylist)
const mockGetPlaylistVideos = vi.mocked(getPlaylistVideos)
const mockGetPlaylistVideoStats = vi.mocked(getPlaylistVideoStats)
const mockGetPlaylistAnalytics = vi.mocked(getPlaylistAnalytics)
const mockGetPlaylistTopVideosByViews = vi.mocked(getPlaylistTopVideosByViews)
const mockGetVideosPublished = vi.mocked(getVideosPublished)
const mockGetPlaylistTrafficSources = vi.mocked(getPlaylistTrafficSources)
const mockGetPlaylistTopVideosByTrafficSource = vi.mocked(getPlaylistTopVideosByTrafficSource)
const mockGetDateRange = vi.mocked(getDateRange)

/** AnalyticsChart and TrafficSourceChart measure their container; jsdom has no real implementation. */
class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', StubResizeObserver)

function renderPlaylistAnalytics(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/playlists/:id" element={<PlaylistAnalytics />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** Exposes the current route's search string so tests can assert on it without parsing the DOM. */
function LocationProbe({ onLocation }: { onLocation: (search: string) => void }) {
  onLocation(useLocation().search)
  return null
}

function renderPlaylistAnalyticsWithSearch(route: string) {
  let search = ''
  const utils = render(
    <MemoryRouter initialEntries={[route]}>
      <LocationProbe onLocation={s => { search = s }} />
      <Routes>
        <Route path="/playlists/:id" element={<PlaylistAnalytics />} />
      </Routes>
    </MemoryRouter>,
  )
  return { ...utils, getSearch: () => search }
}

beforeEach(() => {
  mockGetPlaylist.mockResolvedValue({
    item: {
      id: 'pl1', title: 'My Playlist', thumbnail_url: null, item_count: 3,
      total_views: 0, total_earnings_sgd: 0, last_item_added: null, published_at: '2024-01-01T00:00:00Z',
    },
  })
  mockGetPlaylistVideos.mockResolvedValue({ items: [], total: 0 })
  mockGetPlaylistVideoStats.mockResolvedValue({
    legacy_video_count: 0, legacy_video_views: 0, legacy_video_earnings_sgd: 0,
    legacy_short_count: 0, legacy_short_views: 0, legacy_short_earnings_sgd: 0,
    new_video_count: 0, new_video_views: 0, new_video_earnings_sgd: 0,
    new_short_count: 0, new_short_views: 0, new_short_earnings_sgd: 0,
    total_comments: 0, video_comments: 0, short_comments: 0,
    total_public: 0, total_private: 0, total_unlisted: 0,
  })
  mockGetPlaylistAnalytics.mockResolvedValue({ items: [] })
  mockGetPlaylistTopVideosByViews.mockResolvedValue({ items: [] })
  mockGetVideosPublished.mockResolvedValue({ items: [] })
  mockGetPlaylistTrafficSources.mockResolvedValue({ items: [] })
  mockGetPlaylistTopVideosByTrafficSource.mockResolvedValue({ items: {} })
  mockGetDateRange.mockResolvedValue({ earliest_year: 2022 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

/** Sidebar Top-card calls always sort by views; the main table call uses the page's own sort. */
function sidebarTopCalls() {
  return mockGetPlaylistTopVideosByViews.mock.calls.filter(call => call[1] === 'views')
}

/** Sidebar Recent-card calls always request page 1 at the fixed recent count. */
function sidebarRecentCalls() {
  return mockGetPlaylistVideos.mock.calls.filter(call => call[2] === 10)
}

describe('playlist sidebar cards', () => {
  it('scopes sidebar requests to analytics_* filters, ignoring the Videos tab namespace', async () => {
    renderPlaylistAnalytics(
      '/playlists/pl1?tab=analytics&title=videostab&privacy_status=unlisted' +
      '&analytics_title=foo&analytics_privacy_status=private',
    )

    await waitFor(() => expect(sidebarRecentCalls()).toHaveLength(2))
    for (const call of sidebarRecentCalls()) {
      expect(call[0]).toBe('pl1')
      expect(call[5]).toBe('foo')
      expect(call[6]).toBeUndefined()
      expect(call[7]).toBeUndefined()
      expect(call[9]).toBe('private')
    }
    expect(sidebarRecentCalls().map(c => c[8]).sort()).toEqual(['short', 'video'])

    await waitFor(() => expect(sidebarTopCalls()).toHaveLength(2))
    for (const call of sidebarTopCalls()) {
      expect(call[0]).toBe('pl1')
      expect(call[5]).toBe('private')
      expect(call[6]).toBe('foo')
    }
    expect(sidebarTopCalls().map(c => c[4]).sort()).toEqual(['short', 'video'])
  })

  it('resolves the opposite type empty without requesting it when analytics_content_type=video', async () => {
    renderPlaylistAnalytics('/playlists/pl1?tab=analytics&analytics_content_type=video')

    await waitFor(() => expect(sidebarRecentCalls()).toHaveLength(1))
    expect(sidebarRecentCalls()[0][8]).toBe('video')
    await waitFor(() => expect(sidebarTopCalls()).toHaveLength(1))
    expect(sidebarTopCalls()[0][4]).toBe('video')

    const shortsHeading = await screen.findByText('Top Shorts (Last 7 Days)')
    expect(shortsHeading.closest('.async-card')?.textContent).toContain('No videos for this period')

    const latestShortsHeading = screen.getByText('Latest Shorts')
    expect(latestShortsHeading.closest('.async-card')?.textContent).toContain('No videos for this period')

    expect(sidebarRecentCalls().some(c => c[8] === 'short')).toBe(false)
    expect(sidebarTopCalls().some(c => c[4] === 'short')).toBe(false)
  })
})

describe('Analytics Title search debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces analytics_title independently from the Videos tab title namespace', async () => {
    const { getSearch } = renderPlaylistAnalyticsWithSearch('/playlists/pl1?tab=analytics&title=videostab')
    const input = await screen.findByPlaceholderText('Search…')
    mockGetPlaylistAnalytics.mockClear()

    fireEvent.change(input, { target: { value: 'f' } })
    fireEvent.change(input, { target: { value: 'fo' } })
    fireEvent.change(input, { target: { value: 'foo' } })

    expect((input as HTMLInputElement).value).toBe('foo')
    expect(new URLSearchParams(getSearch()).has('analytics_title')).toBe(false)
    expect(mockGetPlaylistAnalytics).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    const params = new URLSearchParams(getSearch())
    expect(params.get('analytics_title')).toBe('foo')
    expect(params.get('title')).toBe('videostab')
    await waitFor(() => expect(mockGetPlaylistAnalytics).toHaveBeenCalled())
    expect(mockGetPlaylistVideoStats.mock.calls.some(c => c[1] === 'foo')).toBe(true)
  })
})
