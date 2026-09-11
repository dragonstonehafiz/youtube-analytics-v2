// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('@/api', () => ({
  getVideo: vi.fn(),
  getVideoAnalytics: vi.fn(),
  getVideoTrafficSources: vi.fn(),
  getVideoSearchTerms: vi.fn(),
  getVideoRelatedVideoReferrers: vi.fn(),
  getRelatedVideoDestinations: vi.fn(),
  getDateRange: vi.fn(),
}))

import {
  getDateRange,
  getRelatedVideoDestinations,
  getVideo,
  getVideoAnalytics,
  getVideoRelatedVideoReferrers,
  getVideoSearchTerms,
  getVideoTrafficSources,
} from '@/api'
import VideoAnalytics from '@/pages/VideoAnalytics'

const mockGetVideo = vi.mocked(getVideo)
const mockGetVideoAnalytics = vi.mocked(getVideoAnalytics)
const mockGetVideoTrafficSources = vi.mocked(getVideoTrafficSources)
const mockGetVideoSearchTerms = vi.mocked(getVideoSearchTerms)
const mockGetVideoRelatedVideoReferrers = vi.mocked(getVideoRelatedVideoReferrers)
const mockGetRelatedVideoDestinations = vi.mocked(getRelatedVideoDestinations)
const mockGetDateRange = vi.mocked(getDateRange)

/** AnalyticsChart and TrafficSourceChart measure their container; jsdom has no real implementation. */
class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', StubResizeObserver)

function renderVideoAnalytics(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/analytics/videos/:id" element={<VideoAnalytics />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockGetVideo.mockResolvedValue({
    item: {
      id: 'v1', title: 'My Video', description: null, published_at: '2024-01-01T00:00:00Z',
      duration_seconds: 120, thumbnail_url: null, content_type: 'video',
      view_count: 0, like_count: 0, comment_count: 0, total_revenue_sgd: 0, total_watch_time_hours: 0,
    },
  })
  mockGetVideoAnalytics.mockResolvedValue({ items: [] })
  mockGetVideoTrafficSources.mockResolvedValue({ items: [] })
  mockGetVideoSearchTerms.mockResolvedValue({ items: [] })
  mockGetVideoRelatedVideoReferrers.mockResolvedValue({ items: [], total_named_views: 0 })
  mockGetRelatedVideoDestinations.mockResolvedValue({ items: [] })
  mockGetDateRange.mockResolvedValue({ earliest_year: 2022 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('Traffic Sources sub-tabs (Search Insights)', () => {
  it('defaults to the Traffic Sources sub-tab, switching to Search Insights renders the single donut card', async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources')
    await waitFor(() => expect(mockGetVideoTrafficSources).toHaveBeenCalled())
    expect(screen.queryByText('Top Search Terms')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Search Insights' }))
    expect(await screen.findByText('Top Search Terms')).toBeDefined()
  })

  it('has only two sub-tabs and no sidebar — no "Top Videos by Traffic Source" entry', async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources')
    await waitFor(() => expect(mockGetVideoTrafficSources).toHaveBeenCalled())

    expect(screen.queryByRole('button', { name: 'Top Videos by Traffic Source' })).toBeNull()
    expect(screen.queryByText(/Top (Videos|Shorts) by Search Term/)).toBeNull()
  })

  it('scopes the Search Insights fetch to this video id and the shared date filters', async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources&start_date=2024-01-01&end_date=2024-01-31')

    await waitFor(() => expect(mockGetVideoSearchTerms).toHaveBeenCalledWith('v1', '2024-01-01', '2024-01-31'))
  })

  it('a date-filter change refetches the Search Insights donut, not just the traffic chart', async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources')
    await waitFor(() => expect(mockGetVideoSearchTerms).toHaveBeenCalled())
    mockGetVideoSearchTerms.mockClear()

    const startInput = screen.getByLabelText('Start') as HTMLInputElement
    fireEvent.change(startInput, { target: { value: '2024-02-01' } })

    await waitFor(() => expect(mockGetVideoSearchTerms).toHaveBeenCalledWith(
      'v1', '2024-02-01', expect.any(String),
    ))
  })

  it('shows the donut card error state when the request fails', async () => {
    mockGetVideoSearchTerms.mockRejectedValue(new Error('boom'))
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources&ts_tab=search')

    expect(await screen.findByText('boom')).toBeDefined()
  })

  it('an unrecognized ts_tab value falls back to the Traffic Sources sub-tab', async () => {
    const { container } = renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources&ts_tab=bogus')
    await waitFor(() => expect(mockGetVideoTrafficSources).toHaveBeenCalled())

    const tabStrips = container.querySelectorAll('.tabs')
    const subTabStrip = tabStrips[tabStrips.length - 1] as HTMLElement
    const sourcesTab = within(subTabStrip).getByRole('button', { name: 'Traffic Sources' })
    expect(sourcesTab.className).toContain('active')
    expect(screen.queryByText('Top Search Terms')).toBeNull()
  })
})

describe('Related Videos sub-tab', () => {
  const mineRow = { referrer_video_id: 'ref-mine', title: 'My Video', thumbnail_url: null, referrer_own: true, views: 50 }
  const externalRow = { referrer_video_id: 'ref-ext', title: 'External Video', thumbnail_url: null, referrer_own: false, views: 30 }

  beforeEach(() => {
    mockGetVideoRelatedVideoReferrers.mockImplementation(async (_id: string, own: boolean) =>
      own
        ? { items: [mineRow], total_named_views: 80 }
        : { items: [externalRow], total_named_views: 80 })
  })

  it('fetches nothing until the Related Videos sub-tab is actually visible', async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources&ts_tab=sources')
    await waitFor(() => expect(mockGetVideoTrafficSources).toHaveBeenCalled())
    expect(mockGetVideoRelatedVideoReferrers).not.toHaveBeenCalled()
    expect(mockGetRelatedVideoDestinations).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Related Videos' }))
    await waitFor(() => expect(mockGetVideoRelatedVideoReferrers).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(mockGetRelatedVideoDestinations).toHaveBeenCalled())
  })

  it('renders row 1 and a single outbound destinations card with no dropdown', async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources&ts_tab=related')

    expect(await screen.findByText('Related Traffic from My Channel')).toBeDefined()
    expect(await screen.findByText('Related Traffic from Other Channels')).toBeDefined()
    expect(await screen.findByText('Top Destinations From This Video')).toBeDefined()
    expect(screen.queryByRole('combobox', { name: /Top Destinations From This Video referrer/ })).toBeNull()
  })

  it('scopes the referrers fetch to this video id for both ownership buckets', async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources&ts_tab=related&start_date=2024-01-01&end_date=2024-01-31')

    await waitFor(() => expect(mockGetVideoRelatedVideoReferrers).toHaveBeenCalledTimes(2))
    for (const call of mockGetVideoRelatedVideoReferrers.mock.calls) {
      expect(call[0]).toBe('v1')
      expect(call[2]).toBe('2024-01-01')
      expect(call[3]).toBe('2024-01-31')
    }
    expect(mockGetVideoRelatedVideoReferrers.mock.calls.map(c => c[1]).sort()).toEqual([false, true])
  })

  it("calls the channel-scoped destinations endpoint with this video's own ID as the referrer, not a video-scoped route", async () => {
    renderVideoAnalytics('/analytics/videos/v1?tab=traffic-sources&ts_tab=related&start_date=2024-01-01&end_date=2024-01-31')

    await waitFor(() => expect(mockGetRelatedVideoDestinations).toHaveBeenCalledWith('v1', '2024-01-01', '2024-01-31', 1000))
  })
})
