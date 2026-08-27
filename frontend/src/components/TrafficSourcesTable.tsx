import type { TrafficSourceRow } from '@/types'
import { formatTrafficSource, aggregateTrafficSourceTotals, getTrafficSourceColor } from '@/lib/trafficSources'
import AsyncCard from '@/components/AsyncCard'
import './TrafficSourcesTable.css'

interface Props {
  rows: TrafficSourceRow[]
  loading: boolean
  error?: string | null
}

export default function TrafficSourcesTable({ rows, loading, error = null }: Props) {
  const totals = aggregateTrafficSourceTotals(rows)
  const maxViews = totals.length > 0 ? Math.max(...totals.map(t => t.views)) : 0
  const totalViews = totals.reduce((s, t) => s + t.views, 0)

  return (
    <div className="traffic-sources-section">
      <div className="section-header">Traffic Sources</div>
      <AsyncCard
        variant="table"
        loading={loading}
        error={error}
        empty={rows.length === 0}
        emptyMessage="No traffic for this period"
        className="traffic-sources-table-card"
      >
        <div className="table-overflow-wrap traffic-sources-table-wrap">
          <table className="data-table traffic-sources-table">
            <colgroup>
              <col className="traffic-sources-col-source" />
              <col />
              <col className="traffic-sources-col-views" />
              <col className="traffic-sources-col-watch-time" />
              <col className="traffic-sources-col-share" />
            </colgroup>
            <thead>
              <tr>
                <th>Source</th>
                <th></th>
                <th>Views</th>
                <th>Watch Time (hrs)</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {totals.map(t => {
                const color = getTrafficSourceColor(t.traffic_source_type)
                const barPct = maxViews > 0 ? (t.views / maxViews) * 100 : 0
                const sharePct = totalViews > 0 ? (t.views / totalViews) * 100 : 0
                return (
                  <tr key={t.traffic_source_type}>
                    <td>{formatTrafficSource(t.traffic_source_type)}</td>
                    <td>
                      <div className="traffic-source-bar-track">
                        <div className="traffic-source-bar-fill" style={{ width: `${barPct}%`, background: color }} />
                      </div>
                    </td>
                    <td>{t.views.toLocaleString()}</td>
                    <td>{(t.watch_time_minutes / 60).toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                    <td>{sharePct.toLocaleString(undefined, { maximumFractionDigits: 1 })}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </AsyncCard>
    </div>
  )
}
