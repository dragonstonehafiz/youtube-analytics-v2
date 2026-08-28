// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

vi.mock('@/api', () => ({
  getVideoStats: vi.fn(),
  getChannelAnalytics: vi.fn(),
  getTopVideosByViews: vi.fn(),
  getVideosPublished: vi.fn(),
  getVideos: vi.fn(),
  getChannelTrafficSources: vi.fn(),
  getTopVideosByTrafficSource: vi.fn(),
  getComments: vi.fn(),
  getVideoComments: vi.fn(),
  getPlaylistComments: vi.fn(),
  getDateRange: vi.fn(),
}))

import {
  getChannelAnalytics,
  getChannelTrafficSources,
  getComments,
  getDateRange,
  getTopVideosByTrafficSource,
  getTopVideosByViews,
  getVideoStats,
  getVideos,
  getVideosPublished,
} from '@/api'
import Analytics from '@/pages/Analytics'

const mockGetVideoStats = vi.mocked(getVideoStats)
const mockGetChannelAnalytics = vi.mocked(getChannelAnalytics)
const mockGetTopVideosByViews = vi.mocked(getTopVideosByViews)
const mockGetVideosPublished = vi.mocked(getVideosPublished)
const mockGetVideos = vi.mocked(getVideos)
const mockGetChannelTrafficSources = vi.mocked(getChannelTrafficSources)
const mockGetTopVideosByTrafficSource = vi.mocked(getTopVideosByTrafficSource)
const mockGetComments = vi.mocked(getComments)
const mockGetDateRange = vi.mocked(getDateRange)

/** AnalyticsChart and TrafficSourceChart measure their container; jsdom has no real implementation. */
class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', StubResizeObserver)

/** Exposes the current route's search string so tests can assert on it without parsing the DOM. */
function LocationProbe({ onLocation }: { onLocation: (search: string) => void }) {
  onLocation(useLocation().search)
  return null
}

function renderAnalytics(route = '/analytics') {
  let search = ''
  const utils = render(
    <MemoryRouter initialEntries={[route]}>
      <LocationProbe onLocation={s => { search = s }} />
      <Analytics />
    </MemoryRouter>,
  )
  return { ...utils, getSearch: () => search }
}

/**
 * Mounts Analytics behind a real route transition rather than an initial entry, so
 * normalization is proven for in-app navigation to a bare route, not just direct load.
 */
function renderAnalyticsViaNavigation() {
  let search = ''
  const utils = render(
    <MemoryRouter initialEntries={['/elsewhere']}>
      <LocationProbe onLocation={s => { search = s }} />
      <Routes>
        <Route path="/elsewhere" element={<Link to="/analytics">Go to Analytics</Link>} />
        <Route path="/analytics" element={<Analytics />} />
      </Routes>
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('link', { name: 'Go to Analytics' }))
  return { ...utils, getSearch: () => search }
}

/** The tab button carrying the `active` class, or undefined if none does. */
function activeTabButton(): HTMLElement | undefined {
  return screen.getAllByRole('button', { name: /^(Analytics|Traffic Sources|Comments)$/ })
    .find(button => button.className.includes('active'))
}

beforeEach(() => {
  mockGetVideoStats.mockResolvedValue({
    legacy_video_count: 0, legacy_video_views: 0, legacy_video_earnings_sgd: 0,
    legacy_short_count: 0, legacy_short_views: 0, legacy_short_earnings_sgd: 0,
    new_video_count: 0, new_video_views: 0, new_video_earnings_sgd: 0,
    new_short_count: 0, new_short_views: 0, new_short_earnings_sgd: 0,
    total_comments: 0, video_comments: 0, short_comments: 0,
    total_public: 0, total_private: 0, total_unlisted: 0,
  })
  mockGetChannelAnalytics.mockResolvedValue({ items: [] })
  mockGetTopVideosByViews.mockResolvedValue({ items: [] })
  mockGetVideosPublished.mockResolvedValue({ items: [] })
  mockGetVideos.mockResolvedValue({ items: [] })
  mockGetChannelTrafficSources.mockResolvedValue({ items: [] })
  mockGetTopVideosByTrafficSource.mockResolvedValue({ items: {} })
  mockGetComments.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
  mockGetDateRange.mockResolvedValue({ earliest_year: 2022 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('tab selection and URL state', () => {
  it('writes the explicit default tab into the URL on bare entry', async () => {
    const { getSearch } = renderAnalytics('/analytics')

    await waitFor(() => expect(getSearch()).toBe('?tab=analytics'))
    expect(activeTabButton()?.textContent).toBe('Analytics')
    expect(await screen.findByText('Top 10 Videos by Watch Time')).toBeDefined()
  })

  it('normalizes a bare route reached through in-app navigation, not just direct load', async () => {
    const { getSearch } = renderAnalyticsViaNavigation()

    await waitFor(() => expect(getSearch()).toBe('?tab=analytics'))
    expect(activeTabButton()?.textContent).toBe('Analytics')
  })

  it('preserves unrelated query parameters while writing the default tab', async () => {
    const { getSearch } = renderAnalytics('/analytics?sentinel=kept')

    await waitFor(() => {
      const params = new URLSearchParams(getSearch())
      expect(params.get('tab')).toBe('analytics')
      expect(params.get('sentinel')).toBe('kept')
    })
  })

  it('does not duplicate or overwrite an explicit non-default tab', async () => {
    const { getSearch } = renderAnalytics('/analytics?tab=comments')

    expect(await screen.findByText('No comments found')).toBeDefined()
    expect(activeTabButton()?.textContent).toBe('Comments')
    expect(screen.queryByText('Top 10 Videos by Watch Time')).toBeNull()
    expect(getSearch()).toBe('?tab=comments')
  })

  it('keeps explicit tab selections, the active tab, and the rendered content in sync on every switch', async () => {
    const { getSearch } = renderAnalytics('/analytics')
    await waitFor(() => expect(getSearch()).toBe('?tab=analytics'))
    expect(await screen.findByText('Top 10 Videos by Watch Time')).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'Traffic Sources' }))
    await waitFor(() => expect(getSearch()).toBe('?tab=traffic-sources'))
    expect(activeTabButton()?.textContent).toBe('Traffic Sources')
    expect(await screen.findByText('Top Videos by Traffic Source')).toBeDefined()
    expect(screen.queryByText('Top 10 Videos by Watch Time')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Comments' }))
    await waitFor(() => expect(getSearch()).toBe('?tab=comments'))
    expect(activeTabButton()?.textContent).toBe('Comments')
    expect(await screen.findByText('No comments found')).toBeDefined()
    expect(screen.queryByText('Top Videos by Traffic Source')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Analytics' }))
    await waitFor(() => expect(getSearch()).toBe('?tab=analytics'))
    expect(activeTabButton()?.textContent).toBe('Analytics')
    expect(await screen.findByText('Top 10 Videos by Watch Time')).toBeDefined()
    expect(screen.queryByText('No comments found')).toBeNull()
  })
})

/** Sidebar Top-card calls always sort by views; the main table call uses the page's own sort. */
function sidebarTopCalls() {
  return mockGetTopVideosByViews.mock.calls.filter(call => call[0] === 'views')
}

describe('sidebar cards', () => {
  it('forwards title and privacy to all four sidebar surfaces while keeping their fixed periods', async () => {
    renderAnalytics('/analytics?tab=analytics&title=foo&privacy_status=private')

    await waitFor(() => expect(mockGetVideos).toHaveBeenCalledTimes(2))
    for (const call of mockGetVideos.mock.calls) {
      expect(call[4]).toBe('foo')
      expect(call[5]).toBeUndefined()
      expect(call[6]).toBeUndefined()
      expect(call[8]).toBe('private')
    }
    expect(mockGetVideos.mock.calls.map(c => c[7]).sort()).toEqual(['short', 'video'])

    await waitFor(() => expect(sidebarTopCalls()).toHaveLength(2))
    for (const call of sidebarTopCalls()) {
      expect(call[1]).toEqual(expect.any(String))
      expect(call[2]).toEqual(expect.any(String))
      expect(call[4]).toBe('private')
      expect(call[5]).toBe('foo')
    }
    expect(sidebarTopCalls().map(c => c[3]).sort()).toEqual(['short', 'video'])
  })

  it('resolves the opposite type empty without requesting it when Type=Video is selected', async () => {
    renderAnalytics('/analytics?tab=analytics&content_type=video')

    await waitFor(() => expect(mockGetVideos).toHaveBeenCalledTimes(1))
    expect(mockGetVideos.mock.calls[0][7]).toBe('video')
    await waitFor(() => expect(sidebarTopCalls()).toHaveLength(1))
    expect(sidebarTopCalls()[0][3]).toBe('video')

    const shortsHeading = await screen.findByText('Top Shorts (Last 7 Days)')
    const shortsCard = shortsHeading.closest('.async-card')
    expect(shortsCard?.textContent).toContain('No videos for this period')

    const latestShortsHeading = screen.getByText('Latest Shorts')
    const latestShortsCard = latestShortsHeading.closest('.async-card')
    expect(latestShortsCard?.textContent).toContain('No videos for this period')

    expect(mockGetVideos.mock.calls.some(c => c[7] === 'short')).toBe(false)
    expect(sidebarTopCalls().some(c => c[3] === 'short')).toBe(false)
  })

  it('resolves the opposite type empty without requesting it when Type=Short is selected', async () => {
    renderAnalytics('/analytics?tab=analytics&content_type=short')

    await waitFor(() => expect(mockGetVideos).toHaveBeenCalledTimes(1))
    expect(mockGetVideos.mock.calls[0][7]).toBe('short')
    await waitFor(() => expect(sidebarTopCalls()).toHaveLength(1))
    expect(sidebarTopCalls()[0][3]).toBe('short')

    const videosHeading = await screen.findByText('Top Videos (Last 7 Days)')
    const videosCard = videosHeading.closest('.async-card')
    expect(videosCard?.textContent).toContain('No videos for this period')

    const latestVideosHeading = screen.getByText('Latest Videos')
    const latestVideosCard = latestVideosHeading.closest('.async-card')
    expect(latestVideosCard?.textContent).toContain('No videos for this period')

    expect(mockGetVideos.mock.calls.some(c => c[7] === 'video')).toBe(false)
    expect(sidebarTopCalls().some(c => c[3] === 'video')).toBe(false)
  })
})
