import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { SearchTermRow } from '@/types'
import { categoricalColorClass, CATEGORICAL_OTHER_CLASS } from '@/lib/categoricalColors'
import AsyncCard from '@/components/AsyncCard'
import './SearchTermsDonutCard.css'

interface Props {
  title: string
  rows: SearchTermRow[]
  loading: boolean
  error?: string | null
}

const TOP_N = 6
const OTHER_KEY = '__other__'

export default function SearchTermsDonutCard({ title, rows, loading, error = null }: Props) {
  const totalViews = rows.reduce((s, r) => s + r.views, 0)
  const topRows = rows.slice(0, TOP_N)
  const otherRows = rows.slice(TOP_N)
  const otherViews = otherRows.reduce((s, r) => s + r.views, 0)

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
      className="search-terms-donut"
      heading={<div className="section-header">{title}</div>}
    >
      <div className="search-terms-donut-chart-wrap">
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie data={slices} dataKey="views" nameKey="label" innerRadius="65%" outerRadius="100%" paddingAngle={1} stroke="none">
              {slices.map(s => <Cell key={s.key} className={s.colorClass} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}
              labelStyle={{ color: 'var(--text-heading)', fontWeight: 600 }}
              formatter={(value) => [typeof value === 'number' ? value.toLocaleString() : String(value ?? 0), 'Views']}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="search-terms-donut-center">
          <span className="search-terms-donut-center-value">{totalViews.toLocaleString()}</span>
          <span className="search-terms-donut-center-label">Views</span>
        </div>
      </div>

      <div className="search-terms-donut-legend">
        {topRows.map((r, i) => (
          <div key={r.search_term} className="search-terms-donut-legend-item">
            <span className={`search-terms-donut-legend-swatch ${categoricalColorClass(i)}`} />
            <span className="search-terms-donut-legend-label">{r.search_term}</span>
            <span className="search-terms-donut-legend-views">{r.views.toLocaleString()}</span>
          </div>
        ))}

        {otherRows.length > 0 && (
          <>
            <div className="search-terms-donut-legend-divider">Other includes:</div>
            {otherRows.map(r => (
              <div key={r.search_term} className="search-terms-donut-legend-item search-terms-donut-legend-item--sub">
                <span className={`search-terms-donut-legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="search-terms-donut-legend-label">{r.search_term}</span>
                <span className="search-terms-donut-legend-views">{r.views.toLocaleString()}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </AsyncCard>
  )
}
