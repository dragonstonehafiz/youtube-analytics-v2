import { useState, useMemo, useRef, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import type { AnalyticsRow, ContentType, PublishedVideo } from '@/types'
import { YAXIS_WIDTH, CHART_RIGHT, formatCompact, getMarks, computeUploadBuckets, UploadStrip } from '@/components/UploadStrip'
import '@/components/AnalyticsChart.css'

interface Props {
  rows: AnalyticsRow[]
  uploadedVideos?: PublishedVideo[]
}

type Metric = 'views' | 'watch_time_hours' | 'estimated_revenue_sgd'
type BucketSize = 'daily' | 'weekly' | 'monthly'
type ChartMode = 'daily' | 'cumulative'

interface ChartPoint {
  date: string
  video_views: number
  short_views: number
  video_watch_time_hours: number
  short_watch_time_hours: number
  video_estimated_revenue_sgd: number
  short_estimated_revenue_sgd: number
}

interface Series {
  type: ContentType
  label: string
  color: string
}

const SERIES: Series[] = [
  { type: 'video', label: 'Video',  color: 'var(--blue)' },
  { type: 'short', label: 'Shorts', color: '#f59e0b' },
]

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

function seriesDataKey(type: ContentType, metric: Metric): keyof ChartPoint {
  return `${type}_${metric}` as keyof ChartPoint
}

function emptyPoint(date: string): ChartPoint {
  return {
    date,
    video_views: 0, short_views: 0,
    video_watch_time_hours: 0, short_watch_time_hours: 0,
    video_estimated_revenue_sgd: 0, short_estimated_revenue_sgd: 0,
  }
}

function addRowToPoint(point: ChartPoint, row: AnalyticsRow): void {
  const watchTimeHours = row.watch_time_minutes / 60
  if (row.content_type === 'video') {
    point.video_views += row.views
    point.video_watch_time_hours += watchTimeHours
    point.video_estimated_revenue_sgd += row.estimated_revenue_sgd
  } else {
    point.short_views += row.views
    point.short_watch_time_hours += watchTimeHours
    point.short_estimated_revenue_sgd += row.estimated_revenue_sgd
  }
}

function toCumulative(points: ChartPoint[]): ChartPoint[] {
  const running = emptyPoint('')
  return points.map(point => {
    running.video_views += point.video_views
    running.short_views += point.short_views
    running.video_watch_time_hours += point.video_watch_time_hours
    running.short_watch_time_hours += point.short_watch_time_hours
    running.video_estimated_revenue_sgd += point.video_estimated_revenue_sgd
    running.short_estimated_revenue_sgd += point.short_estimated_revenue_sgd
    return { ...running, date: point.date }
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

function aggregateRows(rows: AnalyticsRow[], size: BucketSize): ChartPoint[] {
  const buckets = new Map<string, ChartPoint>()
  for (const row of rows) {
    const key = bucketKey(row.date, size)
    let point = buckets.get(key)
    if (!point) {
      point = emptyPoint(key)
      buckets.set(key, point)
    }
    addRowToPoint(point, row)
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

  const presentTypes = useMemo(() => new Set(rows.map(r => r.content_type)), [rows])
  const activeSeries = useMemo(() => SERIES.filter(s => presentTypes.has(s.type)), [presentTypes])

  const chartRows = useMemo(() =>
    aggregateRows(rows, bucketSize),
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

      {activeSeries.length > 1 && (
        <div className="analytics-chart-legend">
          {activeSeries.map(s => (
            <div key={s.type} className="analytics-chart-legend-item">
              <span className="analytics-chart-legend-swatch" style={{ background: s.color }} />
              {s.label}
            </div>
          ))}
        </div>
      )}

      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={displayRows} margin={{ top: 8, right: CHART_RIGHT, left: 0, bottom: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-secondary)' }} tickLine={false} axisLine={false} width={YAXIS_WIDTH}
            tickFormatter={v => activeMeta.key === 'estimated_revenue_sgd' ? `S$${formatCompact(v)}` : formatCompact(v)} />
          <Tooltip
            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}
            labelStyle={{ color: 'var(--text-heading)', fontWeight: 600 }}
            formatter={(v, name) => [activeMeta.format(Number(v)), name]}
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
          {activeSeries.map(s => (
            <Area
              key={s.type}
              type="linear"
              dataKey={seriesDataKey(s.type, metric)}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              fill={s.color}
              fillOpacity={0.10}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>

      {uploadedVideos && uploadedVideos.length > 0 && <UploadStrip buckets={buckets} />}
    </div>
  )
}
