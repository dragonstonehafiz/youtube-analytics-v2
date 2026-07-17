import { Link } from 'react-router-dom'
import type { TopVideo } from '@/types'
import './TopPerformersCard.css'

interface Props {
  title: string
  videos: TopVideo[]
}

export default function TopPerformersCard({ title, videos }: Props) {
  if (videos.length === 0) return null

  return (
    <div className="card top-performers-card">
      <div className="section-header">{title}</div>
      <div className="top-performers-list">
        {videos.map((v, i) => (
          <Link key={v.id} to={`/analytics/videos/${v.id}`} className="top-performers-row">
            <span className="top-performers-rank">{i + 1}</span>
            {v.thumbnail_url
              ? <img src={v.thumbnail_url} alt="" className="top-performers-thumb" />
              : <div className="top-performers-thumb top-performers-thumb--placeholder" />
            }
            <span className="top-performers-title">{v.title}</span>
            <span className="top-performers-views">{v.period_views.toLocaleString()}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
