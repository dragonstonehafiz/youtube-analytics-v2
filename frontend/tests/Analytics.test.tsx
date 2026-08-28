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
