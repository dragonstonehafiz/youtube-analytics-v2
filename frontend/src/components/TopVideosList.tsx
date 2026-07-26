import { Link } from 'react-router-dom'
import type { TopVideo } from '@/types'
import './TopVideosList.css'

interface Props {
  videos: TopVideo[]
}

export default function TopVideosList({ videos }: Props) {
  if (videos.length === 0) return null

  return (
    <div className="top-videos-section">
      <div className="section-header">Top 10 Videos by Watch Time</div>
      <div className="top-videos-table-wrap">
        <table className="data-table top-videos-table">
          <colgroup>
            <col className="top-videos-col-thumb" />
            <col />
            <col className="top-videos-col-date" />
            <col className="top-videos-col-views" />
            <col className="top-videos-col-watch-time" />
            <col className="top-videos-col-earnings" />
          </colgroup>
          <thead>
            <tr>
              <th></th>
              <th>Title</th>
              <th>Upload Date</th>
              <th>Views</th>
              <th>Watch Time (hrs)</th>
              <th>Estimated Earnings (SGD)</th>
            </tr>
          </thead>
          <tbody>
            {videos.map((v, i) => (
              <tr key={v.id}>
                <td>
                  {v.thumbnail_url
                    ? <img src={v.thumbnail_url} alt="" className="top-videos-thumb" />
                    : <div className="top-videos-thumb top-videos-thumb--placeholder">{i + 1}</div>
                  }
                </td>
                <td className="top-videos-title"><Link to={`/analytics/videos/${v.id}`}>{v.title}</Link></td>
                <td>{v.published_at.slice(0, 10)}</td>
                <td>{v.period_views.toLocaleString()}</td>
                <td>{v.period_watch_time_hours.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td>S${v.period_earnings_sgd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
