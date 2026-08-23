// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { SyncRun, SyncRunStatus, SyncRunsResponse, SyncStatusResponse } from '@/types'

vi.mock('@/api', () => ({
  getSyncStatus: vi.fn(),
  triggerSync: vi.fn(),
  getDateRange: vi.fn(),
  getSyncRuns: vi.fn(),
}))

import { getDateRange, getSyncRuns, getSyncStatus, triggerSync } from '@/api'
import Sync from './Sync'

const mockGetSyncStatus = vi.mocked(getSyncStatus)
const mockGetSyncRuns = vi.mocked(getSyncRuns)
const mockTriggerSync = vi.mocked(triggerSync)
const mockGetDateRange = vi.mocked(getDateRange)

/** A raw error string that must never reach the DOM through any history cell. */
const SECRET_ERROR = 'TRACEBACK-SENTINEL-do-not-render'

function run(overrides: Partial<SyncRun> = {}): SyncRun {
  return {
    id: 1,
    batch_id: 'batch-1',
    sync_type: 'videos',
    scope: 'incremental',
    year: null,
    status: 'success' as SyncRunStatus,
    started_at: '2024-05-02T10:00:00+00:00',
    completed_at: '2024-05-02T10:05:00+00:00',
    rows_fetched: 1234,
    rows_written: 100,
    rows_deleted: 0,
    error_message: null,
    ...overrides,
  }
}

function page(items: SyncRun[], total = items.length, pageNumber = 1): SyncRunsResponse {
  return { items, total, page: pageNumber, page_size: 25 }
}

function renderSync(route = '/sync') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Sync />
    </MemoryRouter>,
  )
}

/** Wait for the initial status poll and date-range fetch to settle. */
async function settled() {
  await waitFor(() => expect(mockGetSyncStatus).toHaveBeenCalled())
}

beforeEach(() => {
  mockGetSyncStatus.mockResolvedValue({ state: 'idle', message: '' } as SyncStatusResponse)
  mockGetDateRange.mockResolvedValue({ earliest_year: 2022 })
  mockGetSyncRuns.mockResolvedValue(page([run()]))
  mockTriggerSync.mockResolvedValue({ queued: true })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('tab selection and URL state', () => {
  it('defaults to the Sync tab and does not request history', async () => {
    renderSync('/sync')
    await settled()

    expect(screen.getByRole('button', { name: 'Sync selected' })).toBeDefined()
    expect(mockGetSyncRuns).not.toHaveBeenCalled()
  })

  it('selects the History tab from the URL', async () => {
    renderSync('/sync?tab=history')

    await waitFor(() => expect(screen.getByRole('columnheader', { name: 'Stage' })).toBeDefined())
    expect(screen.queryByRole('button', { name: 'Sync selected' })).toBeNull()
  })

  it('falls back to the Sync tab for an unsupported tab value', async () => {
    renderSync('/sync?tab=nonsense')
    await settled()

    expect(screen.getByRole('button', { name: 'Sync selected' })).toBeDefined()
    expect(mockGetSyncRuns).not.toHaveBeenCalled()
  })

  it('switching to History requests the first page and keeps the form out of the DOM', async () => {
    renderSync('/sync')
    await settled()

    fireEvent.click(screen.getByRole('button', { name: 'History' }))

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenCalledWith(1, 25))
    expect(screen.queryByRole('button', { name: 'Sync selected' })).toBeNull()
  })

  it('honours a non-default history page from the URL', async () => {
    mockGetSyncRuns.mockResolvedValue(page([run()], 60, 3))
    renderSync('/sync?tab=history&history_page=3')

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenCalledWith(3, 25))
  })

  it('ignores invalid history page values and requests page 1', async () => {
    renderSync('/sync?tab=history&history_page=0')

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenCalledWith(1, 25))
  })

  it('ignores a non-numeric history page value', async () => {
    renderSync('/sync?tab=history&history_page=abc')

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenCalledWith(1, 25))
  })

  it('preserves a non-default history page when switching back from Sync', async () => {
    mockGetSyncRuns.mockResolvedValue(page([run()], 60, 2))
    renderSync('/sync?tab=history&history_page=2')
    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenCalledWith(2, 25))

    fireEvent.click(screen.getByRole('button', { name: 'Sync' }))
    await settled()
    fireEvent.click(screen.getByRole('button', { name: 'History' }))

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenLastCalledWith(2, 25))
  })
})

describe('lifecycle feedback stays out of the page', () => {
  it('renders no page-level text while the first status is pending', async () => {
    mockGetSyncStatus.mockReturnValue(new Promise(() => {}))
    renderSync('/sync')

    expect(screen.queryByText('Checking sync status...')).toBeNull()
    expect(screen.queryByText('Waiting for status...')).toBeNull()
  })

  it('renders no banner and keeps the button copy fixed when status is unavailable', async () => {
    mockGetSyncStatus.mockRejectedValue(new Error('down'))
    renderSync('/sync')

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', true))
    expect(screen.queryByText('Status unavailable')).toBeNull()
  })

  it('keeps the button copy fixed while a sync is running', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'running', message: 'Syncing videos' })
    renderSync('/sync')

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', true))
    expect(screen.queryByText('Sync in progress')).toBeNull()
    expect(screen.queryByText('Syncing videos')).toBeNull()
  })

  it('reports no terminal success or failure text on the page', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'failed', message: 'Sync failed: quota' })
    renderSync('/sync')
    await settled()

    await waitFor(() => expect(screen.queryByText('Sync failed: quota')).toBeNull())
  })
})

describe('the manual form is preserved', () => {
  it('locks every stage control while a sync is running', async () => {
    mockGetSyncStatus.mockResolvedValue({ state: 'running', message: 'Syncing' })
    renderSync('/sync')

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', true))
    screen.getAllByRole('checkbox').forEach(box => expect(box).toHaveProperty('disabled', true))
  })

  it('keeps the pruning prerequisite behaviour', async () => {
    renderSync('/sync')
    await settled()

    const pruning = screen.getByRole('checkbox', { name: 'Pruning' })
    await waitFor(() => expect(pruning).toHaveProperty('disabled', false))
    fireEvent.click(pruning)

    expect(screen.getByRole('checkbox', { name: 'Playlists' })).toHaveProperty('checked', true)
    expect(screen.getByRole('checkbox', { name: 'Videos' })).toHaveProperty('checked', true)
  })

  it('disables submission when no stage is selected', async () => {
    renderSync('/sync')
    await settled()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', false))

    screen.getAllByRole('checkbox').forEach(box => {
      if ((box as HTMLInputElement).checked) fireEvent.click(box)
    })

    expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', true)
  })

  it('shows a rejected trigger next to the form', async () => {
    mockTriggerSync.mockRejectedValue(new Error('Sync already in progress'))
    renderSync('/sync')
    await settled()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', false))

    fireEvent.click(screen.getByRole('button', { name: 'Sync selected' }))

    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent', 'Sync already in progress')
  })

  it('does not surface a failed post-trigger status refresh as a form error', async () => {
    mockGetSyncStatus
      .mockResolvedValueOnce({ state: 'idle', message: '' })
      .mockRejectedValue(new Error('status down'))
    renderSync('/sync')
    await settled()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', false))

    fireEvent.click(screen.getByRole('button', { name: 'Sync selected' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', true))
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('history states', () => {
  it('renders a loading state while the page is in flight', () => {
    mockGetSyncRuns.mockReturnValue(new Promise(() => {}))
    renderSync('/sync?tab=history')

    expect(screen.getByText('Loading...')).toBeDefined()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('renders an empty state without pagination controls', async () => {
    mockGetSyncRuns.mockResolvedValue(page([], 0))
    renderSync('/sync?tab=history')

    expect(await screen.findByText('No sync runs recorded.')).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull()
  })

  it('renders a generic request error and no table', async () => {
    mockGetSyncRuns.mockRejectedValue(new Error('Sync history request failed (500)'))
    renderSync('/sync?tab=history')

    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent', 'Sync history request failed (500)')
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull()
  })

  it('leaves the form untouched when a history request fails', async () => {
    mockGetSyncRuns.mockRejectedValue(new Error('Sync history request failed (500)'))
    renderSync('/sync?tab=history')
    await screen.findByRole('alert')

    fireEvent.click(screen.getByRole('button', { name: 'Sync' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Sync selected' })).toHaveProperty('disabled', false))
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('history rows', () => {
  it('renders the eight columns in order', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(screen.getAllByRole('columnheader').map(h => h.textContent)).toEqual([
      'Stage', 'Scope', 'Status', 'Started', 'Completed', 'Fetched', 'Written', 'Deleted',
    ])
  })

  it('renders human stage, scope, status, and formatted counts', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      run({ id: 1, sync_type: 'video_analytics', scope: 'year', year: 2024, rows_fetched: 1234 }),
    ]))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    const cells = screen.getAllByRole('cell').map(c => c.textContent)
    expect(cells[0]).toBe('Video Analytics')
    expect(cells[1]).toBe('2024')
    expect(cells[2]).toBe('Success')
    expect(cells[5]).toBe((1234).toLocaleString())
  })

  it('labels the two non-year scopes', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      run({ id: 1, scope: 'incremental', started_at: '2024-05-02T10:00:00+00:00' }),
      run({ id: 2, scope: 'all', started_at: '2024-05-01T10:00:00+00:00' }),
    ], 2))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getAllByRole('cell')[1].textContent).toBe('Incremental')
    expect(within(rows[1]).getAllByRole('cell')[1].textContent).toBe('All')
  })

  it('preserves the newest-first order the API returned', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      run({ id: 2, sync_type: 'comments', started_at: '2024-05-03T10:00:00+00:00' }),
      run({ id: 1, sync_type: 'videos', started_at: '2024-05-01T10:00:00+00:00' }),
    ], 2))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getAllByRole('cell')[0].textContent).toBe('Comments')
    expect(within(rows[1]).getAllByRole('cell')[0].textContent).toBe('Videos')
  })

  it('renders an em dash for a still-running row with no completion time', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      run({ status: 'running', completed_at: null }),
    ]))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    const cells = screen.getAllByRole('cell')
    expect(cells[2].textContent).toBe('Running')
    expect(cells[4].textContent).toBe('—')
  })

  it('never renders a failed row\'s stored error message', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      run({ status: 'failed', error_message: SECRET_ERROR, completed_at: null }),
    ]))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(screen.getAllByRole('cell')[2].textContent).toBe('Failed')
    expect(document.body.textContent).not.toContain(SECRET_ERROR)
  })

  it('does not render internal identifiers', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      run({ batch_id: 'BATCH-SENTINEL-1234' }),
    ]))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(document.body.textContent).not.toContain('BATCH-SENTINEL-1234')
  })
})

describe('history pagination', () => {
  const sixtyRunsPage = (pageNumber: number) => page([run({ id: pageNumber })], 60, pageNumber)

  it('disables Previous on the first page', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyRunsPage(1))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Previous' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', false)
    expect(screen.getByText('Page 1 of 3')).toBeDefined()
  })

  it('enables both controls on a middle page', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyRunsPage(2))
    renderSync('/sync?tab=history&history_page=2')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Previous' })).toHaveProperty('disabled', false)
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', false)
    expect(screen.getByText('Page 2 of 3')).toBeDefined()
  })

  it('disables Next on the last page', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyRunsPage(3))
    renderSync('/sync?tab=history&history_page=3')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', true)
    expect(screen.getByText('Page 3 of 3')).toBeDefined()
  })

  it('renders disabled controls for a single page of results', async () => {
    mockGetSyncRuns.mockResolvedValue(page([run()], 5))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Previous' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', true)
    expect(screen.getByText('Page 1 of 1')).toBeDefined()
  })

  it('requests the next page when Next is clicked', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyRunsPage(1))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenLastCalledWith(2, 25))
  })

  it('ignores a superseded response so stale rows cannot replace the active page', async () => {
    let resolveFirst: (value: SyncRunsResponse) => void = () => {}
    mockGetSyncRuns
      .mockReturnValueOnce(new Promise<SyncRunsResponse>(resolve => { resolveFirst = resolve }))
      .mockResolvedValue(page([run({ id: 2, sync_type: 'comments' })], 60, 2))

    renderSync('/sync?tab=history')
    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenCalledWith(1, 25))

    fireEvent.click(screen.getByRole('button', { name: 'Sync' }))
    await settled()
    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    await screen.findByRole('table')

    resolveFirst(page([run({ id: 1, sync_type: 'fx_rates' })], 60, 1))

    await waitFor(() => expect(screen.getAllByRole('cell')[0].textContent).toBe('Comments'))
    expect(document.body.textContent).not.toContain('FX Rates')
  })
})
