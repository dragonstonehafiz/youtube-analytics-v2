import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { SearchTermRow } from '@/types'
import { categoricalColorClass, CATEGORICAL_SLOT_COUNT } from '@/lib/categoricalColors'
import AsyncCard from '@/components/AsyncCard'
import './SearchTermsDonutCard.css'

interface Props {
  title: string
  rows: SearchTermRow[]
  loading: boolean
  error?: string | null
}

export default function SearchTermsDonutCard({ title, rows, loading, error = null }: Props) {
  const totalViews = rows.reduce((s, r) => s + r.views, 0)

  // Every fetched term is a real, named term — there is no unattributed/residual figure
  // computed anywhere in this app, so nothing here is genuinely "Other". The palette only
  // has CATEGORICAL_SLOT_COUNT distinct hues, so slices beyond that reuse them in rotation.
  const slices = rows.map((r, i) => ({ key: r.search_term, label: r.search_term, views: r.views, colorClass: categoricalColorClass(i % CATEGORICAL_SLOT_COUNT) }))

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
              formatter={(value, name) => [typeof value === 'number' ? value.toLocaleString() : String(value ?? 0), name]}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="search-terms-donut-center">
          <span className="search-terms-donut-center-value">{totalViews.toLocaleString()}</span>
          <span className="search-terms-donut-center-label">Views</span>
        </div>
      </div>

      <div className="search-terms-donut-legend">
        {rows.map((r, i) => (
          <div key={r.search_term} className="search-terms-donut-legend-item">
            <span className={`search-terms-donut-legend-swatch ${categoricalColorClass(i % CATEGORICAL_SLOT_COUNT)}`} />
            <span className="search-terms-donut-legend-label">{r.search_term}</span>
            <span className="search-terms-donut-legend-views">{r.views.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </AsyncCard>
  )
}
