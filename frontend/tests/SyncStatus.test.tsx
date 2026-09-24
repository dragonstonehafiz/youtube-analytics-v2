// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import type { SyncStatusResponse } from '@/types'

vi.mock('@/api', () => ({
  getSyncStatus: vi.fn(),
}))

import { getSyncStatus } from '@/api'
import SyncStatus from '@/components/SyncStatus'

const mockGetSyncStatus = vi.mocked(getSyncStatus)

function renderStatus() {
  return render(<SyncStatus />)
}

/**
 * Resolves the poll with `response` inside `act`, so the component's state update and
 * re-render are guaranteed to have happened before this returns — unlike awaiting only
 * `toHaveBeenCalled()`, which observes the call but not its effect on the DOM, and would
 * let a "renders nothing" assertion pass on pure luck (the pre-resolution render is also
 * empty) even if the resolved state incorrectly rendered a pill.
 */
async function renderResolved(response: SyncStatusResponse) {
  let resolve: (value: SyncStatusResponse) => void = () => {}
  const pending = new Promise<SyncStatusResponse>(r => { resolve = r })
  mockGetSyncStatus.mockReturnValueOnce(pending)
  const view = renderStatus()
  await waitFor(() => expect(mockGetSyncStatus).toHaveBeenCalled())
  await act(async () => {
    resolve(response)
    await pending
  })
  return view
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('lifecycle rendering', () => {
  it('renders nothing for the idle state', async () => {
    const { container } = await renderResolved({ state: 'idle', message: '', stages: [] })

    expect(container.firstChild).toBeNull()
  })

  it('renders the running state with its message and pulsing dot', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'running', message: 'Syncing videos...', stages: [] })
    const { container } = renderStatus()

    await screen.findByText('Syncing videos...')
    expect(container.querySelector('.sync-status.syncing')).not.toBeNull()
    expect(container.querySelector('.sync-status-dot')).not.toBeNull()
  })

  it('renders one pill per concurrently active stage while running', async () => {
    mockGetSyncStatus.mockResolvedValue({
      state: 'running',
      message: 'Syncing video analytics (1/5)...; Syncing search insights (1/5)...',
      stages: [
        { key: 'video_analytics', message: 'Syncing video analytics (1/5)...' },
        { key: 'search_insights', message: 'Syncing search insights (1/5)...' },
      ],
    })
    const { container } = renderStatus()

    await screen.findByText('Syncing video analytics (1/5)...')
    await screen.findByText('Syncing search insights (1/5)...')
    expect(container.querySelectorAll('.sync-status.syncing')).toHaveLength(2)
  })

  it('renders nothing for the stopping state', async () => {
    const { container } = await renderResolved({ state: 'stopping', message: 'Stopping sync...', stages: [] })

    expect(container.firstChild).toBeNull()
  })

  it('renders nothing for the cancelled state', async () => {
    const { container } = await renderResolved({ state: 'cancelled', message: 'Sync stopped', stages: [] })

    expect(container.firstChild).toBeNull()
  })

  it('renders the failed state distinctly', async () => {
    mockGetSyncStatus.mockResolvedValue({
      state: 'failed',
      message: 'Sync failed while syncing videos',
      stages: [],
    })
    const { container } = renderStatus()

    await screen.findByText('Sync failed while syncing videos')
    expect(container.querySelector('.sync-status.failed')).not.toBeNull()
  })

  it('renders nothing for the success state', async () => {
    const { container } = await renderResolved({ state: 'success', message: 'Sync complete', stages: [] })

    expect(container.firstChild).toBeNull()
  })
})

describe('status unavailability', () => {
  it('renders a fixed message when the status request fails', async () => {
    mockGetSyncStatus.mockRejectedValue(new Error('down'))
    renderStatus()

    await waitFor(() => expect(screen.getByText('Status unavailable')).toBeDefined())
  })

  it('renders nothing before the first poll resolves', () => {
    mockGetSyncStatus.mockReturnValue(new Promise(() => {}))
    const { container } = renderStatus()

    expect(container.firstChild).toBeNull()
  })
})
