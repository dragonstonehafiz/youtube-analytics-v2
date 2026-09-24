// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import type { SyncStatusResponse } from '@/types'
import SyncStatusBanner from '@/components/SyncStatusBanner'

afterEach(() => {
  cleanup()
})

/** Renders inside `act`, so the assertion below always sees the final, settled DOM. */
function renderBanner(status: SyncStatusResponse | null, unavailable = false, stopRequested = false) {
  let view: ReturnType<typeof render>
  act(() => {
    view = render(<SyncStatusBanner status={status} unavailable={unavailable} stopRequested={stopRequested} />)
  })
  return view!
}

describe('every lifecycle state is shown, unlike the navbar', () => {
  it('renders nothing before a status has been received', () => {
    const { container } = renderBanner(null)

    expect(container.firstChild).toBeNull()
  })

  it('renders the unavailable state', () => {
    const { getByText } = renderBanner(null, true)

    expect(getByText('Status unavailable')).toBeDefined()
  })

  it('renders the idle state', () => {
    const { getByText, container } = renderBanner({ state: 'idle', message: '', stages: [] })

    expect(getByText('Not syncing')).toBeDefined()
    expect(container.querySelector('.sync-status-banner-row.syncing')).toBeNull()
  })

  it('renders the running state with its message', () => {
    const { getByText, container } = renderBanner({
      state: 'running',
      message: 'Syncing videos...',
      stages: [],
    })

    expect(getByText('Syncing videos...')).toBeDefined()
    expect(container.querySelector('.sync-status-banner-dot')).not.toBeNull()
  })

  it('renders the stopping state distinctly from running or failed', () => {
    const { getByText, container } = renderBanner({
      state: 'stopping',
      message: 'Stopping sync...',
      stages: [],
    })

    expect(getByText('Stopping sync...')).toBeDefined()
    expect(container.querySelector('.sync-status-banner-row.failed')).toBeNull()
  })

  it('shows stopping immediately after an accepted stop while the last poll still says running', () => {
    const { getByText, queryByText } = renderBanner({
      state: 'running',
      message: 'Syncing videos...',
      stages: [],
    }, false, true)

    expect(getByText('Stopping sync...')).toBeDefined()
    expect(queryByText('Syncing videos...')).toBeNull()
  })

  it('renders the failed state', () => {
    const { getByText } = renderBanner({
      state: 'failed',
      message: 'Sync failed while syncing videos',
      stages: [],
    })

    expect(getByText('Sync failed while syncing videos')).toBeDefined()
  })

  it('renders the cancelled state', () => {
    const { getByText } = renderBanner({ state: 'cancelled', message: 'Sync stopped', stages: [] })

    expect(getByText('Sync stopped')).toBeDefined()
  })

  it('renders the success state', () => {
    const { getByText } = renderBanner({ state: 'success', message: 'Sync complete', stages: [] })

    expect(getByText('Sync complete')).toBeDefined()
  })
})

describe('concurrent stages stack vertically', () => {
  it('renders one row per active stage, in a vertical stack rather than side by side', () => {
    const { getByText, container } = renderBanner({
      state: 'running',
      message: 'Syncing video analytics (1/5)...; Syncing search insights (1/5)...',
      stages: [
        { key: 'video_analytics', message: 'Syncing video analytics (1/5)...' },
        { key: 'search_insights', message: 'Syncing search insights (1/5)...' },
      ],
    })

    expect(getByText('Syncing video analytics (1/5)...')).toBeDefined()
    expect(getByText('Syncing search insights (1/5)...')).toBeDefined()
    // Each stage gets its own full-width row rather than sharing one; the vertical
    // stacking itself is CSS (`.sync-status-banner { flex-direction: column }`), not
    // provable under jsdom (see UploadStrip.test.tsx's note on the same limitation).
    const rows = container.querySelectorAll('.sync-status-banner-row.syncing')
    expect(rows).toHaveLength(2)
  })
})
