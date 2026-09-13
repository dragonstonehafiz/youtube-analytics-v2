// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
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

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('lifecycle rendering', () => {
  it('renders a neutral idle state', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'idle', message: '' } as SyncStatusResponse)
    const { container } = renderStatus()

    await screen.findByText('Not syncing')
    expect(container.querySelector('.sync-status.syncing')).toBeNull()
    expect(container.querySelector('.sync-status.stopping')).toBeNull()
  })

  it('renders the running state with its message and pulsing dot', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'running', message: 'Syncing videos...' })
    const { container } = renderStatus()

    await screen.findByText('Syncing videos...')
    expect(container.querySelector('.sync-status.syncing')).not.toBeNull()
    expect(container.querySelector('.sync-status-dot')).not.toBeNull()
  })

  it('renders a distinct stopping state, never as failed', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'stopping', message: 'Stopping sync...' })
    const { container } = renderStatus()

    await screen.findByText('Stopping sync...')
    expect(container.querySelector('.sync-status.stopping')).not.toBeNull()
    expect(container.querySelector('.sync-status.failed')).toBeNull()
  })

  it('falls back to default stopping copy when no message is set', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'stopping', message: '' })
    renderStatus()

    await screen.findByText('Stopping sync...')
  })

  it('renders a distinct cancelled state, never as failed or success copy', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'cancelled', message: 'Sync stopped' })
    const { container } = renderStatus()

    await screen.findByText('Sync stopped')
    expect(container.querySelector('.sync-status.cancelled')).not.toBeNull()
    expect(container.querySelector('.sync-status.failed')).toBeNull()
    expect(screen.queryByText('Sync complete')).toBeNull()
  })

  it('falls back to default cancelled copy when no message is set', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'cancelled', message: '' })
    renderStatus()

    await screen.findByText('Sync cancelled')
  })

  it('renders the failed state distinctly from stopping and cancelled', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'failed', message: 'Sync failed while syncing videos' })
    const { container } = renderStatus()

    await screen.findByText('Sync failed while syncing videos')
    expect(container.querySelector('.sync-status.failed')).not.toBeNull()
  })

  it('renders the success state with its message', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'success', message: 'Sync complete' })
    renderStatus()

    await screen.findByText('Sync complete')
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
