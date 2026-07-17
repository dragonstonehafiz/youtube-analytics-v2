import type { TrafficSourceRow } from '@/types'
import { formatTrafficSource, aggregateTrafficSourceTotals, getTrafficSourceColor } from '@/lib/trafficSources'
import './TrafficSourcesTable.css'

interface Props {
  rows: TrafficSourceRow[]
}

export default function TrafficSourcesTable({ rows }: Props) {
  if (rows.length === 0) {
    return <div className="chart-placeholder">No traffic source data available.</div>
  }

  const totals = aggregateTrafficSourceTotals(rows)
  const maxViews = Math.max(...totals.map(t => t.views))
  const totalViews = totals.reduce((s, t) => s + t.views, 0)

  return (
    <div className="traffic-sources-section">
      <div className="section-header">Traffic Sources</div>
      <div className="traffic-sources-table-wrap">
        <table className="data-table traffic-sources-table">
          <colgroup>
            <col style={{ width: '180px' }} />
            <col />
            <col style={{ width: '100px' }} />
            <col style={{ width: '140px' }} />
            <col style={{ width: '90px' }} />
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
    </div>
  )
}
