import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { lastNDates } from '@/lib/dates'

describe('rolling date windows', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-03T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts each window N days before today and ends today', () => {
    expect(lastNDates(7)).toEqual(['2026-09-26', '2026-10-03'])
    expect(lastNDates(28)).toEqual(['2026-09-05', '2026-10-03'])
    expect(lastNDates(90)).toEqual(['2026-07-05', '2026-10-03'])
    expect(lastNDates(365)).toEqual(['2025-10-03', '2026-10-03'])
  })
})
