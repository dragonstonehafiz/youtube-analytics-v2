import { Fragment } from 'react'
import type { ReactNode } from 'react'
import PeriodSelect from '@/components/PeriodSelect'

interface FilterField {
  value: string
  onChange: (value: string) => void
}

interface DateFields {
  startDate: FilterField
  endDate: FilterField
  /** Period dropdown choice, which sets both dates at once. The dropdown is shown only when given. */
  onPeriodChange?: (startDate: string, endDate: string) => void
}

/** Each field group is rendered only when given, in this order, with a divider between groups. */
interface FilterBarProps {
  dates?: DateFields
  title?: FilterField
  contentType?: FilterField
  privacyStatus?: FilterField
  /** A page's own fields, rendered last. */
  children?: ReactNode
}

/** Type select (All / Video / Short). */
export function ContentTypeSelect({ value, onChange }: FilterField) {
  return (
    <label>
      Type
      <select value={value} onChange={e => onChange(e.target.value)}>
        <option value="">All</option>
        <option value="video">Video</option>
        <option value="short">Short</option>
      </select>
    </label>
  )
}

export default function FilterBar({ dates, title, contentType, privacyStatus, children }: FilterBarProps) {
  const groups: ReactNode[] = []
  if (dates) {
    groups.push(
      <>
        {dates.onPeriodChange && (
          <PeriodSelect startDate={dates.startDate.value} endDate={dates.endDate.value} onChange={dates.onPeriodChange} />
        )}
        <label>
          Start
          <input type="date" value={dates.startDate.value} onChange={e => dates.startDate.onChange(e.target.value)} />
        </label>
        <label>
          End
          <input type="date" value={dates.endDate.value} onChange={e => dates.endDate.onChange(e.target.value)} />
        </label>
      </>,
    )
  }
  if (title) {
    groups.push(
      <label>
        Title
        <input type="text" placeholder="Search…" value={title.value} onChange={e => title.onChange(e.target.value)} />
      </label>,
    )
  }
  if (contentType) groups.push(<ContentTypeSelect {...contentType} />)
  if (privacyStatus) {
    groups.push(
      <label>
        Privacy
        <select value={privacyStatus.value} onChange={e => privacyStatus.onChange(e.target.value)}>
          <option value="">All</option>
          <option value="public">Public</option>
          <option value="private">Private</option>
          <option value="unlisted">Unlisted</option>
        </select>
      </label>,
    )
  }
  if (children) groups.push(children)

  return (
    <div className="filter-bar">
      {groups.map((group, i) => (
        <Fragment key={i}>
          {i > 0 && <div className="filter-bar-sep" />}
          {group}
        </Fragment>
      ))}
    </div>
  )
}
