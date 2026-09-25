// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import type { SyncStatusResponse } from '@/types'
import SyncStatusBanner from '@/components/SyncStatusBanner'

afterEach(() => cleanup())

function renderBanner(status: SyncStatusResponse | null, unavailable = false, stopRequested = false) {
  let view: ReturnType<typeof render>
  act(() => {
    view = render(<SyncStatusBanner status={status} unavailable={unavailable} stopRequested={stopRequested} />)
  })
  return view!
}

const emptyStatus: SyncStatusResponse = { active: false, stop_requested: false, stages: [] }

describe('per-stage banner rendering', () => {
  it('renders nothing before the first status response', () => {
    expect(renderBanner(null).container.firstChild).toBeNull()
  })

  it('renders unavailable and no-stage cases', () => {
    expect(renderBanner(null, true).getByText('Status unavailable')).toBeDefined()
    expect(renderBanner(emptyStatus).getByText('Not syncing')).toBeDefined()
  })

  it('shows a failed and running stage with their own treatments', () => {
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

  it('renders pending, success, and cancelled rows with stage labels', () => {
    const { getByText, container } = renderBanner({
      active: true,
      stop_requested: false,
      stages: [
        { key: 'videos', state: 'pending', message: '' },
        { key: 'playlists', state: 'success', message: '' },
        { key: 'comments', state: 'cancelled', message: '' },
      ],
    })
    expect(getByText('Waiting to sync Videos').className).toContain('pending')
    expect(getByText('Playlists synced').className).toContain('success')
    expect(getByText('Comments cancelled').className).toContain('cancelled')
    expect(container.querySelectorAll('.sync-status-banner-row')).toHaveLength(3)
  })

  it('marks stages pending after an inactive plan as not run', () => {
    expect(renderBanner({
      active: false,
      stop_requested: false,
      stages: [{ key: 'comments', state: 'pending', message: '' }],
    }).getByText('Comments not run')).toBeDefined()
  })

  it('keeps an accepted stop visible after the plan reservation ends', () => {
    const { getByText, container } = renderBanner({
      active: false,
      stop_requested: true,
      stages: [
        { key: 'playlists', state: 'success', message: '' },
        { key: 'videos', state: 'cancelled', message: '' },
      ],
    })
    expect(getByText('Stop request received').className).toContain('cancelled')
    expect(getByText('Playlists synced')).toBeDefined()
    expect(getByText('Videos cancelled')).toBeDefined()
    expect(container.querySelector('.sync-status-banner-row.stopping')).toBeNull()
  })

  it('shows stopping advisory above stage rows, preserving progress context', () => {
    const { getByText, container } = renderBanner({
      active: true,
      stop_requested: true,
      stages: [{ key: 'videos', state: 'running', message: 'Syncing videos...' }],
    })
    expect(getByText('Stopping sync...')).toBeDefined()
    expect(getByText('Syncing videos...')).toBeDefined()
    expect(container.querySelectorAll('.sync-status-banner-row')).toHaveLength(2)
  })
})
