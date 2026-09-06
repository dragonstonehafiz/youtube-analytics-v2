// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('@/api', () => ({
  getVideo: vi.fn(),
  getVideoAnalytics: vi.fn(),
  getVideoTrafficSources: vi.fn(),
  getVideoSearchTerms: vi.fn(),
  getDateRange: vi.fn(),
}))

import {
  getDateRange,
  getVideo,
  getVideoAnalytics,
  getVideoSearchTerms,
  getVideoTrafficSources,
} from '@/api'
import VideoAnalytics from '@/pages/VideoAnalytics'

const mockGetVideo = vi.mocked(getVideo)
const mockGetVideoAnalytics = vi.mocked(getVideoAnalytics)
const mockGetVideoTrafficSources = vi.mocked(getVideoTrafficSources)
const mockGetVideoSearchTerms = vi.mocked(getVideoSearchTerms)
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
    expect(screen.queryByText(/^Top Videos —/)).toBeNull()
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
