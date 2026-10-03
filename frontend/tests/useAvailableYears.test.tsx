// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, renderHook, waitFor } from '@testing-library/react'

vi.mock('@/api', () => ({
  getDateRange: vi.fn(),
}))

import { getDateRange } from '@/api'
import { useAvailableYears } from '@/hooks/useAvailableYears'

const mockGetDateRange = vi.mocked(getDateRange)

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date('2026-10-03T12:00:00Z'))
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
})
