// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

vi.mock('@/api', () => ({
  getVideoStats: vi.fn(),
  getChannelAnalytics: vi.fn(),
  getTopVideosByViews: vi.fn(),
  getVideosPublished: vi.fn(),
  getVideos: vi.fn(),
  getChannelTrafficSources: vi.fn(),
  getTopVideosByTrafficSource: vi.fn(),
  getSearchTerms: vi.fn(),
  getVideosBySearchTerm: vi.fn(),
  getRelatedVideoReferrers: vi.fn(),
  getRelatedVideoDestinations: vi.fn(),
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
  getRelatedVideoDestinations,
  getRelatedVideoReferrers,
  getSearchTerms,
  getTopVideosByTrafficSource,
  getTopVideosByViews,
  getVideoStats,
  getVideos,
  getVideosBySearchTerm,
  getVideosPublished,
} from '@/api'
import Analytics from '@/pages/Analytics'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useDebouncedInput'

const mockGetVideoStats = vi.mocked(getVideoStats)
const mockGetChannelAnalytics = vi.mocked(getChannelAnalytics)
const mockGetTopVideosByViews = vi.mocked(getTopVideosByViews)
const mockGetVideosPublished = vi.mocked(getVideosPublished)
const mockGetVideos = vi.mocked(getVideos)
const mockGetChannelTrafficSources = vi.mocked(getChannelTrafficSources)
const mockGetTopVideosByTrafficSource = vi.mocked(getTopVideosByTrafficSource)
const mockGetSearchTerms = vi.mocked(getSearchTerms)
const mockGetVideosBySearchTerm = vi.mocked(getVideosBySearchTerm)
const mockGetRelatedVideoReferrers = vi.mocked(getRelatedVideoReferrers)
const mockGetRelatedVideoDestinations = vi.mocked(getRelatedVideoDestinations)
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
  mockGetSearchTerms.mockResolvedValue({ items: [] })
  mockGetVideosBySearchTerm.mockResolvedValue({ items: [] })
  mockGetRelatedVideoReferrers.mockResolvedValue({ items: [], total_named_views: 0 })
  mockGetRelatedVideoDestinations.mockResolvedValue({ items: [] })
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

describe('Traffic Sources sub-tabs', () => {
  it('defaults to the Traffic Sources sub-tab, switching to Search Insights renders its three columns', async () => {
    renderAnalytics('/analytics?tab=traffic-sources')
    await waitFor(() => expect(mockGetChannelTrafficSources).toHaveBeenCalled())
    expect(screen.queryByText('Top Search Terms')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Search Insights' }))
    expect(await screen.findByText('Top Search Terms')).toBeDefined()
    expect(await screen.findByText('Top Search Terms — Videos')).toBeDefined()
    expect(await screen.findByText('Top Search Terms — Shorts')).toBeDefined()
  })

  it('renders one independent sidebar card per content type, each with its own dropdown', async () => {
    mockGetSearchTerms.mockResolvedValue({ items: [{ search_term: 'cats', views: 10 }] })
    renderAnalytics('/analytics?tab=traffic-sources&ts_tab=search')

    expect(await screen.findByText('Top Videos by Search Term')).toBeDefined()
    expect(await screen.findByText('Top Shorts by Search Term')).toBeDefined()
    await waitFor(() => expect(mockGetVideosBySearchTerm).toHaveBeenCalled())
    const contentTypes = mockGetVideosBySearchTerm.mock.calls.map(call => call[1]?.contentType)
    expect(contentTypes).toContain('video')
    expect(contentTypes).toContain('short')
  })
})

describe('Related Videos sub-tab', () => {
  const mineRow = { referrer_video_id: 'ref-mine', title: 'My Video', thumbnail_url: null, referrer_own: true, views: 50 }
  const externalRow = { referrer_video_id: 'ref-ext', title: 'External Video', thumbnail_url: null, referrer_own: false, views: 30 }
  const unresolvedRow = { referrer_video_id: 'ref-unresolved', title: null, thumbnail_url: null, referrer_own: null, views: 10 }

  beforeEach(() => {
    mockGetRelatedVideoReferrers.mockImplementation(async (own: boolean) =>
      own
        ? { items: [mineRow], total_named_views: 90 }
        : { items: [externalRow, unresolvedRow], total_named_views: 90 })
  })

  it('defaults to Traffic Sources, switching to Related Videos renders both rows of cards', async () => {
    renderAnalytics('/analytics?tab=traffic-sources')
    await waitFor(() => expect(mockGetChannelTrafficSources).toHaveBeenCalled())
    expect(screen.queryByText('Related Traffic from My Channel')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Related Videos' }))
    expect(await screen.findByText('Related Traffic from My Channel')).toBeDefined()
    expect(await screen.findByText('Related Traffic from Other Channels')).toBeDefined()
    expect(await screen.findByText('Top Destinations — My Channel')).toBeDefined()
    expect(await screen.findByText('Top Destinations — Other Channels')).toBeDefined()
  })

  it('fetches nothing until the Related Videos sub-tab is actually visible', async () => {
    renderAnalytics('/analytics?tab=traffic-sources&ts_tab=sources')
    await waitFor(() => expect(mockGetChannelTrafficSources).toHaveBeenCalled())
    expect(mockGetRelatedVideoReferrers).not.toHaveBeenCalled()
    expect(mockGetRelatedVideoDestinations).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Related Videos' }))
    await waitFor(() => expect(mockGetRelatedVideoReferrers).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(mockGetRelatedVideoDestinations).toHaveBeenCalledTimes(2))
  })

  it('requests referrers for both ownership buckets, forwarding the page filters', async () => {
    renderAnalytics(
      '/analytics?tab=traffic-sources&ts_tab=related&title=foo&content_type=video&privacy_status=public&start_date=2024-01-10&end_date=2024-01-20',
    )
    await waitFor(() => expect(mockGetRelatedVideoReferrers).toHaveBeenCalledTimes(2))

    const calls = mockGetRelatedVideoReferrers.mock.calls
    expect(calls.map(c => c[0]).sort()).toEqual([false, true])
    for (const call of calls) {
      expect(call[1]).toEqual({
        startDate: '2024-01-10', endDate: '2024-01-20', title: 'foo', contentType: 'video', privacyStatus: 'public',
      })
      expect(call[2]).toBe(1000)
    }
  })

  it('links an owned referrer internally, an external referrer to YouTube, and leaves an unresolved referrer unlinked', async () => {
    renderAnalytics('/analytics?tab=traffic-sources&ts_tab=related')
    const internalLink = await screen.findByRole('link', { name: 'My Video' })
    expect(internalLink.getAttribute('href')).toBe('/analytics/videos/ref-mine?tab=traffic-sources&ts_tab=related')

    const externalLink = screen.getByRole('link', { name: 'External Video' })
    expect(externalLink.getAttribute('href')).toBe('https://www.youtube.com/watch?v=ref-ext')
    expect(externalLink.getAttribute('target')).toBe('_blank')

    expect(screen.getByText('Unavailable Video: ref-unresolved')).toBeDefined()
    expect(screen.queryByRole('link', { name: /Unavailable Video/ })).toBeNull()
  })

  it("each destination card starts with its own bucket's top referrer and fetches independently", async () => {
    renderAnalytics('/analytics?tab=traffic-sources&ts_tab=related')
    await waitFor(() => expect(mockGetRelatedVideoDestinations).toHaveBeenCalledTimes(2))
    expect(mockGetRelatedVideoDestinations.mock.calls.map(c => c[0]).sort()).toEqual(['ref-ext', 'ref-mine'])
  })

  it('selecting a referrer in one destination card does not affect the other', async () => {
    renderAnalytics('/analytics?tab=traffic-sources&ts_tab=related')
    await waitFor(() => expect(mockGetRelatedVideoDestinations).toHaveBeenCalledTimes(2))
    mockGetRelatedVideoDestinations.mockClear()

    const otherSelect = screen.getByRole('combobox', { name: 'Top Destinations — Other Channels referrer' })
    fireEvent.change(otherSelect, { target: { value: 'ref-unresolved' } })

    await waitFor(() => expect(mockGetRelatedVideoDestinations).toHaveBeenCalledTimes(1))
    expect(mockGetRelatedVideoDestinations.mock.calls[0][0]).toBe('ref-unresolved')
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

describe('Title search debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not commit the URL or fan out requests until the user pauses typing', async () => {
    const { getSearch } = renderAnalytics('/analytics?tab=analytics')
    const input = await screen.findByPlaceholderText('Search…')
    mockGetChannelAnalytics.mockClear()
    mockGetVideoStats.mockClear()

    fireEvent.change(input, { target: { value: 'f' } })
    fireEvent.change(input, { target: { value: 'fo' } })
    fireEvent.change(input, { target: { value: 'foo' } })

    expect((input as HTMLInputElement).value).toBe('foo')
    expect(new URLSearchParams(getSearch()).has('title')).toBe(false)
    expect(mockGetChannelAnalytics).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    expect(new URLSearchParams(getSearch()).get('title')).toBe('foo')
    await waitFor(() => expect(mockGetChannelAnalytics).toHaveBeenCalled())
    expect(mockGetVideoStats.mock.calls.some(c => c[0] === 'foo')).toBe(true)
  })
})
