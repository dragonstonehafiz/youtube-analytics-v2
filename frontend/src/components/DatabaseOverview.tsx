import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { getDatabaseStats } from '@/api'
import type { DatabaseStatsResponse, DatabaseTableStats } from '@/types'
import AsyncCard from '@/components/AsyncCard'
import { categoricalColorClass, CATEGORICAL_OTHER_CLASS } from '@/lib/categoricalColors'
import '@/components/DonutCard.css'
import '@/components/DatabaseOverview.css'

const BYTES_PER_GB = 1_000_000_000
const GB_DECIMALS = 3
const MIN_SHOWN_GB = 0.001
const DONUT_HEIGHT = 180
/** Matches the traffic-source table's bar ends. */
const BAR_RADIUS = 5

const OTHER_KEY = 'other'
const OTHER_INTERNALS = 'free space and SQLite internals'

// One fixed categorical slot per table, in theme order; slices follow this order so neighbours keep the
// validated pairs. Tables past the eight slots fold into Other.
const TABLE_SLOTS: readonly string[] = [
  'video_analytics',
  'video_traffic_sources',
  'comments',
  'comment_authors',
  'search_terms',
  'related_videos',
  'videos',
  'sync_coverage',
]

interface Slice {
  key: string
  label: string
  bytes: number
  colorClass: string
}

interface LoadState {
  data: DatabaseStatsResponse | null
  error: string | null
}

function tableColorClass(name: string): string {
  const slot = TABLE_SLOTS.indexOf(name)
  return slot === -1 ? CATEGORICAL_OTHER_CLASS : categoricalColorClass(slot)
}

function formatGb(bytes: number): string {
  const gb = bytes / BYTES_PER_GB
  if (gb > 0 && gb < MIN_SHOWN_GB) return `<${MIN_SHOWN_GB} GB`
  return `${gb.toLocaleString(undefined, { minimumFractionDigits: GB_DECIMALS, maximumFractionDigits: GB_DECIMALS })} GB`
}

/** Largest row count first; equal counts fall back to table name. */
function byRowCount(a: DatabaseTableStats, b: DatabaseTableStats): number {
  return b.row_count - a.row_count || a.name.localeCompare(b.name)
}

function StorageTooltip({ active, payload }: TooltipContentProps) {
  const slice = payload?.[0]?.payload as Slice | undefined
  if (!active || !slice) return null
  return (
    <div className="database-overview-tooltip">
      <span className="database-overview-tooltip-label">{slice.label}</span>
      <span>{formatGb(slice.bytes)}</span>
    </div>
  )
}

/** Database storage donut and per-table row counts, fetched once per mount. */
export default function DatabaseOverview() {
  const [state, setState] = useState<LoadState>({ data: null, error: null })

  useEffect(() => {
    let active = true
    getDatabaseStats()
      .then(data => {
        if (active) setState({ data, error: null })
      })
      .catch((err: unknown) => {
        if (active) setState({ data: null, error: err instanceof Error ? err.message : 'Could not load database statistics' })
      })
    return () => {
      active = false
    }
  }, [])

  const { data, error } = state
  const loading = data === null && error === null

  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={data !== null && data.total_bytes === 0}
      emptyMessage="The database has no allocated storage"
      className="database-overview donut-card"
      heading={<div className="section-header">Database</div>}
    >
      {data && <DatabaseOverviewContent data={data} />}
    </AsyncCard>
  )
}

function DatabaseOverviewContent({ data }: { data: DatabaseStatsResponse }) {
  const slotted = TABLE_SLOTS.flatMap(name => data.tables.filter(t => t.name === name))
  const folded = data.tables.filter(t => !TABLE_SLOTS.includes(t.name))
  const otherLabel = `Other (${[...folded.map(t => t.name), OTHER_INTERNALS].join(', ')})`
  const otherBytes = data.other_bytes + folded.reduce((sum, t) => sum + t.size_bytes, 0)
  const slices: Slice[] = [
    ...slotted.map(t => ({ key: t.name, label: t.name, bytes: t.size_bytes, colorClass: tableColorClass(t.name) })),
    { key: OTHER_KEY, label: otherLabel, bytes: otherBytes, colorClass: CATEGORICAL_OTHER_CLASS },
  ].filter(s => s.bytes > 0)
  const rows = [...data.tables].sort(byRowCount)
  const maxRows = rows.length > 0 ? rows[0].row_count : 0

  return (
    <div className="database-overview-body">
      <div className="donut-chart-wrap">
        <ResponsiveContainer width="100%" height={DONUT_HEIGHT}>
          <PieChart>
            <Pie
              data={slices}
              dataKey="bytes"
              nameKey="label"
              innerRadius="65%"
              outerRadius="100%"
              paddingAngle={1}
              stroke="none"
            >
              {slices.map(s => <Cell key={s.key} className={s.colorClass} />)}
            </Pie>
            <Tooltip content={StorageTooltip} />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <span className="donut-center-value">{formatGb(data.total_bytes)}</span>
          <span className="donut-center-label">Total</span>
        </div>
      </div>

      <div className="database-overview-rows">
        {maxRows === 0 && <p className="database-overview-note">No rows stored yet</p>}
        <ul className="database-overview-bars" aria-label="Rows per table">
          {rows.map(t => (
            <li key={t.name} className="database-overview-bar-row">
              <span className="database-overview-bar-label">{t.name}</span>
              <svg className="database-overview-bar" aria-hidden="true">
                <rect className="database-overview-bar-track" width="100%" height="100%" rx={BAR_RADIUS} />
                <rect
                  data-testid={`bar-${t.name}`}
                  width={`${maxRows > 0 ? (t.row_count / maxRows) * 100 : 0}%`}
                  height="100%"
                  rx={BAR_RADIUS}
                  className={tableColorClass(t.name)}
                />
              </svg>
              <span className="database-overview-bar-value">{t.row_count.toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
