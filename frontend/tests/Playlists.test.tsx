// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useDebouncedInput'

vi.mock('@/api', () => ({
  getPlaylists: vi.fn(),
}))

import { getPlaylists } from '@/api'
import Playlists from '@/pages/Playlists'

const mockGetPlaylists = vi.mocked(getPlaylists)

/** Exposes the current route's search string so tests can assert on it without parsing the DOM. */
function LocationProbe({ onLocation }: { onLocation: (search: string) => void }) {
  onLocation(useLocation().search)
  return null
}

function renderPlaylists(route = '/playlists') {
  let search = ''
  const utils = render(
    <MemoryRouter initialEntries={[route]}>
      <LocationProbe onLocation={s => { search = s }} />
      <Playlists />
    </MemoryRouter>,
  )
  return { ...utils, getSearch: () => search }
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockGetPlaylists.mockResolvedValue({ items: [], total: 0 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe('Playlists Title search debounce', () => {
  it('does not commit the URL or refetch until the user pauses typing', async () => {
    const { getSearch } = renderPlaylists('/playlists')
    const input = await screen.findByPlaceholderText('Search…')
    mockGetPlaylists.mockClear()

    fireEvent.change(input, { target: { value: 'f' } })
    fireEvent.change(input, { target: { value: 'fo' } })
    fireEvent.change(input, { target: { value: 'foo' } })

    expect((input as HTMLInputElement).value).toBe('foo')
    expect(getSearch()).toBe('')
    expect(mockGetPlaylists).not.toHaveBeenCalled()

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    const params = new URLSearchParams(getSearch())
    expect(params.get('title')).toBe('foo')
    expect(params.get('page')).toBe('1')
    expect(mockGetPlaylists.mock.calls.some(c => c[4] === 'foo')).toBe(true)
  })

  it('resets to page 1 only once the search commits', async () => {
    const { getSearch } = renderPlaylists('/playlists?page=2')
    const input = await screen.findByPlaceholderText('Search…')

    fireEvent.change(input, { target: { value: 'foo' } })
    expect(new URLSearchParams(getSearch()).get('page')).toBe('2')

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    const params = new URLSearchParams(getSearch())
    expect(params.get('title')).toBe('foo')
    expect(params.get('page')).toBe('1')
  })

  it('delays clearing the same way as typing, then deletes the param', async () => {
    const { getSearch } = renderPlaylists('/playlists?title=existing')
    const input = await screen.findByPlaceholderText('Search…') as HTMLInputElement
    expect(input.value).toBe('existing')

    fireEvent.change(input, { target: { value: '' } })
    expect(new URLSearchParams(getSearch()).get('title')).toBe('existing')

    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(new URLSearchParams(getSearch()).has('title')).toBe(false)
  })

  it('cancels a pending commit and restarts on newer input', async () => {
    renderPlaylists('/playlists')
    const input = await screen.findByPlaceholderText('Search…')
    mockGetPlaylists.mockClear()

    fireEvent.change(input, { target: { value: 'first' } })
    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50) })
    fireEvent.change(input, { target: { value: 'second' } })
    await act(async () => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50) })
    expect(mockGetPlaylists.mock.calls.some(c => c[4] === 'first')).toBe(false)

    await act(async () => { vi.advanceTimersByTime(50) })
    expect(mockGetPlaylists.mock.calls.some(c => c[4] === 'second')).toBe(true)
  })
})
