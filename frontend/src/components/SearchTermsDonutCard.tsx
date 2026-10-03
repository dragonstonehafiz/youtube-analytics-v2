import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { SearchTermRow } from '@/types'
import { categoricalColorClass, CATEGORICAL_OTHER_CLASS, CATEGORICAL_SLOT_COUNT } from '@/lib/categoricalColors'
import AsyncCard from '@/components/AsyncCard'
import '@/components/DonutCard.css'

interface Props {
  title: string
  rows: SearchTermRow[]
  loading: boolean
  error?: string | null
}

const OTHER_ITEMIZE_N = 3
const OTHER_KEY = '__other__'

export default function SearchTermsDonutCard({ title, rows, loading, error = null }: Props) {
  const totalViews = rows.reduce((s, r) => s + r.views, 0)
  const topRows = rows.slice(0, CATEGORICAL_SLOT_COUNT)
  const otherRows = rows.slice(CATEGORICAL_SLOT_COUNT)
  const otherViews = otherRows.reduce((s, r) => s + r.views, 0)
  const itemizedOtherRows = otherRows.slice(0, OTHER_ITEMIZE_N)
  const remainderRows = otherRows.slice(OTHER_ITEMIZE_N)
  const remainderViews = remainderRows.reduce((s, r) => s + r.views, 0)

  const slices = [
    ...topRows.map((r, i) => ({ key: r.search_term, label: r.search_term, views: r.views, colorClass: categoricalColorClass(i) })),
    ...(otherViews > 0 ? [{ key: OTHER_KEY, label: 'Other', views: otherViews, colorClass: CATEGORICAL_OTHER_CLASS }] : []),
  ]

  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={rows.length === 0 || totalViews === 0}
      emptyMessage="No search traffic for this period"
      className="search-terms-donut donut-card"
      heading={<div className="section-header">{title}</div>}
    >
      <div className="donut-chart-wrap">
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie data={slices} dataKey="views" nameKey="label" innerRadius="65%" outerRadius="100%" paddingAngle={1} stroke="none">
              {slices.map(s => <Cell key={s.key} className={s.colorClass} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}
              labelStyle={{ color: 'var(--text-heading)', fontWeight: 600 }}
              formatter={(value, name) => [typeof value === 'number' ? value.toLocaleString() : String(value ?? 0), name]}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <span className="donut-center-value">{totalViews.toLocaleString()}</span>
          <span className="donut-center-label">Views</span>
        </div>
      </div>

      <div className="donut-legend">
        {topRows.map((r, i) => (
          <div key={r.search_term} className="donut-legend-item">
            <span className={`legend-swatch ${categoricalColorClass(i)}`} />
            <span className="donut-legend-label">{r.search_term}</span>
            <span className="donut-legend-value">{r.views.toLocaleString()}</span>
          </div>
        ))}

        {otherRows.length > 0 && (
          <>
            <div className="donut-legend-divider">Other includes:</div>
            {itemizedOtherRows.map(r => (
              <div key={r.search_term} className="donut-legend-item donut-legend-item--sub">
                <span className={`legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="donut-legend-label">{r.search_term}</span>
                <span className="donut-legend-value">{r.views.toLocaleString()}</span>
              </div>
            ))}
            {remainderRows.length > 0 && (
              <div className="donut-legend-item donut-legend-item--sub">
                <span className={`legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="donut-legend-label">{remainderRows.length} more terms</span>
                <span className="donut-legend-value">{remainderViews.toLocaleString()}</span>
              </div>
            )}
          </>
        )}
      </div>
    </AsyncCard>
  )
}
