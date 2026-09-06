import { Link } from 'react-router-dom'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { SearchTermRow, SearchTermVideo } from '@/types'
import { CATEGORICAL_COLORS, CATEGORICAL_OTHER_COLOR } from '@/lib/categoricalColors'
import AsyncCard from '@/components/AsyncCard'
import './SearchTermVideosDonutCard.css'

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

const TOP_N = 6
const OTHER_KEY = '__other__'

export default function SearchTermVideosDonutCard({
  title, terms, termsLoading, selectedTerm, onSelectTerm, videos, loading, error = null,
}: Props) {
  const totalViews = videos.reduce((s, v) => s + v.views, 0)
  const topVideos = videos.slice(0, TOP_N)
  const otherVideos = videos.slice(TOP_N)
  const otherViews = otherVideos.reduce((s, v) => s + v.views, 0)

  const slices = [
    ...topVideos.map((v, i) => ({ key: v.id, label: v.title, views: v.views, color: CATEGORICAL_COLORS[i] })),
    ...(otherViews > 0 ? [{ key: OTHER_KEY, label: 'Other', views: otherViews, color: CATEGORICAL_OTHER_COLOR }] : []),
  ]

  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={videos.length === 0 || totalViews === 0}
      emptyMessage="No videos for this term"
      className="search-videos-donut"
      heading={
        <div className="search-videos-donut-heading">
          <div className="section-header">{title}</div>
          <select
            className="search-videos-donut-select"
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
      <div className="search-videos-donut-chart-wrap">
        <ResponsiveContainer width="100%" height={160}>
          <PieChart>
            <Pie data={slices} dataKey="views" nameKey="label" innerRadius="65%" outerRadius="100%" paddingAngle={1} stroke="none">
              {slices.map(s => <Cell key={s.key} fill={s.color} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}
              labelStyle={{ color: 'var(--text-heading)', fontWeight: 600 }}
              formatter={(value) => [typeof value === 'number' ? value.toLocaleString() : String(value ?? 0), 'Views']}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="search-videos-donut-center">
          <span className="search-videos-donut-center-value">{totalViews.toLocaleString()}</span>
          <span className="search-videos-donut-center-label">Views</span>
        </div>
      </div>

      <div className="search-videos-donut-legend">
        {topVideos.map((v, i) => (
          <div key={v.id} className="search-videos-donut-legend-item">
            {v.thumbnail_url
              ? <img src={v.thumbnail_url} alt="" className="search-videos-donut-thumb" />
              : <div className="search-videos-donut-thumb search-videos-donut-thumb--placeholder" />}
            <span className="search-videos-donut-legend-swatch" style={{ background: CATEGORICAL_COLORS[i] }} />
            <span className="search-videos-donut-legend-label"><Link to={`/analytics/videos/${v.id}`}>{v.title}</Link></span>
            <span className="search-videos-donut-legend-views">{v.views.toLocaleString()}</span>
          </div>
        ))}

        {otherVideos.length > 0 && (
          <div className="search-videos-donut-legend-divider">
            Other includes {otherVideos.length} more video{otherVideos.length === 1 ? '' : 's'} ({otherViews.toLocaleString()} views)
          </div>
        )}
      </div>
    </AsyncCard>
  )
}
