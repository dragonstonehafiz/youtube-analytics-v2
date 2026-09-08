import { Link } from 'react-router-dom'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { RelatedReferrerRow } from '@/types'
import { categoricalColorClass, CATEGORICAL_OTHER_CLASS } from '@/lib/categoricalColors'
import AsyncCard from '@/components/AsyncCard'
import './RelatedReferrerBreakdownCard.css'

interface Props {
  title: string
  /** Already ranked and capped at 10 by the backend, for one ownership bucket. */
  referrers: RelatedReferrerRow[]
  loading: boolean
  error?: string | null
}

const TOP_N = 6
const OTHER_NAMED_KEY = '__other_named__'

function referrerLabel(r: RelatedReferrerRow): string {
  return r.title ?? `Unavailable Video: ${r.referrer_video_id}`
}

/** An owned referrer deep-links to its own Related Videos sub-tab; a confirmed external
 * referrer opens the real video on YouTube; an unresolved referrer is never linked. */
function ReferrerName({ r }: { r: RelatedReferrerRow }) {
  const label = referrerLabel(r)
  if (r.referrer_own === true) {
    return <Link to={`/analytics/videos/${r.referrer_video_id}?tab=traffic-sources&ts_tab=related`}>{label}</Link>
  }
  if (r.referrer_own === false) {
    return <a href={`https://www.youtube.com/watch?v=${r.referrer_video_id}`} target="_blank" rel="noreferrer">{label}</a>
  }
  return <span>{label}</span>
}

function ReferrerThumb({ r }: { r: RelatedReferrerRow }) {
  return r.thumbnail_url
    ? <img src={r.thumbnail_url} alt="" className="related-referrer-thumb" />
    : <div className="related-referrer-thumb related-referrer-thumb--placeholder" />
}

export default function RelatedReferrerBreakdownCard({ title, referrers, loading, error = null }: Props) {
  const topReferrers = referrers.slice(0, TOP_N)
  const otherReferrers = referrers.slice(TOP_N)
  const otherViews = otherReferrers.reduce((s, r) => s + r.views, 0)
  const totalViews = referrers.reduce((s, r) => s + r.views, 0)

  const slices = [
    ...topReferrers.map((r, i) => ({ key: r.referrer_video_id, label: referrerLabel(r), views: r.views, colorClass: categoricalColorClass(i) })),
    ...(otherViews > 0 ? [{ key: OTHER_NAMED_KEY, label: 'Other named referrers', views: otherViews, colorClass: CATEGORICAL_OTHER_CLASS }] : []),
  ]

  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={totalViews === 0}
      emptyMessage="No Related Video traffic for this period"
      className="related-referrer-breakdown"
      heading={<div className="section-header">{title}</div>}
    >
      <div className="related-referrer-breakdown-chart-wrap">
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
        <div className="related-referrer-breakdown-center">
          <span className="related-referrer-breakdown-center-value">{totalViews.toLocaleString()}</span>
          <span className="related-referrer-breakdown-center-label">Views</span>
        </div>
      </div>

      <div className="related-referrer-breakdown-legend">
        {topReferrers.map((r, i) => (
          <div key={r.referrer_video_id} className="related-referrer-breakdown-legend-item">
            <ReferrerThumb r={r} />
            <span className={`related-referrer-breakdown-legend-swatch ${categoricalColorClass(i)}`} />
            <span className="related-referrer-breakdown-legend-label"><ReferrerName r={r} /></span>
            <span className="related-referrer-breakdown-legend-views">{r.views.toLocaleString()}</span>
          </div>
        ))}

        {otherReferrers.length > 0 && (
          <>
            <div className="related-referrer-breakdown-legend-divider">Other includes:</div>
            {otherReferrers.map(r => (
              <div key={r.referrer_video_id} className="related-referrer-breakdown-legend-item related-referrer-breakdown-legend-item--sub">
                <ReferrerThumb r={r} />
                <span className={`related-referrer-breakdown-legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="related-referrer-breakdown-legend-label"><ReferrerName r={r} /></span>
                <span className="related-referrer-breakdown-legend-views">{r.views.toLocaleString()}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </AsyncCard>
  )
}
