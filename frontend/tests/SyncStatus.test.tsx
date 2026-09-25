// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import type { SyncStatusResponse } from '@/types'

vi.mock('@/api', () => ({ getSyncStatus: vi.fn() }))

import { getSyncStatus } from '@/api'
import SyncStatus from '@/components/SyncStatus'

const mockGetSyncStatus = vi.mocked(getSyncStatus)

async function renderResolved(response: SyncStatusResponse) {
  let resolve: (value: SyncStatusResponse) => void = () => {}
  const pending = new Promise<SyncStatusResponse>(r => { resolve = r })
  mockGetSyncStatus.mockReturnValueOnce(pending)
  const view = render(<SyncStatus />)
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

describe('per-stage navbar rendering', () => {
  it('renders nothing when there are no running or failed stages', async () => {
    const { container } = await renderResolved({ active: false, stop_requested: false, stages: [] })
    expect(container.firstChild).toBeNull()
  })

  it('renders active running stages with a pulsing indicator', async () => {
    mockGetSyncStatus.mockResolvedValue({
      active: true,
      stop_requested: false,
      stages: [{ key: 'videos', state: 'running', message: 'Syncing videos...' }],
    })
    const { container } = render(<SyncStatus />)
    await screen.findByText('Syncing videos...')
    expect(container.querySelector('.sync-status.syncing')).not.toBeNull()
    expect(container.querySelector('.sync-status-dot')).not.toBeNull()
  })

  it('shows failed and running stages with distinct styling from one response', async () => {
    mockGetSyncStatus.mockResolvedValue({
      active: true,
      stop_requested: false,
      stages: [
        { key: 'video_analytics', state: 'failed', message: 'syncing video analytics failed' },
        { key: 'search_insights', state: 'running', message: 'Syncing search insights...' },
      ],
    })
    const { container } = render(<SyncStatus />)
    await screen.findByText('syncing video analytics failed')
    await screen.findByText('Syncing search insights...')
    expect(container.querySelector('.sync-status.failed')).not.toBeNull()
    expect(container.querySelector('.sync-status.syncing')).not.toBeNull()
  })

  it('keeps failures visible after the active plan ends', async () => {
    const { container } = await renderResolved({
      active: false,
      stop_requested: false,
      stages: [{ key: 'videos', state: 'failed', message: 'syncing videos failed' }],
    })
    expect(container.querySelector('.sync-status.failed')).not.toBeNull()
  })

  it('suppresses running pills after a stop request', async () => {
    const { container } = await renderResolved({
      active: true,
      stop_requested: true,
      stages: [{ key: 'videos', state: 'running', message: 'Syncing videos...' }],
    })
    expect(container.firstChild).toBeNull()
  })
})

describe('status unavailability', () => {
  it('renders a fixed message when the status request fails', async () => {
    mockGetSyncStatus.mockRejectedValue(new Error('down'))
    render(<SyncStatus />)
    await waitFor(() => expect(screen.getByText('Status unavailable')).toBeDefined())
  })
})
