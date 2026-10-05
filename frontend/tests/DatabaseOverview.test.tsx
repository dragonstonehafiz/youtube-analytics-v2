// @vitest-environment jsdom
import { cloneElement } from 'react'
import type { ComponentProps, ReactElement } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import type { DatabaseStatsResponse, DatabaseTableStats } from '@/types'

vi.mock('@/api', () => ({
  getDatabaseStats: vi.fn(),
}))

// jsdom has no layout, so give the chart a fixed size instead of measuring its container,
// and draw slices immediately instead of after the entry animation.
vi.mock('recharts', async importOriginal => {
  const actual = await importOriginal<typeof import('recharts')>()
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement<{ width?: number, height?: number }> }) =>
      cloneElement(children, { width: 200, height: 200 }),
    Pie: (props: ComponentProps<typeof actual.Pie>) => <actual.Pie {...props} isAnimationActive={false} />,
  }
})

import { getDatabaseStats } from '@/api'
import DatabaseOverview from '@/components/DatabaseOverview'

const mockGetDatabaseStats = vi.mocked(getDatabaseStats)

const GB = 1_000_000_000

function table(name: string, row_count: number, size_bytes = 1_000_000): DatabaseTableStats {
  return { name, row_count, size_bytes }
}

function stats(overrides: Partial<DatabaseStatsResponse> = {}): DatabaseStatsResponse {
  const tables = overrides.tables ?? [table('videos', 10, GB), table('comments', 2500, GB), table('fx_rates', 10, GB / 2)]
  const attributed = tables.reduce((sum, t) => sum + t.size_bytes, 0)
  const other_bytes = overrides.other_bytes ?? GB / 2
  return { tables, other_bytes, total_bytes: attributed + other_bytes, ...overrides }
}

const barRows = () => within(screen.getByRole('list', { name: 'Rows per table' })).getAllByRole('listitem')

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('DatabaseOverview', () => {
  it('shows a loading state until the request settles', () => {
    mockGetDatabaseStats.mockReturnValue(new Promise(() => {}))
    render(<DatabaseOverview />)

    expect(screen.getByRole('status')).toBeDefined()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('shows the total in GB and the rows sorted by count, ties by name', async () => {
    mockGetDatabaseStats.mockResolvedValue(stats())
    render(<DatabaseOverview />)

    await waitFor(() => expect(screen.getByText('3.000 GB')).toBeDefined())
    expect(barRows().map(row => row.textContent)).toEqual([
      `comments${(2500).toLocaleString()}`,
      'fx_rates10',
      'videos10',
    ])
  })

  it('scales bars to the largest count and gives each table its fixed slot, or Other past the eight', async () => {
    mockGetDatabaseStats.mockResolvedValue(stats())
    render(<DatabaseOverview />)

    await waitFor(() => expect(screen.getByTestId('bar-comments')).toBeDefined())
    expect(screen.getByTestId('bar-comments').getAttribute('width')).toBe('100%')
    expect(screen.getByTestId('bar-videos').getAttribute('width')).toBe('0.4%')
    expect(screen.getByTestId('bar-comments').getAttribute('class')).toBe('categorical-color-2')
    expect(screen.getByTestId('bar-videos').getAttribute('class')).toBe('categorical-color-6')
    expect(screen.getByTestId('bar-fx_rates').getAttribute('class')).toBe('categorical-color-other')
  })

  it('draws slotted tables in slot order, then one Other slice holding folded tables and free space', async () => {
    mockGetDatabaseStats.mockResolvedValue(stats())
    const { container } = render(<DatabaseOverview />)

    const sectors = () => Array.from(container.querySelectorAll('.recharts-pie-sector path'))
    await waitFor(() => expect(sectors().length).toBe(3))
    const colorClass = (el: Element) => Array.from(el.classList).find(c => c.startsWith('categorical-color-'))
    expect(sectors().map(colorClass)).toEqual(['categorical-color-2', 'categorical-color-6', 'categorical-color-other'])
  })

  it('marks tiny positive sizes instead of rounding them to zero', async () => {
    mockGetDatabaseStats.mockResolvedValue(stats({ tables: [table('videos', 1, 4096)], other_bytes: 0 }))
    render(<DatabaseOverview />)

    await waitFor(() => expect(screen.getByText('<0.001 GB')).toBeDefined())
  })

  it('shows the request failure without any values', async () => {
    mockGetDatabaseStats.mockRejectedValue(new Error('Database statistics request failed (503)'))
    render(<DatabaseOverview />)

    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Database statistics request failed (503)'))
    expect(screen.queryByRole('list')).toBeNull()
    expect(screen.queryByText(/GB$/)).toBeNull()
  })

  it('keeps the storage of a database with no rows and shows empty bars', async () => {
    mockGetDatabaseStats.mockResolvedValue(stats({ tables: [table('videos', 0), table('comments', 0)] }))
    render(<DatabaseOverview />)

    await waitFor(() => expect(screen.getByText('No rows stored yet')).toBeDefined())
    expect(screen.getByTestId('bar-videos').getAttribute('width')).toBe('0%')
    expect(screen.getByText('0.502 GB')).toBeDefined()
  })

  it('shows an empty state for a zero-byte database', async () => {
    mockGetDatabaseStats.mockResolvedValue({ total_bytes: 0, other_bytes: 0, tables: [table('videos', 0, 0)] })
    render(<DatabaseOverview />)

    await waitFor(() => expect(screen.getByText('The database has no allocated storage')).toBeDefined())
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('requests once per mount and ignores a response that lands after unmount', async () => {
    let resolve: (value: DatabaseStatsResponse) => void = () => {}
    mockGetDatabaseStats.mockReturnValue(new Promise(r => { resolve = r }))
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { unmount } = render(<DatabaseOverview />)

    unmount()
    resolve(stats())
    await Promise.resolve()

    expect(mockGetDatabaseStats).toHaveBeenCalledTimes(1)
    expect(consoleError).not.toHaveBeenCalled()
    consoleError.mockRestore()

    mockGetDatabaseStats.mockResolvedValue(stats())
    render(<DatabaseOverview />)
    await waitFor(() => expect(screen.getByText('3.000 GB')).toBeDefined())
    expect(mockGetDatabaseStats).toHaveBeenCalledTimes(2)
  })
})
