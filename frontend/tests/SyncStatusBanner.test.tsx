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

const emptyStatus: SyncStatusResponse = { active: false, stop_requested: false, stages: [] }

describe('the banner shows only what the user could not otherwise know', () => {
  it('renders nothing before the first status response', () => {
    expect(renderBanner(null).container.firstChild).toBeNull()
  })

  it('renders the unavailable case', () => {
    expect(renderBanner(null, true).getByText('Status unavailable')).toBeDefined()
  })

  it('renders nothing when nothing is running, failed, or freshly succeeded', () => {
    expect(renderBanner(emptyStatus).container.firstChild).toBeNull()
  })

  it('shows a failed and a running stage with their own treatments', () => {
    const { getByText, container } = renderBanner({
      active: true,
      stop_requested: false,
      stages: [
        { key: 'video_analytics', state: 'failed', message: 'syncing video analytics failed' },
        { key: 'search_insights', state: 'running', message: 'Syncing search insights (1/5)...' },
      ],
    })
    expect(getByText('syncing video analytics failed').closest('.failed')).not.toBeNull()
    expect(getByText('Syncing search insights (1/5)...').closest('.syncing')).not.toBeNull()
    expect(container.querySelectorAll('.sync-status-banner-row')).toHaveLength(2)
  })

  it('shows a successfully finished stage, labelled by name', () => {
    const { getByText } = renderBanner({
      active: false,
      stop_requested: false,
      stages: [{ key: 'playlists', state: 'success', message: '' }],
    })
    expect(getByText('Playlists synced').className).toContain('success')
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
    expect(container.querySelectorAll('.sync-status-banner-row')).toHaveLength(1)
    expect(queryByText(/Comments/)).toBeNull()
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
    expect(getVisibleRows(container)).toHaveLength(1)
    expect(queryByText(/Videos/)).toBeNull()
  })

  it('never renders a separate stopping/stop-requested advisory row', () => {
    const { container, queryByText } = renderBanner({
      active: true,
      stop_requested: true,
      stages: [{ key: 'videos', state: 'running', message: 'Syncing videos...' }],
    })
    expect(getVisibleRows(container)).toHaveLength(1)
    expect(queryByText(/[Ss]top/)).toBeNull()
  })
})

function getVisibleRows(container: HTMLElement) {
  return container.querySelectorAll('.sync-status-banner-row')
}
