import { Link } from 'react-router-dom'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { SearchTermRow, SearchTermVideo } from '@/types'
import { categoricalColorClass, CATEGORICAL_OTHER_CLASS, CATEGORICAL_SLOT_COUNT } from '@/lib/categoricalColors'
import AsyncCard from '@/components/AsyncCard'
import '@/components/DonutCard.css'

interface Props {
  title: string
  /** Options for this card's own term dropdown. Independent per card — selecting a term
   * here has no effect on any other card. */
  terms: SearchTermRow[]
  termsLoading: boolean
  selectedTerm: string | null
  onSelectTerm: (term: string) => void
  videos: SearchTermVideo[]
  loading: boolean
  error?: string | null
}

const OTHER_ITEMIZE_N = 3
const OTHER_KEY = '__other__'

export default function SearchTermVideosDonutCard({
  title, terms, termsLoading, selectedTerm, onSelectTerm, videos, loading, error = null,
}: Props) {
  const totalViews = videos.reduce((s, v) => s + v.views, 0)
  const topVideos = videos.slice(0, CATEGORICAL_SLOT_COUNT)
  const otherVideos = videos.slice(CATEGORICAL_SLOT_COUNT)
  const otherViews = otherVideos.reduce((s, v) => s + v.views, 0)
  const itemizedOtherVideos = otherVideos.slice(0, OTHER_ITEMIZE_N)
  const remainderVideos = otherVideos.slice(OTHER_ITEMIZE_N)
  const remainderViews = remainderVideos.reduce((s, v) => s + v.views, 0)

  const slices = [
    ...topVideos.map((v, i) => ({ key: v.id, label: v.title, views: v.views, colorClass: categoricalColorClass(i) })),
    ...(otherViews > 0 ? [{ key: OTHER_KEY, label: 'Other', views: otherViews, colorClass: CATEGORICAL_OTHER_CLASS }] : []),
  ]

  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={videos.length === 0 || totalViews === 0}
      emptyMessage="No videos for this term"
      className="search-videos-donut donut-card donut-card--picker"
      heading={
        <div className="donut-card-heading">
          <div className="section-header">{title}</div>
          <select
            className="form-control"
            value={selectedTerm ?? ''}
            onChange={e => onSelectTerm(e.target.value)}
            disabled={termsLoading || terms.length === 0}
          >
            {terms.length === 0 && <option value="">No search terms</option>}
            {terms.map(t => (
              <option key={t.search_term} value={t.search_term}>{t.search_term} ({t.views.toLocaleString()})</option>
            ))}
          </select>
        </div>
      }
    >
      <div className="donut-chart-wrap">
        <ResponsiveContainer width="100%" height={160}>
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
        {topVideos.map((v, i) => (
          <div key={v.id} className="donut-legend-item">
            {v.thumbnail_url
              ? <img src={v.thumbnail_url} alt="" className="thumb-small" />
              : <div className="thumb-small thumb-placeholder" />}
            <span className={`legend-swatch ${categoricalColorClass(i)}`} />
            <span className="donut-legend-label"><Link to={`/analytics/videos/${v.id}`}>{v.title}</Link></span>
            <span className="donut-legend-value">{v.views.toLocaleString()}</span>
          </div>
        ))}

        {otherVideos.length > 0 && (
          <>
            <div className="donut-legend-divider">Other includes:</div>
            {itemizedOtherVideos.map(v => (
              <div key={v.id} className="donut-legend-item donut-legend-item--sub">
                {v.thumbnail_url
                  ? <img src={v.thumbnail_url} alt="" className="thumb-small" />
                  : <div className="thumb-small thumb-placeholder" />}
                <span className={`legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="donut-legend-label"><Link to={`/analytics/videos/${v.id}`}>{v.title}</Link></span>
                <span className="donut-legend-value">{v.views.toLocaleString()}</span>
              </div>
            ))}
            {remainderVideos.length > 0 && (
              <div className="donut-legend-item donut-legend-item--sub">
                <div className="thumb-small thumb-placeholder" />
                <span className={`legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="donut-legend-label">{remainderVideos.length} more videos</span>
                <span className="donut-legend-value">{remainderViews.toLocaleString()}</span>
              </div>
            )}
          </>
        )}
      </div>
    </AsyncCard>
  )
}
