// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { TopVideo, Video } from '@/types'

vi.mock('@/api', () => ({
  getTopVideosByViews: vi.fn(),
  getVideos: vi.fn(),
  getChannelTrafficSources: vi.fn(),
  getSearchTerms: vi.fn(),
  getVideosBySearchTerm: vi.fn(),
}))

import { getChannelTrafficSources, getTopVideosByViews, getVideos, getSearchTerms, getVideosBySearchTerm } from '@/api'
import Home from '@/pages/Home'

const mockGetTopVideosByViews = vi.mocked(getTopVideosByViews)
const mockGetVideos = vi.mocked(getVideos)
const mockGetChannelTrafficSources = vi.mocked(getChannelTrafficSources)
const mockGetSearchTerms = vi.mocked(getSearchTerms)
const mockGetVideosBySearchTerm = vi.mocked(getVideosBySearchTerm)

/** The five cards whose own request drives their loading indicator directly. */
const CARD_HEADINGS = [
  'Top Videos (Last 28 Days)',
  'Top Shorts (Last 28 Days)',
  'Latest Uploads',
  'Traffic Sources (Last 28 Days)',
  'Top Search Terms (Last 28 Days)',
] as const

/** This card's own request never starts until a default term exists, so before the term
 * list resolves it renders its empty state rather than a loading indicator. */
const VIDEO_BY_TERM_HEADING = 'Top Videos by Search Term (Last 28 Days)'

function topVideo(overrides: Partial<TopVideo> = {}): TopVideo {
  return {
    id: 'video-1',
    title: 'A resolved video',
    published_at: '2024-05-01T00:00:00+00:00',
    thumbnail_url: null,
    content_type: 'video',
    period_views: 4321,
    period_watch_time_hours: 12,
    period_earnings_sgd: 3.5,
    ...overrides,
  }
}

function video(overrides: Partial<Video> = {}): Video {
  return {
    id: 'video-9',
    title: 'A recent upload',
    published_at: '2024-05-04T00:00:00+00:00',
    thumbnail_url: null,
    content_type: 'video',
    view_count: 10,
    like_count: 1,
    comment_count: 0,
    duration_seconds: 90,
    description: null,
    privacy_status: 'public',
    total_watch_time_hours: 2,
    total_revenue_sgd: 1,
    ...overrides,
  } as Video
}

/** A promise plus the handle that settles it, so a test controls exactly when it lands. */
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => {}
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

function renderHome() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Home />
    </MemoryRouter>,
  )
}

/** The stable shell owning one titled card. */
function cardFor(heading: string): HTMLElement {
  const shell = screen.getByText(heading).closest('.async-card')
  if (!shell) throw new Error(`No card shell for ${heading}`)
  return shell as HTMLElement
}

beforeEach(() => {
  mockGetTopVideosByViews.mockReturnValue(new Promise(() => {}))
  mockGetVideos.mockReturnValue(new Promise(() => {}))
  mockGetChannelTrafficSources.mockReturnValue(new Promise(() => {}))
  mockGetSearchTerms.mockReturnValue(new Promise(() => {}))
  mockGetVideosBySearchTerm.mockReturnValue(new Promise(() => {}))
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('dashboard card shells', () => {
  it('renders every data card shell and indicator before any request resolves', () => {
    const { container } = renderHome()

    expect(container.querySelectorAll('.async-card')).toHaveLength(CARD_HEADINGS.length + 1)
    for (const heading of CARD_HEADINGS) {
      expect(within(cardFor(heading)).getByRole('status')).toBeDefined()
    }
    // No default term exists yet (the term list is still loading), so this card shows its
    // empty state rather than a spinner — it never issued its own request to be pending on.
    expect(within(cardFor(VIDEO_BY_TERM_HEADING)).getByText('No videos for this term')).toBeDefined()
  })

  it('leaves the static navigation cards out of the loading surfaces', () => {
    const { container } = renderHome()

    expect(container.querySelectorAll('.home-nav-card')).toHaveLength(3)
    for (const label of ['Videos', 'Playlists', 'Analytics']) {
      expect(screen.getByText(label).closest('.async-card')).toBeNull()
    }
  })
})

describe('independent resolution', () => {
  it('populates one card while the others are still loading', async () => {
    const top = deferred<{ items: TopVideo[] }>()
    mockGetTopVideosByViews
      .mockReturnValueOnce(top.promise)
      .mockReturnValue(new Promise(() => {}))
    renderHome()
    const shell = cardFor('Top Videos (Last 28 Days)')

    top.resolve({ items: [topVideo({ title: 'The resolved top video' })] })

    await waitFor(() => expect(within(shell).getByText('The resolved top video')).toBeDefined())
    // The same shell carried both states.
    expect(cardFor('Top Videos (Last 28 Days)')).toBe(shell)
    expect(within(shell).queryByRole('status')).toBeNull()
    for (const heading of ['Top Shorts (Last 28 Days)', 'Latest Uploads', 'Traffic Sources (Last 28 Days)', 'Top Search Terms (Last 28 Days)']) {
      expect(within(cardFor(heading)).getByRole('status')).toBeDefined()
    }
  })

  it('resolves the recent uploads card without waiting for the top-video requests', async () => {
    const recent = deferred<{ items: Video[] }>()
    mockGetVideos.mockReturnValue(recent.promise)
    renderHome()

    recent.resolve({ items: [video({ title: 'The newest upload' })] })

    await waitFor(() =>
      expect(within(cardFor('Latest Uploads')).getByText('The newest upload')).toBeDefined())
    expect(within(cardFor('Top Videos (Last 28 Days)')).getByRole('status')).toBeDefined()
  })
})

describe('top videos by search term', () => {
  it('defaults to the top term and pools videos and shorts together, with no content_type filter', async () => {
    mockGetSearchTerms.mockResolvedValue({ items: [{ search_term: 'cats', views: 10 }] })
    mockGetVideosBySearchTerm.mockResolvedValue({
      items: [
        { id: 'v-1', title: 'A cat video', thumbnail_url: null, content_type: 'video', views: 7 },
        { id: 'v-2', title: 'A cat short', thumbnail_url: null, content_type: 'short', views: 3 },
      ],
    })
    renderHome()

    await waitFor(() => expect(mockGetVideosBySearchTerm).toHaveBeenCalled())
    const [term, query] = mockGetVideosBySearchTerm.mock.calls[0]
    expect(term).toBe('cats')
    expect(query).not.toHaveProperty('contentType')

    const shell = cardFor(VIDEO_BY_TERM_HEADING)
    await waitFor(() => expect(within(shell).getByText('A cat video')).toBeDefined())
    expect(within(shell).getByText('A cat short')).toBeDefined()
  })
})

describe('resolved empty and failed requests', () => {
  it('shows an empty message only once a request has finished', async () => {
    const top = deferred<{ items: TopVideo[] }>()
    mockGetTopVideosByViews
      .mockReturnValueOnce(top.promise)
      .mockReturnValue(new Promise(() => {}))
    renderHome()
    expect(within(cardFor('Top Videos (Last 28 Days)')).queryByText('No videos for this period')).toBeNull()

    top.resolve({ items: [] })

    await waitFor(() =>
      expect(within(cardFor('Top Videos (Last 28 Days)')).getByText('No videos for this period')).toBeDefined())
  })

  it('keeps a failed card inside its own shell', async () => {
    mockGetChannelTrafficSources.mockRejectedValue(new Error('Traffic request failed (500)'))
    renderHome()

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('Traffic request failed (500)')
    expect(alert.closest('.async-card')).toBe(cardFor('Traffic Sources (Last 28 Days)'))
    expect(within(cardFor('Top Videos (Last 28 Days)')).getByRole('status')).toBeDefined()
  })
})
