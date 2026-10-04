import { useEffect, useState } from 'react'
import { getDateRange } from '@/api'

// One request per page load, shared by every caller. Cleared on failure or when nothing is
// stored yet, so the next mount asks again.
let earliestYearRequest: Promise<number | null> | null = null

/** Years with data, newest first, from the earliest stored year through the current year; empty until loaded or on failure. */
export function useAvailableYears(): number[] {
  const [earliestYear, setEarliestYear] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    earliestYearRequest ??= getDateRange()
      .then((data: { earliest_year: number | null }) => {
        if (data.earliest_year === null) earliestYearRequest = null
        return data.earliest_year
      })
      .catch(() => {
        earliestYearRequest = null
        return null
      })
    earliestYearRequest.then(year => { if (active) setEarliestYear(year) })
    return () => { active = false }
  }, [])

  const currentYear = new Date().getFullYear()
  return earliestYear && earliestYear <= currentYear
    ? Array.from({ length: currentYear - earliestYear + 1 }, (_, i) => currentYear - i)
    : []
}
