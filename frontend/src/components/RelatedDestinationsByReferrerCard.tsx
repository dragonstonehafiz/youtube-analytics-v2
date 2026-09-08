import { Link } from 'react-router-dom'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import type { RelatedDestinationRow, RelatedReferrerRow } from '@/types'
import { categoricalColorClass, CATEGORICAL_OTHER_CLASS } from '@/lib/categoricalColors'
import AsyncCard from '@/components/AsyncCard'
import './RelatedDestinationsByReferrerCard.css'

interface Props {
  title: string
  /** Options for this card's own referrer dropdown, sourced from the same full
   * response that fed the paired breakdown card — no separate request for the options.
   * Omitted entirely (along with the other dropdown props) for the video page's
   * outbound card, which has no ownership split and no dropdown: its referrer is
   * fixed to that page's own video. */
  referrerOptions?: RelatedReferrerRow[]
  referrerOptionsLoading?: boolean
  selectedReferrerId?: string | null
  onSelectReferrer?: (id: string) => void
  destinations: RelatedDestinationRow[]
  loading: boolean
  error?: string | null
}

const TOP_N = 6
const OTHER_ITEMIZE_N = 3
const OTHER_KEY = '__other__'

function referrerOptionLabel(r: RelatedReferrerRow): string {
  return r.title ?? `Unavailable Video: ${r.referrer_video_id}`
}

export default function RelatedDestinationsByReferrerCard({
  title,
  referrerOptions,
  referrerOptionsLoading = false,
  selectedReferrerId,
  onSelectReferrer,
  destinations,
  loading,
  error = null,
}: Props) {
  const selectedReferrer = referrerOptions?.find(r => r.referrer_video_id === selectedReferrerId) ?? null
  const totalViews = destinations.reduce((s, d) => s + d.views, 0)
  const topDestinations = destinations.slice(0, TOP_N)
  const otherDestinations = destinations.slice(TOP_N)
  const otherViews = otherDestinations.reduce((s, d) => s + d.views, 0)
  const itemizedOtherDestinations = otherDestinations.slice(0, OTHER_ITEMIZE_N)
  const remainderDestinations = otherDestinations.slice(OTHER_ITEMIZE_N)
  const remainderViews = remainderDestinations.reduce((s, d) => s + d.views, 0)

  const slices = [
    ...topDestinations.map((d, i) => ({ key: d.target_video_id, label: d.title, views: d.views, colorClass: categoricalColorClass(i) })),
    ...(otherViews > 0 ? [{ key: OTHER_KEY, label: 'Other', views: otherViews, colorClass: CATEGORICAL_OTHER_CLASS }] : []),
  ]

  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={totalViews === 0}
      emptyMessage="No destinations for this referrer"
      className="related-destinations"
      heading={
        onSelectReferrer ? (
          <div className="related-destinations-heading">
            <div className="section-header">{title}</div>
            <select
              className="related-destinations-select"
              aria-label={`${title} referrer`}
              value={selectedReferrerId ?? ''}
              onChange={e => onSelectReferrer(e.target.value)}
              disabled={referrerOptionsLoading || !referrerOptions || referrerOptions.length === 0}
            >
              {(!referrerOptions || referrerOptions.length === 0) && <option value="">No referrers</option>}
              {referrerOptions?.map(r => (
                <option key={r.referrer_video_id} value={r.referrer_video_id}>
                  {referrerOptionLabel(r)} ({r.views.toLocaleString()})
                </option>
              ))}
            </select>
            {selectedReferrer && (
              <div className="related-destinations-selected-referrer">
                {selectedReferrer.thumbnail_url
                  ? <img src={selectedReferrer.thumbnail_url} alt={referrerOptionLabel(selectedReferrer)} className="related-destinations-selected-referrer-thumb" />
                  : <div className="related-destinations-selected-referrer-thumb related-destinations-selected-referrer-thumb--placeholder" />}
              </div>
            )}
          </div>
        ) : (
          <div className="section-header">{title}</div>
        )
      }
    >
      <div className="related-destinations-chart-wrap">
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
        <div className="related-destinations-center">
          <span className="related-destinations-center-value">{totalViews.toLocaleString()}</span>
          <span className="related-destinations-center-label">Views</span>
        </div>
      </div>

      <div className="related-destinations-legend">
        {topDestinations.map((d, i) => (
          <div key={d.target_video_id} className="related-destinations-legend-item">
            {d.thumbnail_url
              ? <img src={d.thumbnail_url} alt="" className="related-destinations-thumb" />
              : <div className="related-destinations-thumb related-destinations-thumb--placeholder" />}
            <span className={`related-destinations-legend-swatch ${categoricalColorClass(i)}`} />
            <span className="related-destinations-legend-label"><Link to={`/analytics/videos/${d.target_video_id}`}>{d.title}</Link></span>
            <span className="related-destinations-legend-views">{d.views.toLocaleString()}</span>
          </div>
        ))}

        {otherDestinations.length > 0 && (
          <>
            <div className="related-destinations-legend-divider">Other includes:</div>
            {itemizedOtherDestinations.map(d => (
              <div key={d.target_video_id} className="related-destinations-legend-item related-destinations-legend-item--sub">
                {d.thumbnail_url
                  ? <img src={d.thumbnail_url} alt="" className="related-destinations-thumb" />
                  : <div className="related-destinations-thumb related-destinations-thumb--placeholder" />}
                <span className={`related-destinations-legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="related-destinations-legend-label"><Link to={`/analytics/videos/${d.target_video_id}`}>{d.title}</Link></span>
                <span className="related-destinations-legend-views">{d.views.toLocaleString()}</span>
              </div>
            ))}
            {remainderDestinations.length > 0 && (
              <div className="related-destinations-legend-item related-destinations-legend-item--sub">
                <div className="related-destinations-thumb related-destinations-thumb--placeholder" />
                <span className={`related-destinations-legend-swatch ${CATEGORICAL_OTHER_CLASS}`} />
                <span className="related-destinations-legend-label">{remainderDestinations.length} more videos</span>
                <span className="related-destinations-legend-views">{remainderViews.toLocaleString()}</span>
              </div>
            )}
          </>
        )}
      </div>
    </AsyncCard>
  )
}
