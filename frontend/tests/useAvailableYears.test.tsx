// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, renderHook, waitFor } from '@testing-library/react'

vi.mock('@/api', () => ({
  getDateRange: vi.fn(),
}))

import { getDateRange } from '@/api'

const mockGetDateRange = vi.mocked(getDateRange)

/** The hook from a fresh module, so each test starts without a cached year. */
let useAvailableYears: typeof import('@/hooks/useAvailableYears').useAvailableYears

beforeEach(async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-10-03T12:00:00Z'))
  vi.resetModules()
  ;({ useAvailableYears } = await import('@/hooks/useAvailableYears'))
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useAvailableYears', () => {
  it('lists the earliest stored year through the current year, newest first', async () => {
    mockGetDateRange.mockResolvedValue({ earliest_year: 2023 })
    const { result } = renderHook(() => useAvailableYears())
    await waitFor(() => expect(result.current).toEqual([2026, 2025, 2024, 2023]))
  })

  it('stays empty when no data is stored', async () => {
    mockGetDateRange.mockResolvedValue({ earliest_year: null })
    const { result } = renderHook(() => useAvailableYears())
    await waitFor(() => expect(mockGetDateRange).toHaveBeenCalled())
    expect(result.current).toEqual([])
  })

  it('stays empty when the request fails', async () => {
    mockGetDateRange.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useAvailableYears())
    await waitFor(() => expect(mockGetDateRange).toHaveBeenCalled())
    expect(result.current).toEqual([])
  })

  it('ignores a response that arrives after unmount', async () => {
    let resolve: (value: { earliest_year: number }) => void = () => {}
    mockGetDateRange.mockReturnValue(new Promise(r => { resolve = r }))
    const { result, unmount } = renderHook(() => useAvailableYears())
    unmount()
    resolve({ earliest_year: 2024 })
    await Promise.resolve()
    expect(result.current).toEqual([])
  })

  it('reuses the first response for later mounts without another request', async () => {
    mockGetDateRange.mockResolvedValue({ earliest_year: 2024 })
    const first = renderHook(() => useAvailableYears())
    await waitFor(() => expect(first.result.current).toEqual([2026, 2025, 2024]))
    first.unmount()

    const second = renderHook(() => useAvailableYears())
    await waitFor(() => expect(second.result.current).toEqual([2026, 2025, 2024]))
    expect(mockGetDateRange).toHaveBeenCalledTimes(1)
  })

  it('shares one request between components mounted together', async () => {
    mockGetDateRange.mockResolvedValue({ earliest_year: 2025 })
    const a = renderHook(() => useAvailableYears())
    const b = renderHook(() => useAvailableYears())
    await waitFor(() => expect(b.result.current).toEqual([2026, 2025]))
    expect(a.result.current).toEqual([2026, 2025])
    expect(mockGetDateRange).toHaveBeenCalledTimes(1)
  })

  it('asks again on the next mount after a failure', async () => {
    mockGetDateRange.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce({ earliest_year: 2025 })
    const first = renderHook(() => useAvailableYears())
    await waitFor(() => expect(mockGetDateRange).toHaveBeenCalledTimes(1))
    first.unmount()

    const second = renderHook(() => useAvailableYears())
    await waitFor(() => expect(second.result.current).toEqual([2026, 2025]))
    expect(mockGetDateRange).toHaveBeenCalledTimes(2)
  })

  it('asks again on the next mount when nothing was stored yet', async () => {
    mockGetDateRange.mockResolvedValueOnce({ earliest_year: null }).mockResolvedValueOnce({ earliest_year: 2025 })
    const first = renderHook(() => useAvailableYears())
    await waitFor(() => expect(mockGetDateRange).toHaveBeenCalledTimes(1))
    first.unmount()

    const second = renderHook(() => useAvailableYears())
    await waitFor(() => expect(second.result.current).toEqual([2026, 2025]))
    expect(mockGetDateRange).toHaveBeenCalledTimes(2)
  })
})
