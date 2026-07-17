import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getTopVideosByViews, getVideos, getChannelTrafficSources } from '@/api'
import type { TopVideo, Video, TrafficSourceRow } from '@/types'
import VideoCarouselCard from '@/components/VideoCarouselCard'
import TrafficSourceDonutCard from '@/components/TrafficSourceDonutCard'
import './Home.css'

const RECENT_COUNT = 10

function last28Dates(): [string, string] {
  const today = new Date()
  const end = today.toISOString().slice(0, 10)
  const start = new Date(today.getTime() - 28 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  return [start, end]
}

function toTopVideoShape(v: Video): TopVideo {
  return {
    id: v.id,
    title: v.title,
    published_at: v.published_at,
    thumbnail_url: v.thumbnail_url,
    content_type: v.content_type,
    period_views: v.view_count,
    period_watch_time_hours: v.total_watch_time_hours,
    period_earnings_sgd: v.total_revenue_sgd,
  }
}

const NAV_ITEMS = [
  {
    to: '/videos',
    label: 'Videos',
    icon: (
      <svg viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="18" rx="2"/><path d="M10 8l6 4-6 4V8z"/></svg>
    ),
  },
  {
    to: '/playlists',
    label: 'Playlists',
    icon: (
      <svg viewBox="0 0 24 24"><path d="M3 5h18M3 10h18M3 15h12M3 20h12"/><circle cx="19" cy="17.5" r="3"/><path d="M18 10v5"/></svg>
    ),
  },
  {
    to: '/analytics',
    label: 'Analytics',
    icon: (
      <svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M7 16l4-4 4 4 4-8"/></svg>
    ),
  },
]

export default function Home() {
  const [topVideos, setTopVideos] = useState<TopVideo[]>([])
  const [topShorts, setTopShorts] = useState<TopVideo[]>([])
  const [recentVideos, setRecentVideos] = useState<TopVideo[]>([])
  const [trafficSourceRows, setTrafficSourceRows] = useState<TrafficSourceRow[]>([])

  useEffect(() => {
    const [startDate, endDate] = last28Dates()
    getTopVideosByViews(startDate, endDate, 'video', 'public')
      .then((data: { items: TopVideo[] }) => setTopVideos(data.items ?? []))
    getTopVideosByViews(startDate, endDate, 'short', 'public')
      .then((data: { items: TopVideo[] }) => setTopShorts(data.items ?? []))
    getVideos(1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, undefined, 'public')
      .then((data: { items: Video[] }) => setRecentVideos((data.items ?? []).map(toTopVideoShape)))
    getChannelTrafficSources({ start_date: startDate, end_date: endDate, privacy_status: 'public' })
      .then((data: { items: TrafficSourceRow[] }) => setTrafficSourceRows(data.items ?? []))
  }, [])

  return (
    <div className="home">
      <div className="page-header">
        <h1>Dashboard</h1>
      </div>
      <div className="home-nav">
        {NAV_ITEMS.map(item => (
          <Link key={item.to} to={item.to} className="home-nav-card">
            <div className="home-nav-icon">{item.icon}</div>
            <span className="home-nav-label">{item.label}</span>
          </Link>
        ))}
      </div>
      <div className="home-carousels">
        <VideoCarouselCard title="Top Videos (Last 28 Days)" videos={topVideos} />
        <VideoCarouselCard title="Top Shorts (Last 28 Days)" videos={topShorts} />
        <VideoCarouselCard title="Latest Uploads" videos={recentVideos} />
        <TrafficSourceDonutCard title="Traffic Sources (Last 28 Days)" rows={trafficSourceRows} />
      </div>
    </div>
  )
}
