import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getTopVideosByViews, getVideos, getChannelTrafficSources, getSearchTerms, getVideosBySearchTerm } from '@/api'
import type { TopVideo, Video, TrafficSourceRow, SearchTermRow, SearchTermVideo } from '@/types'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import VideoCarouselCard from '@/components/VideoCarouselCard'
import TrafficSourceDonutCard from '@/components/TrafficSourceDonutCard'
import SearchTermsDonutCard from '@/components/SearchTermsDonutCard'
import SearchTermVideosDonutCard from '@/components/SearchTermVideosDonutCard'
import './Home.css'

const RECENT_COUNT = 10
// Show every video with views for the selected term, not just a "top" handful.
const ALL_VIDEOS_FOR_TERM_LIMIT = 1000

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
  const [topVideos, setTopVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [topShorts, setTopShorts] = useState<RequestState<TopVideo[]>>(pending([]))
  const [recentVideos, setRecentVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [trafficSourceRows, setTrafficSourceRows] = useState<RequestState<TrafficSourceRow[]>>(pending([]))
  const [searchTerms, setSearchTerms] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [videoTerm, setVideoTerm] = useState<string | null>(null)
  const [videosForTerm, setVideosForTerm] = useState<RequestState<SearchTermVideo[]>>(pending([]))

  useEffect(() => {
    let active = true
    const [startDate, endDate] = last28Dates()
    // Each card owns one request, so a slow or failing one never holds up the others.
    track(getTopVideosByViews('views', startDate, endDate, 'video', 'public')
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopVideos, () => active)
    track(getTopVideosByViews('views', startDate, endDate, 'short', 'public')
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopShorts, () => active)
    track(getVideos(1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, undefined, 'public')
      .then((data: { items: Video[] }) => (data.items ?? []).map(toTopVideoShape)), setRecentVideos, () => active)
    track(getChannelTrafficSources({ start_date: startDate, end_date: endDate, privacy_status: 'public' })
      .then((data: { items: TrafficSourceRow[] }) => data.items ?? []), setTrafficSourceRows, () => active)
    track(getSearchTerms({ startDate, endDate, privacyStatus: 'public' })
      .then((data: { items: SearchTermRow[] }) => data.items ?? []), setSearchTerms, () => active)
    return () => { active = false }
  }, [])

  // The video-by-term card owns its own term selection, defaulting to the top term once
  // the term list resolves. No content_type split here — videos and shorts are pooled.
  useEffect(() => {
    let active = true
    const [startDate, endDate] = last28Dates()
    const term = videoTerm || searchTerms.data[0]?.search_term
    if (!term) { setVideosForTerm({ data: [], loading: false, error: null }); return }
    track(getVideosBySearchTerm(term, { startDate, endDate, privacyStatus: 'public' }, ALL_VIDEOS_FOR_TERM_LIMIT)
      .then((data: { items: SearchTermVideo[] }) => data.items ?? []), setVideosForTerm, () => active, 'Could not load videos')
    return () => { active = false }
  }, [videoTerm, searchTerms.data])

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
        <VideoCarouselCard
          title="Top Videos (Last 28 Days)"
          videos={topVideos.data}
          loading={topVideos.loading}
          error={topVideos.error}
        />
        <VideoCarouselCard
          title="Top Shorts (Last 28 Days)"
          videos={topShorts.data}
          loading={topShorts.loading}
          error={topShorts.error}
        />
        <VideoCarouselCard
          title="Latest Uploads"
          videos={recentVideos.data}
          loading={recentVideos.loading}
          error={recentVideos.error}
        />
        <TrafficSourceDonutCard
          title="Traffic Sources (Last 28 Days)"
          rows={trafficSourceRows.data}
          loading={trafficSourceRows.loading}
          error={trafficSourceRows.error}
        />
        <SearchTermsDonutCard
          title="Top Search Terms (Last 28 Days)"
          rows={searchTerms.data}
          loading={searchTerms.loading}
          error={searchTerms.error}
        />
        <SearchTermVideosDonutCard
          title="Top Videos by Search Term (Last 28 Days)"
          terms={searchTerms.data}
          termsLoading={searchTerms.loading}
          selectedTerm={videoTerm || searchTerms.data[0]?.search_term || null}
          onSelectTerm={setVideoTerm}
          videos={videosForTerm.data}
          loading={videosForTerm.loading}
          error={videosForTerm.error}
        />
      </div>
    </div>
  )
}
