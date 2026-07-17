import { useEffect, useState } from 'react'
import { getDateRange } from '@/api'

function lastNDates(days: number): [string, string] {
  const today = new Date()
  const end = today.toISOString().slice(0, 10)
  const start = new Date(today.getTime() - days * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  return [start, end]
}

export function last365Dates(): [string, string] {
  return lastNDates(365)
}

export function last90Dates(): [string, string] {
  return lastNDates(90)
}

export function last28Dates(): [string, string] {
  return lastNDates(28)
}

function datesForPeriod(period: string): [string, string] {
  if (period === 'custom') return ['', '']
  if (period === 'last365') return last365Dates()
  if (period === 'last90') return last90Dates()
  if (period === 'last28') return last28Dates()
  return [`${period}-01-01`, `${period}-12-31`]
}

function periodFromDates(start: string, end: string): string {
  if (!start && !end) return 'custom'
  const year = start.slice(0, 4)
  if (start === `${year}-01-01` && end === `${year}-12-31`) return year
  const [l365start, l365end] = last365Dates()
  if (start === l365start && end === l365end) return 'last365'
  const [l90start, l90end] = last90Dates()
  if (start === l90start && end === l90end) return 'last90'
  const [l28start, l28end] = last28Dates()
  if (start === l28start && end === l28end) return 'last28'
  return 'custom'
}

interface PeriodSelectProps {
  startDate: string
  endDate: string
  onChange: (startDate: string, endDate: string) => void
}

export default function PeriodSelect({ startDate, endDate, onChange }: PeriodSelectProps) {
  const [earliestYear, setEarliestYear] = useState<number | null>(null)

  useEffect(() => {
    getDateRange().then((data: { earliest_year: number | null }) => {
      setEarliestYear(data.earliest_year)
    })
  }, [])

  const currentYear = new Date().getFullYear()
  const years = earliestYear
    ? Array.from({ length: currentYear - earliestYear + 1 }, (_, i) => currentYear - i)
    : []

  const value = periodFromDates(startDate, endDate)

  const handleChange = (period: string) => {
    const [start, end] = datesForPeriod(period)
    onChange(start, end)
  }

  return (
    <label>
      Period
      <select value={value} onChange={e => handleChange(e.target.value)}>
        <option value="custom">Custom</option>
        <option value="last365">Last 365 days</option>
        <option value="last90">Last 90 days</option>
        <option value="last28">Last 28 days</option>
        {years.map(y => (
          <option key={y} value={String(y)}>{y}</option>
        ))}
      </select>
    </label>
  )
}
