import { Link } from 'react-router-dom'
import type { TopVideo, TopVideoSortBy } from '@/types'
import './TopVideosList.css'

interface Props {
  videos: TopVideo[]
  sortBy: TopVideoSortBy
  onSort: (sortBy: TopVideoSortBy) => void
}

export default function TopVideosList({ videos, sortBy, onSort }: Props) {
  if (videos.length === 0) return null

  const heading = sortBy === 'views' ? 'Top 10 Videos by Views' : 'Top 10 Videos by Watch Time'
  const handleSort = (value: TopVideoSortBy) => {
    if (value === sortBy) return
    onSort(value)
  }

  return (
    <div className="top-videos-section">
      <div className="section-header">{heading}</div>
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
              <th
                className="sortable"
                aria-sort={sortBy === 'views' ? 'descending' : 'none'}
                onClick={() => handleSort('views')}
              >
                Views{sortBy === 'views' ? ' ↓' : ''}
              </th>
              <th
                className="sortable"
                aria-sort={sortBy === 'watch_time' ? 'descending' : 'none'}
                onClick={() => handleSort('watch_time')}
              >
                Watch Time (hrs){sortBy === 'watch_time' ? ' ↓' : ''}
              </th>
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
