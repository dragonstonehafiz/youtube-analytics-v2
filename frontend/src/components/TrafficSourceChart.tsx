import { useState, useMemo, useRef, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import type { TrafficSourceRow, PublishedVideo } from '@/types'
import { formatTrafficSource, aggregateTrafficSourceTotals, getTrafficSourceColor, TRAFFIC_SOURCE_OTHER_COLOR } from '@/lib/trafficSources'
import { YAXIS_WIDTH, CHART_RIGHT, formatCompact, getMarks, computeUploadBuckets, UploadStrip } from '@/components/UploadStrip'
import '@/components/AnalyticsChart.css'
import './TrafficSourceChart.css'

interface Props {
  rows: TrafficSourceRow[]
  uploadedVideos?: PublishedVideo[]
}

type Metric = 'views' | 'watch_time_hours'
type BucketSize = 'daily' | 'weekly' | 'monthly'
type ChartMode = 'daily' | 'cumulative'

const METRICS: { key: Metric; label: string; format: (v: number) => string }[] = [
  { key: 'views',            label: 'Views',              format: v => v.toLocaleString() },
  { key: 'watch_time_hours', label: 'Watch Time (hours)', format: v => v.toLocaleString(undefined, { maximumFractionDigits: 0 }) },
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

const TOP_N = 6
const OTHER_KEY = 'Other'

interface ChartDatum {
  date: string
  [key: string]: string | number
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

function toCumulative(rows: ChartDatum[], seriesKeys: string[]): ChartDatum[] {
  const running: Record<string, number> = {}
  for (const key of seriesKeys) running[key] = 0
  return rows.map(row => {
    const next: ChartDatum = { ...row }
    for (const key of seriesKeys) {
      running[key] += row[key] as number
      next[key] = running[key]
    }
    return next
  })
}

export default function TrafficSourceChart({ rows, uploadedVideos }: Props) {
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

  const topTypes = useMemo(
    () => aggregateTrafficSourceTotals(rows).slice(0, TOP_N).map(t => t.traffic_source_type),
    [rows]
  )

  const series = useMemo(
    () => topTypes.map(type => ({ key: type, label: formatTrafficSource(type), color: getTrafficSourceColor(type) })),
    [topTypes]
  )

  const chartRows = useMemo(() => {
    const topSet = new Set(topTypes)
    const byBucket = new Map<string, ChartDatum>()
    for (const r of rows) {
      const key = bucketKey(r.date, bucketSize)
      let datum = byBucket.get(key)
      if (!datum) {
        datum = { date: key }
        for (const t of topTypes) datum[t] = 0
        datum[OTHER_KEY] = 0
        byBucket.set(key, datum)
      }
      const seriesKey = topSet.has(r.traffic_source_type) ? r.traffic_source_type : OTHER_KEY
      const value = metric === 'views' ? r.views : r.watch_time_minutes / 60
      datum[seriesKey] = (datum[seriesKey] as number) + value
    }
    return Array.from(byBucket.values()).sort((a, b) => a.date.localeCompare(b.date))
  }, [rows, topTypes, metric, bucketSize])

  const displayRows = useMemo(
    () => chartMode === 'cumulative' ? toCumulative(chartRows, [...topTypes, OTHER_KEY]) : chartRows,
    [chartRows, chartMode, topTypes]
  )

  const totals = useMemo(() => ({
    views: rows.reduce((s, r) => s + r.views, 0),
    watch_time_hours: rows.reduce((s, r) => s + r.watch_time_minutes / 60, 0),
  }), [rows])

  const buckets = useMemo(() =>
    computeUploadBuckets(chartRows, uploadedVideos, cardWidth),
    [uploadedVideos, chartRows, cardWidth]
  )

  const hasOther = useMemo(
    () => chartRows.some(r => (r[OTHER_KEY] as number) > 0),
    [chartRows]
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

      <div className="traffic-source-legend">
        {series.map(s => (
          <div key={s.key} className="traffic-source-legend-item">
            <span className="traffic-source-legend-swatch" style={{ background: s.color }} />
            {s.label}
          </div>
        ))}
        {hasOther && (
          <div className="traffic-source-legend-item">
            <span className="traffic-source-legend-swatch" style={{ background: TRAFFIC_SOURCE_OTHER_COLOR }} />
            Other
          </div>
        )}
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={displayRows} margin={{ top: 8, right: CHART_RIGHT, left: 0, bottom: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-secondary)' }} tickLine={false} axisLine={false} width={YAXIS_WIDTH}
            tickFormatter={v => formatCompact(v)} />
          <Tooltip
            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}
            labelStyle={{ color: 'var(--text-heading)', fontWeight: 600 }}
            formatter={(v, name) => [activeMeta.format(Number(v)), name === OTHER_KEY ? OTHER_KEY : formatTrafficSource(String(name))]}
            itemSorter={item => -(item.value as number)}
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
          {series.map(s => (
            <Line key={s.key} type="linear" dataKey={s.key} name={s.key} stroke={s.color} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          ))}
          {hasOther && (
            <Line type="linear" dataKey={OTHER_KEY} name={OTHER_KEY} stroke={TRAFFIC_SOURCE_OTHER_COLOR} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          )}
        </LineChart>
      </ResponsiveContainer>

      {uploadedVideos && uploadedVideos.length > 0 && <UploadStrip buckets={buckets} />}
    </div>
  )
}
