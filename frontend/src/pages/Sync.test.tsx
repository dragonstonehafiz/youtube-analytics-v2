// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type {
  SyncRun,
  SyncRunBatch,
  SyncRunStatus,
  SyncRunsResponse,
  SyncStatusResponse,
} from '@/types'

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

/** Raw values that must never reach the DOM through any history cell. */
const SECRET_ERROR = 'TRACEBACK-SENTINEL-do-not-render'
const SECRET_BATCH_ID = 'BATCH-SENTINEL-0d4f-1234'

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

/** Build a batch whose rollups are summed from its children, as the backend does. */
function batch(runs: SyncRun[] = [run()], overrides: Partial<SyncRunBatch> = {}): SyncRunBatch {
  const batchId = overrides.batch_id ?? runs[0]?.batch_id ?? 'batch-1'
  return {
    batch_id: batchId,
    started_at: runs.map(r => r.started_at).sort()[0] ?? '2024-05-02T10:00:00+00:00',
    run_count: runs.length,
    rows_fetched: runs.reduce((sum, r) => sum + r.rows_fetched, 0),
    rows_written: runs.reduce((sum, r) => sum + r.rows_written, 0),
    rows_deleted: runs.reduce((sum, r) => sum + r.rows_deleted, 0),
    runs,
    ...overrides,
  }
}

function page(items: SyncRunBatch[], total = items.length, pageNumber = 1): SyncRunsResponse {
  return { items, total, page: pageNumber, page_size: 25 }
}

/** Format an expected timestamp the same way the component does, so locale never matters. */
function localTime(iso: string): string {
  return new Date(iso).toLocaleString()
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

const parentTable = () => screen.getAllByRole('table')[0]
const nestedTable = () => screen.getAllByRole('table')[1]
const disclosures = () => screen.getAllByRole('button', { name: /^Sync batch started/ })

beforeEach(() => {
  mockGetSyncStatus.mockResolvedValue({ state: 'idle', message: '' } as SyncStatusResponse)
  mockGetDateRange.mockResolvedValue({ earliest_year: 2022 })
  mockGetSyncRuns.mockResolvedValue(page([batch()]))
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

    await waitFor(() => expect(screen.getByRole('columnheader', { name: 'Started' })).toBeDefined())
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
    mockGetSyncRuns.mockResolvedValue(page([batch()], 60, 3))
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
    mockGetSyncRuns.mockResolvedValue(page([batch()], 60, 2))
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

  it('reports genuinely empty history when the total is zero', async () => {
    mockGetSyncRuns.mockResolvedValue(page([], 0))
    renderSync('/sync?tab=history')

    expect(await screen.findByText('No sync runs recorded.')).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull()
  })

  it('distinguishes an out-of-range page from empty history', async () => {
    mockGetSyncRuns.mockResolvedValue(page([], 60, 9))
    renderSync('/sync?tab=history&history_page=9')

    expect(await screen.findByText('No sync batches found on this page.')).toBeDefined()
    expect(screen.queryByText('No sync runs recorded.')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull()
  })
})

describe('parent batch rows', () => {
  it('renders the six parent columns in order', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(within(parentTable()).getAllByRole('columnheader').map(h => h.textContent)).toEqual([
      'Started', 'Status', 'Stages', 'Fetched', 'Written', 'Deleted',
    ])
  })

  it('shows the batch earliest start time, stage count, and API rollups', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([
        run({ id: 2, sync_type: 'comments', started_at: '2024-05-01T10:05:00+00:00',
              rows_fetched: 7, rows_written: 3, rows_deleted: 0 }),
        run({ id: 1, sync_type: 'videos', started_at: '2024-05-01T10:00:00+00:00',
              rows_fetched: 10, rows_written: 5, rows_deleted: 1 }),
      ]),
    ]))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    const cells = within(parentTable()).getAllByRole('cell').map(c => c.textContent)
    expect(cells[0]).toBe(localTime('2024-05-01T10:00:00+00:00'))
    expect(cells[1]).toBe('Success')
    expect(cells[2]).toBe('2')
    expect(cells[3]).toBe((17).toLocaleString())
    expect(cells[4]).toBe((8).toLocaleString())
    expect(cells[5]).toBe((1).toLocaleString())
  })

  it('keeps two batches from the same date as separate rows', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ id: 2, batch_id: 'batch-pm', started_at: '2024-05-01T18:00:00+00:00' })]),
      batch([run({ id: 1, batch_id: 'batch-am', started_at: '2024-05-01T09:00:00+00:00' })]),
    ], 2))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    const buttons = disclosures()
    expect(buttons).toHaveLength(2)
    expect(buttons[0].textContent).toBe(localTime('2024-05-01T18:00:00+00:00'))
    expect(buttons[1].textContent).toBe(localTime('2024-05-01T09:00:00+00:00'))
  })

  it('preserves the newest-first batch order the API returned', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ id: 2, batch_id: 'batch-b', started_at: '2024-05-03T10:00:00+00:00' })]),
      batch([run({ id: 1, batch_id: 'batch-a', started_at: '2024-05-01T10:00:00+00:00' })]),
    ], 2))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(disclosures().map(b => b.textContent)).toEqual([
      localTime('2024-05-03T10:00:00+00:00'),
      localTime('2024-05-01T10:00:00+00:00'),
    ])
  })

  it('does not render the raw batch id', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ batch_id: SECRET_BATCH_ID })]),
    ]))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(document.body.textContent).not.toContain(SECRET_BATCH_ID)
    expect(disclosures()[0].getAttribute('aria-label')).not.toContain(SECRET_BATCH_ID)
  })

})

describe('status reporting', () => {
  const stage = (id: number, overrides: Partial<SyncRun>) =>
    run({ id, started_at: `2024-05-01T10:0${id}:00+00:00`, ...overrides })

  const renderStatuses = async (runs: SyncRun[]) => {
    mockGetSyncRuns.mockResolvedValue(page([batch(runs)]))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')
  }

  const parentStatus = () => within(parentTable()).getAllByRole('cell')[1].textContent

  it('reports a stage still marked running with no completion as Incomplete', async () => {
    await renderStatuses([stage(1, { status: 'running', completed_at: null })])
    fireEvent.click(disclosures()[0])

    expect(within(nestedTable()).getAllByRole('cell')[2].textContent).toBe('Incomplete')
    expect(document.body.textContent).not.toContain('Running')
  })

  it('still reports Running when a running stage carries a completion time', async () => {
    await renderStatuses([
      stage(1, { status: 'running', completed_at: '2024-05-01T10:05:00+00:00' }),
    ])
    fireEvent.click(disclosures()[0])

    expect(within(nestedTable()).getAllByRole('cell')[2].textContent).toBe('Running')
  })

  it('rolls an all-success batch up to Success', async () => {
    await renderStatuses([stage(1, {}), stage(2, {})])

    expect(parentStatus()).toBe('Success')
  })

  it('rolls a batch containing an interrupted stage up to Incomplete', async () => {
    await renderStatuses([
      stage(1, {}),
      stage(2, { status: 'running', completed_at: null }),
    ])

    expect(parentStatus()).toBe('Incomplete')
  })

  it('lets a failed stage outrank an interrupted one', async () => {
    await renderStatuses([
      stage(1, {}),
      stage(2, { status: 'running', completed_at: null }),
      stage(3, { status: 'failed', error_message: SECRET_ERROR }),
    ])

    expect(parentStatus()).toBe('Failed')
    expect(document.body.textContent).not.toContain(SECRET_ERROR)
  })

  it('gives the parent status the same styling hook as a stage status', async () => {
    await renderStatuses([stage(1, {})])

    const badge = within(parentTable()).getAllByRole('cell')[1].firstElementChild
    expect(badge?.className).toContain('sync-history-status-success')
  })
})

describe('batch disclosure', () => {
  it('starts collapsed with no detail table', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(screen.getAllByRole('table')).toHaveLength(1)
    expect(disclosures()[0].getAttribute('aria-expanded')).toBe('false')
  })

  it('expands on a disclosure button click exactly once', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    fireEvent.click(disclosures()[0])

    // A double toggle from the click also reaching the row handler would leave this collapsed.
    expect(screen.getAllByRole('table')).toHaveLength(2)
    expect(disclosures()[0].getAttribute('aria-expanded')).toBe('true')
  })

  it('collapses again on a second disclosure click', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    fireEvent.click(disclosures()[0])
    fireEvent.click(disclosures()[0])

    expect(screen.getAllByRole('table')).toHaveLength(1)
    expect(disclosures()[0].getAttribute('aria-expanded')).toBe('false')
  })

  it('expands when the parent row itself is clicked', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    const parentRow = within(parentTable()).getAllByRole('row')[1]
    fireEvent.click(parentRow)

    expect(screen.getAllByRole('table')).toHaveLength(2)
    expect(disclosures()[0].getAttribute('aria-expanded')).toBe('true')
  })

  it('points aria-controls at the detail container it reveals', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    fireEvent.click(disclosures()[0])

    const controls = disclosures()[0].getAttribute('aria-controls')
    expect(controls).toBeTruthy()
    expect(document.getElementById(controls as string)).not.toBeNull()
  })

  it('keeps several batches open independently', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ id: 3, batch_id: 'batch-c', started_at: '2024-05-03T10:00:00+00:00' })]),
      batch([run({ id: 2, batch_id: 'batch-b', started_at: '2024-05-02T10:00:00+00:00' })]),
      batch([run({ id: 1, batch_id: 'batch-a', started_at: '2024-05-01T10:00:00+00:00' })]),
    ], 3))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    fireEvent.click(disclosures()[0])
    fireEvent.click(disclosures()[2])

    expect(disclosures().map(b => b.getAttribute('aria-expanded')))
      .toEqual(['true', 'false', 'true'])
    expect(screen.getAllByRole('table')).toHaveLength(3)
  })

  it('does not collapse the parent when the expanded detail is clicked', async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')
    fireEvent.click(disclosures()[0])

    fireEvent.click(within(nestedTable()).getAllByRole('row')[1])

    expect(screen.getAllByRole('table')).toHaveLength(2)
    expect(disclosures()[0].getAttribute('aria-expanded')).toBe('true')
  })

  it('clears expansion after moving to another page', async () => {
    mockGetSyncRuns.mockResolvedValue(page([batch()], 60, 1))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')
    fireEvent.click(disclosures()[0])
    expect(screen.getAllByRole('table')).toHaveLength(2)

    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ id: 9, batch_id: 'batch-page-2' })]),
    ], 60, 2))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenLastCalledWith(2, 25))
    await waitFor(() => expect(screen.getAllByRole('table')).toHaveLength(1))
    expect(disclosures()[0].getAttribute('aria-expanded')).toBe('false')
  })
})

describe('expanded stage details', () => {
  const expandFirst = async () => {
    renderSync('/sync?tab=history')
    await screen.findByRole('table')
    fireEvent.click(disclosures()[0])
  }

  it('renders the eight stage columns in order', async () => {
    await expandFirst()

    expect(within(nestedTable()).getAllByRole('columnheader').map(h => h.textContent)).toEqual([
      'Stage', 'Scope', 'Status', 'Started', 'Completed', 'Fetched', 'Written', 'Deleted',
    ])
  })

  it('renders each child stage in the response order', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([
        run({ id: 3, sync_type: 'comments', started_at: '2024-05-01T10:02:00+00:00' }),
        run({ id: 2, sync_type: 'videos', started_at: '2024-05-01T10:01:00+00:00' }),
        run({ id: 1, sync_type: 'playlists', started_at: '2024-05-01T10:00:00+00:00' }),
      ]),
    ]))
    await expandFirst()

    const rows = within(nestedTable()).getAllByRole('row').slice(1)
    expect(rows.map(r => within(r).getAllByRole('cell')[0].textContent))
      .toEqual(['Comments', 'Videos', 'Playlists'])
  })

  it('renders the actual per-stage counters, not the rollups', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([
        run({ id: 2, sync_type: 'comments', rows_fetched: 7, rows_written: 3, rows_deleted: 0 }),
        run({ id: 1, sync_type: 'videos', rows_fetched: 10, rows_written: 5, rows_deleted: 1 }),
      ]),
    ]))
    await expandFirst()

    const rows = within(nestedTable()).getAllByRole('row').slice(1)
    expect(within(rows[0]).getAllByRole('cell')[5].textContent).toBe((7).toLocaleString())
    expect(within(rows[1]).getAllByRole('cell')[5].textContent).toBe((10).toLocaleString())
  })

  it('labels a year scope, the two non-year scopes, and an unknown stage', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([
        run({ id: 3, sync_type: 'video_analytics', scope: 'year', year: 2024,
              started_at: '2024-05-01T10:02:00+00:00' }),
        run({ id: 2, sync_type: 'comments', scope: 'all',
              started_at: '2024-05-01T10:01:00+00:00' }),
        run({ id: 1, sync_type: 'chapters', scope: 'incremental',
              started_at: '2024-05-01T10:00:00+00:00' }),
      ]),
    ]))
    await expandFirst()

    const rows = within(nestedTable()).getAllByRole('row').slice(1)
    expect(within(rows[0]).getAllByRole('cell')[0].textContent).toBe('Video Analytics')
    expect(within(rows[0]).getAllByRole('cell')[1].textContent).toBe('2024')
    expect(within(rows[1]).getAllByRole('cell')[1].textContent).toBe('All')
    expect(within(rows[2]).getAllByRole('cell')[0].textContent).toBe('chapters')
    expect(within(rows[2]).getAllByRole('cell')[1].textContent).toBe('Incremental')
  })

  it('renders an em dash for an interrupted stage with no completion time', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ status: 'running', completed_at: null })]),
    ]))
    await expandFirst()

    const cells = within(nestedTable()).getAllByRole('cell')
    expect(cells[2].textContent).toBe('Incomplete')
    expect(cells[4].textContent).toBe('—')
  })

  it('renders a success stage with its formatted timestamps', async () => {
    await expandFirst()

    const cells = within(nestedTable()).getAllByRole('cell')
    expect(cells[2].textContent).toBe('Success')
    expect(cells[3].textContent).toBe(localTime('2024-05-02T10:00:00+00:00'))
    expect(cells[4].textContent).toBe(localTime('2024-05-02T10:05:00+00:00'))
  })

  it('never renders a failed stage\'s stored error message', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ status: 'failed', error_message: SECRET_ERROR, completed_at: null })]),
    ]))
    await expandFirst()

    expect(within(nestedTable()).getAllByRole('cell')[2].textContent).toBe('Failed')
    expect(document.body.textContent).not.toContain(SECRET_ERROR)
  })

  it('does not render internal identifiers in the expanded detail', async () => {
    mockGetSyncRuns.mockResolvedValue(page([
      batch([run({ batch_id: SECRET_BATCH_ID })]),
    ]))
    await expandFirst()

    expect(document.body.textContent).not.toContain(SECRET_BATCH_ID)
  })
})

describe('history pagination', () => {
  const sixtyBatchesPage = (pageNumber: number) =>
    page([batch([run({ id: pageNumber, batch_id: `batch-${pageNumber}` })])], 60, pageNumber)

  it('disables Previous on the first page', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyBatchesPage(1))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Previous' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', false)
    expect(screen.getByText('Page 1 of 3')).toBeDefined()
  })

  it('enables both controls on a middle page', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyBatchesPage(2))
    renderSync('/sync?tab=history&history_page=2')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Previous' })).toHaveProperty('disabled', false)
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', false)
    expect(screen.getByText('Page 2 of 3')).toBeDefined()
  })

  it('disables Next on the last page', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyBatchesPage(3))
    renderSync('/sync?tab=history&history_page=3')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', true)
    expect(screen.getByText('Page 3 of 3')).toBeDefined()
  })

  it('paginates by batch count, not stage count', async () => {
    const sevenStages = Array.from({ length: 7 }, (_, i) =>
      run({ id: i + 1, sync_type: 'videos', started_at: `2024-05-01T10:0${i}:00+00:00` }))
    mockGetSyncRuns.mockResolvedValue(page([batch(sevenStages)], 30, 1))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    // 30 batches at 25 per page is 2 pages, regardless of how many stages each holds.
    expect(screen.getByText('Page 1 of 2')).toBeDefined()
    expect(disclosures()).toHaveLength(1)
  })

  it('renders disabled controls for a single page of results', async () => {
    mockGetSyncRuns.mockResolvedValue(page([batch()], 5))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    expect(screen.getByRole('button', { name: 'Previous' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', true)
    expect(screen.getByText('Page 1 of 1')).toBeDefined()
  })

  it('requests the next page when Next is clicked', async () => {
    mockGetSyncRuns.mockResolvedValue(sixtyBatchesPage(1))
    renderSync('/sync?tab=history')
    await screen.findByRole('table')

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenLastCalledWith(2, 25))
  })

  it('ignores a superseded response so stale rows cannot replace the active page', async () => {
    let resolveFirst: (value: SyncRunsResponse) => void = () => {}
    mockGetSyncRuns
      .mockReturnValueOnce(new Promise<SyncRunsResponse>(resolve => { resolveFirst = resolve }))
      .mockResolvedValue(page([
        batch([run({ id: 2, batch_id: 'batch-fresh', started_at: '2024-05-09T10:00:00+00:00' })]),
      ], 60, 2))

    renderSync('/sync?tab=history')
    await waitFor(() => expect(mockGetSyncRuns).toHaveBeenCalledWith(1, 25))

    fireEvent.click(screen.getByRole('button', { name: 'Sync' }))
    await settled()
    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    await screen.findByRole('table')

    resolveFirst(page([
      batch([run({ id: 1, batch_id: 'batch-stale', started_at: '2024-05-01T10:00:00+00:00' })]),
    ], 60, 1))

    await waitFor(() =>
      expect(disclosures()[0].textContent).toBe(localTime('2024-05-09T10:00:00+00:00')))
    expect(document.body.textContent).not.toContain(localTime('2024-05-01T10:00:00+00:00'))
  })
})
