import { useState, useMemo, useRef, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import type { AnalyticsRow, PublishedVideo } from '@/types'
import { YAXIS_WIDTH, CHART_RIGHT, formatCompact, getMarks, computeUploadBuckets, UploadStrip } from '@/components/UploadStrip'
import '@/components/AnalyticsChart.css'

interface Props {
  rows: AnalyticsRow[]
  uploadedVideos?: PublishedVideo[]
}

type Metric = 'views' | 'watch_time_hours' | 'estimated_revenue_sgd'
type BucketSize = 'daily' | 'weekly' | 'monthly'
type ChartMode = 'daily' | 'cumulative'

const METRICS: { key: Metric; label: string; format: (v: number) => string }[] = [
  { key: 'views',                label: 'Views',                  format: v => v.toLocaleString() },
  { key: 'watch_time_hours',     label: 'Watch Time (hours)',      format: v => v.toLocaleString(undefined, { maximumFractionDigits: 0 }) },
  { key: 'estimated_revenue_sgd',label: 'Estimated Earnings (SGD)',format: v => `S$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` },
]

const BUCKET_SIZES: { key: BucketSize; label: string }[] = [
  { key: 'daily',   label: 'Daily' },
  { key: 'weekly',  label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
]

const CHART_MODES: { key: ChartMode; label: string }[] = [
  { key: 'daily',      label: 'Per Bucket' },
  { key: 'cumulative', label: 'Cumulative Total' },
]

function toCumulative(rows: (AnalyticsRow & { watch_time_hours: number })[]) {
  let views = 0
  let watchTimeHours = 0
  let revenueSgd = 0
  return rows.map(row => {
    views += row.views
    watchTimeHours += row.watch_time_hours
    revenueSgd += row.estimated_revenue_sgd
    return { ...row, views, watch_time_hours: watchTimeHours, estimated_revenue_sgd: revenueSgd }
  })
}

function bucketKey(date: string, size: BucketSize): string {
  const d = new Date(date)
  if (size === 'monthly') {
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`
  }
  if (size === 'weekly') {
    const day = d.getUTCDay()
    const diffToMonday = (day + 6) % 7
    d.setUTCDate(d.getUTCDate() - diffToMonday)
    return d.toISOString().slice(0, 10)
  }
  return date
}

function aggregateRows(rows: (AnalyticsRow & { watch_time_hours: number })[], size: BucketSize) {
  if (size === 'daily') return rows
  const buckets = new Map<string, AnalyticsRow & { watch_time_hours: number }>()
  for (const row of rows) {
    const key = bucketKey(row.date, size)
    const existing = buckets.get(key)
    if (!existing) {
      buckets.set(key, { ...row, date: key })
    } else {
      existing.views += row.views
      existing.watch_time_minutes += row.watch_time_minutes
      existing.watch_time_hours += row.watch_time_hours
      existing.estimated_revenue += row.estimated_revenue
      existing.estimated_revenue_sgd += row.estimated_revenue_sgd
      existing.likes += row.likes
      existing.subscribers_gained += row.subscribers_gained
      existing.subscribers_lost += row.subscribers_lost
    }
  }
  return Array.from(buckets.values()).sort((a, b) => a.date.localeCompare(b.date))
}

export default function AnalyticsChart({ rows, uploadedVideos }: Props) {
  const [metric, setMetric] = useState<Metric>('views')
  const [bucketSize, setBucketSize] = useState<BucketSize>('daily')
  const [chartMode, setChartMode] = useState<ChartMode>('daily')
  const cardRef = useRef<HTMLDivElement>(null)
  const [cardWidth, setCardWidth] = useState(0)

  useEffect(() => {
    if (!cardRef.current) return
    const obs = new ResizeObserver(entries => {
      setCardWidth(entries[0].contentRect.width)
    })
    obs.observe(cardRef.current)
    return () => obs.disconnect()
  }, [rows.length > 0])

  const chartRows = useMemo(() =>
    aggregateRows(rows.map(r => ({ ...r, watch_time_hours: r.watch_time_minutes / 60 })), bucketSize),
    [rows, bucketSize]
  )

  const displayRows = useMemo(() =>
    chartMode === 'cumulative' ? toCumulative(chartRows) : chartRows,
    [chartRows, chartMode]
  )

  const totals = useMemo(() => ({
    views: rows.reduce((s, r) => s + r.views, 0),
    watch_time_hours: rows.reduce((s, r) => s + r.watch_time_minutes / 60, 0),
    estimated_revenue_sgd: rows.reduce((s, r) => s + r.estimated_revenue_sgd, 0),
  }), [rows])

  const buckets = useMemo(() =>
    computeUploadBuckets(rows, uploadedVideos, cardWidth),
    [uploadedVideos, rows, cardWidth]
  )

  if (rows.length === 0) {
    return (
      <div className="chart-placeholder">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 3v18h18"/><path d="M7 16l4-4 4 4 4-8"/>
        </svg>
        <p>No data for this period</p>
      </div>
    )
  }

  const marks = getMarks(displayRows)
  const activeMeta = METRICS.find(m => m.key === metric)!

  return (
    <div className="analytics-chart card" ref={cardRef}>
      <div className="section-header">Chart Type</div>
      <div className="chart-bucket-buttons">
        {CHART_MODES.map(m => (
          <button
            key={m.key}
            className={`chart-bucket-btn${chartMode === m.key ? ' active' : ''}`}
            onClick={() => setChartMode(m.key)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="section-header">Bucket Size</div>
      <div className="chart-bucket-buttons">
        {BUCKET_SIZES.map(b => (
          <button
            key={b.key}
            className={`chart-bucket-btn${bucketSize === b.key ? ' active' : ''}`}
            onClick={() => setBucketSize(b.key)}
          >
            {b.label}
          </button>
        ))}
      </div>
      <div className="chart-metric-buttons">
        {METRICS.map(m => (
          <button
            key={m.key}
            className={`chart-metric-btn${metric === m.key ? ' active' : ''}`}
            onClick={() => setMetric(m.key)}
          >
            <span className="chart-metric-label">{m.label}</span>
            <span className="chart-metric-value">{m.format(totals[m.key])}</span>
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={displayRows} margin={{ top: 8, right: CHART_RIGHT, left: 0, bottom: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-secondary)' }} tickLine={false} axisLine={false} width={YAXIS_WIDTH}
            tickFormatter={v => activeMeta.key === 'estimated_revenue_sgd' ? `S$${formatCompact(v)}` : formatCompact(v)} />
          <Tooltip
            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}
            labelStyle={{ color: 'var(--text-heading)', fontWeight: 600 }}
            itemStyle={{ color: 'var(--blue)' }}
            formatter={(v) => [activeMeta.format(Number(v)), activeMeta.label]}
          />
          {marks.map(({ date, label }) => (
            <ReferenceLine
              key={date}
              x={date}
              stroke="var(--text-secondary)"
              strokeDasharray="4 3"
              label={{ value: label, position: 'insideBottomLeft', fontSize: 11, fill: 'var(--text-secondary)', dy: 20 }}
            />
          ))}
          <Area type="linear" dataKey={metric} stroke="var(--blue)" strokeWidth={2} fill="var(--blue)" fillOpacity={0.10} dot={false} activeDot={{ r: 4 }} />
        </AreaChart>
      </ResponsiveContainer>

      {uploadedVideos && uploadedVideos.length > 0 && <UploadStrip buckets={buckets} />}
    </div>
  )
}
