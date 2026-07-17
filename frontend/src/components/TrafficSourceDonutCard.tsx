import { useMemo } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { TrafficSourceRow } from '@/types'
import { formatTrafficSource, aggregateTrafficSourceTotals, getTrafficSourceColor, TRAFFIC_SOURCE_OTHER_COLOR } from '@/lib/trafficSources'
import './TrafficSourceDonutCard.css'

interface Props {
  title: string
  rows: TrafficSourceRow[]
}

const TOP_N = 6
const OTHER_KEY = 'Other'

export default function TrafficSourceDonutCard({ title, rows }: Props) {
  const totals = useMemo(() => aggregateTrafficSourceTotals(rows), [rows])

  const totalViews = useMemo(() => totals.reduce((s, t) => s + t.views, 0), [totals])

  const topTotals = totals.slice(0, TOP_N)
  const otherTotals = totals.slice(TOP_N)
  const otherViews = otherTotals.reduce((s, t) => s + t.views, 0)

  if (rows.length === 0 || totalViews === 0) return null

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
    <div className="traffic-donut card">
      <div className="section-header">{title}</div>

      <div className="traffic-donut-chart-wrap">
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
        <div className="traffic-donut-center">
          <span className="traffic-donut-center-value">{totalViews.toLocaleString()}</span>
          <span className="traffic-donut-center-label">Views</span>
        </div>
      </div>

      <div className="traffic-donut-legend">
        {topTotals.map(t => (
          <div key={t.traffic_source_type} className="traffic-donut-legend-item">
            <span className="traffic-donut-legend-swatch" style={{ background: getTrafficSourceColor(t.traffic_source_type) }} />
            <span className="traffic-donut-legend-label">{formatTrafficSource(t.traffic_source_type)}</span>
            <span className="traffic-donut-legend-pct">{t.views.toLocaleString()}</span>
          </div>
        ))}

        {otherTotals.length > 0 && (
          <>
            <div className="traffic-donut-legend-divider">Other includes:</div>
            {otherTotals.map(t => (
              <div key={t.traffic_source_type} className="traffic-donut-legend-item traffic-donut-legend-item--sub">
                <span className="traffic-donut-legend-swatch" style={{ background: TRAFFIC_SOURCE_OTHER_COLOR }} />
                <span className="traffic-donut-legend-label">{formatTrafficSource(t.traffic_source_type)}</span>
                <span className="traffic-donut-legend-pct">{t.views.toLocaleString()}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
