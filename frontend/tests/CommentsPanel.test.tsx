// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useDebouncedInput'

vi.mock('@/api', () => ({
  getComments: vi.fn(),
  getVideoComments: vi.fn(),
  getPlaylistComments: vi.fn(),
}))

import { getComments, getVideoComments } from '@/api'
import CommentsPanel from '@/components/CommentsPanel'

const mockGetComments = vi.mocked(getComments)
const mockGetVideoComments = vi.mocked(getVideoComments)

/** Exposes the current route's search string so tests can assert on it without parsing the DOM. */
function LocationProbe({ onLocation }: { onLocation: (search: string) => void }) {
  onLocation(useLocation().search)
  return null
}

function renderChannelPanel(route = '/analytics?tab=comments') {
  let search = ''
  const utils = render(
    <MemoryRouter initialEntries={[route]}>
      <LocationProbe onLocation={s => { search = s }} />
      <CommentsPanel scope={{ kind: 'channel' }} />
    </MemoryRouter>,
  )
  return { ...utils, getSearch: () => search }
}

function renderVideoPanel(route = '/analytics/videos/v1?tab=comments') {
  let search = ''
  const utils = render(
    <MemoryRouter initialEntries={[route]}>
      <LocationProbe onLocation={s => { search = s }} />
      <CommentsPanel scope={{ kind: 'video', videoId: 'v1' }} />
    </MemoryRouter>,
  )
  return { ...utils, getSearch: () => search }
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockGetComments.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
  mockGetVideoComments.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('channel/playlist scope debounce', () => {
  it('reflects each field immediately but does not refetch until the user pauses typing', async () => {
    const { getSearch } = renderChannelPanel()
    const commentInput = await screen.findByLabelText('Comment') as HTMLInputElement
    const commenterInput = screen.getByLabelText('Commenter') as HTMLInputElement
    const videoInput = screen.getByLabelText('Video') as HTMLInputElement
    mockGetComments.mockClear()

    fireEvent.change(commentInput, { target: { value: 'c' } })
    fireEvent.change(commentInput, { target: { value: 'co' } })

    expect(commentInput.value).toBe('co')
    expect(getSearch()).toBe('?tab=comments')
    expect(mockGetComments).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(new URLSearchParams(getSearch()).get('comments_text')).toBe('co')
    expect(mockGetComments).toHaveBeenCalled()

    fireEvent.change(commenterInput, { target: { value: 'a' } })
    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(new URLSearchParams(getSearch()).get('comments_author')).toBe('a')

    fireEvent.change(videoInput, { target: { value: 'v' } })
    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    const params = new URLSearchParams(getSearch())
    expect(params.get('comments_text')).toBe('co')
    expect(params.get('comments_author')).toBe('a')
    expect(params.get('comments_video_title')).toBe('v')
    const lastCall = mockGetComments.mock.calls.at(-1)![0]
    expect(lastCall).toMatchObject({ text: 'co', author: 'a', videoTitle: 'v' })
  })

  it('shares one timer across all three fields: a keystroke in any field restarts the single pending commit', async () => {
    const { getSearch } = renderChannelPanel()
    const commentInput = await screen.findByLabelText('Comment')
    const commenterInput = screen.getByLabelText('Commenter')
    const videoInput = screen.getByLabelText('Video')
    mockGetComments.mockClear()

    fireEvent.change(commentInput, { target: { value: 'co' } })
    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50) })
    fireEvent.change(commenterInput, { target: { value: 'a' } })
    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50) })
    fireEvent.change(videoInput, { target: { value: 'v' } })

    // Neither of the first two keystrokes should have committed on its own timer.
    expect(new URLSearchParams(getSearch()).has('comments_text')).toBe(false)
    expect(new URLSearchParams(getSearch()).has('comments_author')).toBe(false)
    expect(mockGetComments).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    const params = new URLSearchParams(getSearch())
    expect(params.get('comments_text')).toBe('co')
    expect(params.get('comments_author')).toBe('a')
    expect(params.get('comments_video_title')).toBe('v')
    expect(mockGetComments).toHaveBeenCalledTimes(1)
    expect(mockGetComments.mock.calls[0][0]).toMatchObject({ text: 'co', author: 'a', videoTitle: 'v' })
  })

  it('deletes comments_page once a settled search commits', async () => {
    const { getSearch } = renderChannelPanel('/analytics?tab=comments&comments_page=3')
    const commentInput = await screen.findByLabelText('Comment')

    fireEvent.change(commentInput, { target: { value: 'foo' } })
    expect(new URLSearchParams(getSearch()).get('comments_page')).toBe('3')

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(new URLSearchParams(getSearch()).has('comments_page')).toBe(false)
  })

  it('preserves other comment params when one search commits', async () => {
    const { getSearch } = renderChannelPanel('/analytics?tab=comments&comments_author=kept&comments_sort_by=likes')
    const commentInput = await screen.findByLabelText('Comment')

    fireEvent.change(commentInput, { target: { value: 'foo' } })
    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    const params = new URLSearchParams(getSearch())
    expect(params.get('comments_text')).toBe('foo')
    expect(params.get('comments_author')).toBe('kept')
    expect(params.get('comments_sort_by')).toBe('likes')
  })
})

describe('video scope', () => {
  it('debounces Comment and Commenter but has no Video search field', async () => {
    const { getSearch } = renderVideoPanel()
    const commentInput = await screen.findByLabelText('Comment') as HTMLInputElement
    expect(screen.getByLabelText('Commenter')).toBeDefined()
    expect(screen.queryByLabelText('Video')).toBeNull()

    fireEvent.change(commentInput, { target: { value: 'foo' } })
    expect(new URLSearchParams(getSearch()).has('comments_text')).toBe(false)

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(new URLSearchParams(getSearch()).get('comments_text')).toBe('foo')
    expect(mockGetVideoComments).toHaveBeenCalled()
  })
})
