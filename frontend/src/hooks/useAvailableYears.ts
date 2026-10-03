import { useEffect, useState } from 'react'
import { getDateRange } from '@/api'

/** Years with data, newest first, from the earliest stored year through the current year; empty until loaded or on failure. */
export function useAvailableYears(): number[] {
  const [earliestYear, setEarliestYear] = useState<number | null>(null)

  useEffect(() => {
    let active = true
    getDateRange()
      .then((data: { earliest_year: number | null }) => { if (active) setEarliestYear(data.earliest_year) })
      .catch(() => {})
    return () => { active = false }
  }, [])

  const currentYear = new Date().getFullYear()
  return earliestYear && earliestYear <= currentYear
    ? Array.from({ length: currentYear - earliestYear + 1 }, (_, i) => currentYear - i)
    : []
}
