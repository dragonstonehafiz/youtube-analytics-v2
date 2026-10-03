import { useMemo } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { TrafficSourceRow } from '@/types'
import { formatTrafficSource, aggregateTrafficSourceTotals, getTrafficSourceColor, TRAFFIC_SOURCE_OTHER_COLOR } from '@/lib/trafficSources'
import AsyncCard from '@/components/AsyncCard'
import '@/components/DonutCard.css'

interface Props {
  title: string
  rows: TrafficSourceRow[]
  loading: boolean
  error?: string | null
}

const TOP_N = 6
const OTHER_KEY = 'Other'

export default function TrafficSourceDonutCard({ title, rows, loading, error = null }: Props) {
  const totals = useMemo(() => aggregateTrafficSourceTotals(rows), [rows])

  const totalViews = useMemo(() => totals.reduce((s, t) => s + t.views, 0), [totals])

  const topTotals = totals.slice(0, TOP_N)
  const otherTotals = totals.slice(TOP_N)
  const otherViews = otherTotals.reduce((s, t) => s + t.views, 0)

  const slices = [
    ...topTotals.map(t => ({
      key: t.traffic_source_type,
      label: formatTrafficSource(t.traffic_source_type),
      views: t.views,
      color: getTrafficSourceColor(t.traffic_source_type),
    })),
    ...(otherViews > 0 ? [{ key: OTHER_KEY, label: OTHER_KEY, views: otherViews, color: TRAFFIC_SOURCE_OTHER_COLOR }] : []),
  ]

  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={rows.length === 0 || totalViews === 0}
      emptyMessage="No traffic for this period"
      className="traffic-donut donut-card"
      heading={<div className="section-header">{title}</div>}
    >
      <div className="donut-chart-wrap">
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie
              data={slices}
              dataKey="views"
              nameKey="label"
              innerRadius="65%"
              outerRadius="100%"
              paddingAngle={1}
              stroke="none"
            >
              {slices.map(s => <Cell key={s.key} fill={s.color} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}
              labelStyle={{ color: 'var(--text-heading)', fontWeight: 600 }}
              formatter={(value) => [
                typeof value === 'number' ? value.toLocaleString() : String(value ?? 0),
                'Views',
              ]}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <span className="donut-center-value">{totalViews.toLocaleString()}</span>
          <span className="donut-center-label">Views</span>
        </div>
      </div>

      <div className="donut-legend">
        {topTotals.map(t => (
          <div key={t.traffic_source_type} className="donut-legend-item">
            <span className="legend-swatch" style={{ background: getTrafficSourceColor(t.traffic_source_type) }} />
            <span className="donut-legend-label">{formatTrafficSource(t.traffic_source_type)}</span>
            <span className="donut-legend-value">{t.views.toLocaleString()}</span>
          </div>
        ))}

        {otherTotals.length > 0 && (
          <>
            <div className="donut-legend-divider">Other includes:</div>
            {otherTotals.map(t => (
              <div key={t.traffic_source_type} className="donut-legend-item donut-legend-item--sub">
                <span className="legend-swatch" style={{ background: TRAFFIC_SOURCE_OTHER_COLOR }} />
                <span className="donut-legend-label">{formatTrafficSource(t.traffic_source_type)}</span>
                <span className="donut-legend-value">{t.views.toLocaleString()}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </AsyncCard>
  )
}
