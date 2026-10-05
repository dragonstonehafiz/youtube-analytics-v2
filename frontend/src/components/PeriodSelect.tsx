import { lastNDates } from '@/lib/dates'
import { useAvailableYears } from '@/hooks/useAvailableYears'

function datesForPeriod(period: string): [string, string] {
  if (period === 'custom') return ['', '']
  if (period === 'last365') return lastNDates(365)
  if (period === 'last90') return lastNDates(90)
  if (period === 'last28') return lastNDates(28)
  return [`${period}-01-01`, `${period}-12-31`]
}

function periodFromDates(start: string, end: string): string {
  if (!start && !end) return 'custom'
  const year = start.slice(0, 4)
  if (start === `${year}-01-01` && end === `${year}-12-31`) return year
  const [l365start, l365end] = lastNDates(365)
  if (start === l365start && end === l365end) return 'last365'
  const [l90start, l90end] = lastNDates(90)
  if (start === l90start && end === l90end) return 'last90'
  const [l28start, l28end] = lastNDates(28)
  if (start === l28start && end === l28end) return 'last28'
  return 'custom'
}

interface PeriodSelectProps {
  startDate: string
  endDate: string
  onChange: (startDate: string, endDate: string) => void
}

export default function PeriodSelect({ startDate, endDate, onChange }: PeriodSelectProps) {
  const years = useAvailableYears()

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
