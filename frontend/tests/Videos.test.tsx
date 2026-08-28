// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useDebouncedInput'

vi.mock('@/api', () => ({
  getVideos: vi.fn(),
  getVideoStats: vi.fn(),
  getDateRange: vi.fn(),
}))

import { getDateRange, getVideos, getVideoStats } from '@/api'
import Videos from '@/pages/Videos'

const mockGetVideos = vi.mocked(getVideos)
const mockGetVideoStats = vi.mocked(getVideoStats)
const mockGetDateRange = vi.mocked(getDateRange)

/** Exposes the current route's search string so tests can assert on it without parsing the DOM. */
function LocationProbe({ onLocation }: { onLocation: (search: string) => void }) {
  onLocation(useLocation().search)
  return null
}

function renderVideos(route = '/videos') {
  let search = ''
  const utils = render(
    <MemoryRouter initialEntries={[route]}>
      <LocationProbe onLocation={s => { search = s }} />
      <Videos />
    </MemoryRouter>,
  )
  return { ...utils, getSearch: () => search }
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockGetVideos.mockResolvedValue({ items: [], total: 0 })
  mockGetVideoStats.mockResolvedValue({
    legacy_video_count: 0, legacy_video_views: 0, legacy_video_earnings_sgd: 0,
    legacy_short_count: 0, legacy_short_views: 0, legacy_short_earnings_sgd: 0,
    new_video_count: 0, new_video_views: 0, new_video_earnings_sgd: 0,
    new_short_count: 0, new_short_views: 0, new_short_earnings_sgd: 0,
    total_comments: 0, video_comments: 0, short_comments: 0,
    total_public: 0, total_private: 0, total_unlisted: 0,
  })
  mockGetDateRange.mockResolvedValue({ earliest_year: 2022 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('Videos Title search debounce', () => {
  it('does not commit the URL or refetch until the user pauses typing', async () => {
    const { getSearch } = renderVideos('/videos')
    const input = await screen.findByPlaceholderText('Search…')
    mockGetVideos.mockClear()

    fireEvent.change(input, { target: { value: 'f' } })
    fireEvent.change(input, { target: { value: 'fo' } })
    fireEvent.change(input, { target: { value: 'foo' } })

    expect((input as HTMLInputElement).value).toBe('foo')
    expect(getSearch()).toBe('')
    expect(mockGetVideos).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    const params = new URLSearchParams(getSearch())
    expect(params.get('title')).toBe('foo')
    expect(params.get('page')).toBe('1')
    expect(mockGetVideos.mock.calls.some(c => c[4] === 'foo')).toBe(true)
  })

  it('resets to page 1 only once the search commits', async () => {
    const { getSearch } = renderVideos('/videos?page=2')
    const input = await screen.findByPlaceholderText('Search…')

    fireEvent.change(input, { target: { value: 'foo' } })
    expect(new URLSearchParams(getSearch()).get('page')).toBe('2')

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    const params = new URLSearchParams(getSearch())
    expect(params.get('title')).toBe('foo')
    expect(params.get('page')).toBe('1')
  })

  it('delays clearing the same way as typing, then deletes the param', async () => {
    const { getSearch } = renderVideos('/videos?title=existing')
    const input = await screen.findByPlaceholderText('Search…') as HTMLInputElement
    expect(input.value).toBe('existing')

    fireEvent.change(input, { target: { value: '' } })
    expect(new URLSearchParams(getSearch()).get('title')).toBe('existing')

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(new URLSearchParams(getSearch()).has('title')).toBe(false)
  })

  it('does not leak or lose a pending title draft when an immediate filter commits first', async () => {
    const { getSearch } = renderVideos('/videos')
    const input = await screen.findByPlaceholderText('Search…') as HTMLInputElement
    const typeSelect = screen.getByLabelText('Type') as HTMLSelectElement

    fireEvent.change(input, { target: { value: 'foo' } })
    fireEvent.change(typeSelect, { target: { value: 'short' } })

    const immediateParams = new URLSearchParams(getSearch())
    expect(immediateParams.get('content_type')).toBe('short')
    expect(immediateParams.has('title')).toBe(false)
    expect(input.value).toBe('foo')

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    const params = new URLSearchParams(getSearch())
    expect(params.get('title')).toBe('foo')
    expect(params.get('content_type')).toBe('short')
  })
})
