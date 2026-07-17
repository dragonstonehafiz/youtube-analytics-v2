import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { TrafficSourceRow, TrafficSourceTopVideo } from '@/types'
import { aggregateTrafficSourceTotals, formatTrafficSource, getTrafficSourceColor } from '@/lib/trafficSources'
import './TrafficSourceTopVideosPanel.css'

interface Props {
  rows: TrafficSourceRow[]
  bySource: Record<string, TrafficSourceTopVideo[]>
}

export default function TrafficSourceTopVideosPanel({ rows, bySource }: Props) {
  const order = aggregateTrafficSourceTotals(rows).map(t => t.traffic_source_type)
  const [selected, setSelected] = useState<string | null>(null)

  if (rows.length === 0) return null

  const activeType = selected && order.includes(selected) ? selected : order[0]
  const videos = bySource[activeType] ?? []

  return (
    <div className="card traffic-source-top-videos-card">
      <div className="traffic-source-top-videos-switcher">
        {order.map(type => (
          <button
            key={type}
            type="button"
            className={`traffic-source-top-videos-tab${type === activeType ? ' active' : ''}`}
            onClick={() => setSelected(type)}
          >
            <span className="traffic-source-top-videos-swatch" style={{ background: getTrafficSourceColor(type) }} />
            {formatTrafficSource(type)}
          </button>
        ))}
      </div>
      {videos.length === 0 ? (
        <p className="traffic-source-top-videos-empty">No videos for this source</p>
      ) : (
        <table className="data-table traffic-source-top-videos-table">
          <colgroup>
            <col style={{ width: '20px' }} />
            <col style={{ width: '64px' }} />
            <col />
            <col style={{ width: '100px' }} />
            <col style={{ width: '120px' }} />
          </colgroup>
          <thead>
            <tr>
              <th></th>
              <th></th>
              <th>Title</th>
              <th>Views</th>
              <th>Watch Time</th>
            </tr>
          </thead>
          <tbody>
            {videos.map((v, i) => (
              <tr key={v.id}>
                <td className="traffic-source-top-videos-rank">{i + 1}</td>
                <td>
                  {v.thumbnail_url
                    ? <img src={v.thumbnail_url} alt="" className="traffic-source-top-videos-thumb" />
                    : <div className="traffic-source-top-videos-thumb traffic-source-top-videos-thumb--placeholder" />
                  }
                </td>
                <td className="traffic-source-top-videos-title"><Link to={`/analytics/videos/${v.id}`}>{v.title}</Link></td>
                <td>{v.views.toLocaleString()}</td>
                <td>{(v.watch_time_minutes / 60).toLocaleString(undefined, { maximumFractionDigits: 1 })}h</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
