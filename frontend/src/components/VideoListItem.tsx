import { Link } from 'react-router-dom'

interface VideoListItemProps {
  id: string
  title: string
  published_at?: string
  thumbnail_url?: string | null
  content_type?: string
  view_count?: number
}

export default function VideoListItem({ id, title, published_at, thumbnail_url, content_type, view_count }: VideoListItemProps) {
  return (
    <Link to={`/analytics/videos/${id}`} className="video-list-item">
      {thumbnail_url ? (
        <img src={thumbnail_url} alt="" />
      ) : (
        <div style={{ width: 96, height: 54, borderRadius: 6, background: 'var(--border)', flexShrink: 0 }} />
      )}
      <div className="video-list-item-info">
        <div className="video-list-item-title">{title}</div>
        <div className="video-list-item-meta">
          {published_at && <span>{published_at.slice(0, 10)}</span>}
          {content_type && (
            <span className={`badge${content_type === 'short' ? ' short' : ''}`}>
              {content_type === 'short' ? 'Short' : 'Video'}
            </span>
          )}
          {view_count != null && <span>{view_count.toLocaleString()} views</span>}
        </div>
      </div>
    </Link>
  )
}
