import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { TopVideo } from '@/types'
import './VideoCarouselCard.css'

interface Props {
  title: string
  videos: TopVideo[]
}

function timeSincePublished(publishedAt: string): string {
  const start = new Date(publishedAt)
  const now = new Date()
  let years = now.getUTCFullYear() - start.getUTCFullYear()
  let months = now.getUTCMonth() - start.getUTCMonth()
  let days = now.getUTCDate() - start.getUTCDate()
  if (days < 0) {
    months -= 1
    days += new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 0)).getUTCDate()
  }
  if (months < 0) {
    years -= 1
    months += 12
  }
  const parts: string[] = []
  if (years > 0) parts.push(`${years} ${years === 1 ? 'year' : 'years'}`)
  if (months > 0) parts.push(`${months} ${months === 1 ? 'month' : 'months'}`)
  if (days > 0 || parts.length === 0) parts.push(`${days} ${days === 1 ? 'day' : 'days'}`)
  return `${parts.join(', ')} ago`
}

export default function VideoCarouselCard({ title, videos }: Props) {
  const [index, setIndex] = useState(0)

  if (videos.length === 0) return null

  const video = videos[Math.min(index, videos.length - 1)]

  return (
    <div className="video-carousel card">
      <div className="section-header">{title}</div>

      <Link to={`/analytics/videos/${video.id}`} className="video-carousel-thumb-wrap">
        {video.thumbnail_url
          ? <img src={video.thumbnail_url} alt="" className="video-carousel-thumb" />
          : <div className="video-carousel-thumb video-carousel-thumb--placeholder" />}
        <div className="video-carousel-overlay">
          <span className="video-carousel-title">{video.title}</span>
        </div>
      </Link>

      <div className="video-carousel-age">Uploaded {timeSincePublished(video.published_at)}</div>

      <div className="video-carousel-stats">
        <div className="video-carousel-stat-row">
          <span className="video-carousel-stat-label">Views</span>
          <span className="video-carousel-stat-value">{video.period_views.toLocaleString()}</span>
        </div>
        <div className="video-carousel-stat-row">
          <span className="video-carousel-stat-label">Watch Time (hours)</span>
          <span className="video-carousel-stat-value">
            {video.period_watch_time_hours.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
        </div>
        <div className="video-carousel-stat-row">
          <span className="video-carousel-stat-label">Earnings (SGD)</span>
          <span className="video-carousel-stat-value">
            S${video.period_earnings_sgd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>
      </div>

      <div className="video-carousel-nav">
        <button
          type="button"
          className="video-carousel-arrow"
          onClick={() => setIndex(i => i - 1)}
          disabled={index <= 0}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <span className="video-carousel-page">{index + 1}/{videos.length}</span>
        <button
          type="button"
          className="video-carousel-arrow"
          onClick={() => setIndex(i => i + 1)}
          disabled={index >= videos.length - 1}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
      </div>
    </div>
  )
}
