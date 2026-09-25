// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import type { SyncStatusResponse } from '@/types'
import SyncStatusBanner from '@/components/SyncStatusBanner'

afterEach(() => cleanup())

function renderBanner(status: SyncStatusResponse | null, unavailable = false) {
  let view: ReturnType<typeof render>
  act(() => {
    view = render(<SyncStatusBanner status={status} unavailable={unavailable} />)
  })
  return view!
}

function getCards(container: HTMLElement) {
  return container.querySelectorAll('.sync-status-card')
}

const emptyStatus: SyncStatusResponse = { active: false, stop_requested: false, stages: [] }

describe('the strip is its own fixed-size container, sized the same whether empty or full', () => {
  it('shows a centered, greyed "No sync in progress" message before the first status response', () => {
    const { container, getByText } = renderBanner(null)
    expect(container.querySelector('.sync-status-banner-shell')).not.toBeNull()
    expect(getCards(container)).toHaveLength(0)
    expect(getByText('No sync in progress').className).toContain('sync-status-banner-empty')
  })

  it('shows the same "No sync in progress" message when nothing is running, failed, or freshly succeeded', () => {
    const { container, getByText } = renderBanner(emptyStatus)
    expect(container.querySelector('.sync-status-banner-shell')).not.toBeNull()
    expect(getCards(container)).toHaveLength(0)
    expect(getByText('No sync in progress')).toBeDefined()
  })

  it('renders the unavailable case the same way as the empty state, not as a card', () => {
    const { container, getByText } = renderBanner(null, true)
    expect(getByText('Status unavailable').className).toContain('sync-status-banner-empty')
    expect(getCards(container)).toHaveLength(0)
  })
})

describe('each stage is a square card; full text lives in its tooltip', () => {
  it('shows a failed and a running stage as separate cards with their own treatments', () => {
    const { getByText, container } = renderBanner({
      active: true,
      stop_requested: false,
      stages: [
        { key: 'video_analytics', state: 'failed', message: 'syncing video analytics failed' },
        { key: 'search_insights', state: 'running', message: 'Syncing search insights (1/5)...' },
      ],
    })

    const failedCard = getByText(/Video Analytics Failed/).closest('.sync-status-card')
    expect(failedCard).not.toBeNull()
    expect(failedCard?.className).toContain('failed')
    expect(failedCard?.getAttribute('title')).toBe('syncing video analytics failed')

    const runningCard = getByText(/Syncing Search Insights/).closest('.sync-status-card')
    expect(runningCard).not.toBeNull()
    expect(runningCard?.className).toContain('syncing')
    expect(runningCard?.getAttribute('title')).toBe('Syncing search insights (1/5)...')
    // The dot sits below the "Syncing <stage>" text, not the other way around.
    expect(runningCard?.firstElementChild?.textContent).toBe('Syncing Search Insights')
    expect(runningCard?.lastElementChild?.className).toContain('sync-status-card-dot')

    expect(getCards(container)).toHaveLength(2)
  })

  it('shows a successfully finished stage, labelled by name', () => {
    const { getByText } = renderBanner({
      active: false,
      stop_requested: false,
      stages: [{ key: 'playlists', state: 'success', message: '' }],
    })
    const card = getByText(/Playlists Synced/).closest('.sync-status-card')
    expect(card?.className).toContain('success')
  })

  it('never renders a pending (not-yet-started) stage', () => {
    const { container, queryByText } = renderBanner({
      active: true,
      stop_requested: false,
      stages: [
        { key: 'videos', state: 'running', message: 'Syncing videos...' },
        { key: 'comments', state: 'pending', message: '' },
      ],
    })
    expect(getCards(container)).toHaveLength(1)
    expect(queryByText('Comments')).toBeNull()
  })

  it('never renders a cancelled stage — the user already knows, they requested the stop', () => {
    const { container, queryByText } = renderBanner({
      active: false,
      stop_requested: true,
      stages: [
        { key: 'playlists', state: 'success', message: '' },
        { key: 'videos', state: 'cancelled', message: '' },
      ],
    })
    expect(getCards(container)).toHaveLength(1)
    expect(queryByText('Videos')).toBeNull()
  })

  it('never renders a separate stopping/stop-requested advisory card', () => {
    const { container, queryByText } = renderBanner({
      active: true,
      stop_requested: true,
      stages: [{ key: 'videos', state: 'running', message: 'Syncing videos...' }],
    })
    expect(getCards(container)).toHaveLength(1)
    expect(queryByText(/[Ss]top/)).toBeNull()
  })
})
