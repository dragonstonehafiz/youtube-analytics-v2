import { useEffect, useState } from 'react'
import { getVideoStats, getChannelAnalytics, getTopVideosByViews, getVideosPublished, getVideos, getChannelTrafficSources, getTopVideosByTrafficSource } from '@/api'
import type { AnalyticsRow, VideoStats, TopVideo, PublishedVideo, Video, TrafficSourceRow, TrafficSourceTopVideo } from '@/types'
import PeriodSelect, { last28Dates } from '@/components/PeriodSelect'
import { toTopVideoShape, last7Dates } from '@/lib/topVideos'
import VideoStatsBar from '@/components/VideoStatsBar'
import AnalyticsChart from '@/components/AnalyticsChart'
import TopVideosList from '@/components/TopVideosList'
import VideoCarouselCard from '@/components/VideoCarouselCard'
import TopPerformersCard from '@/components/TopPerformersCard'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import TrafficSourceTopVideosPanel from '@/components/TrafficSourceTopVideosPanel'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import './Analytics.css'

const RECENT_COUNT = 10

type Tab = 'analytics' | 'traffic-sources'

export default function Analytics() {
  const [searchParams, setSearchParams] = useReplaceSearchParams()
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'
  const [rows, setRows] = useState<AnalyticsRow[]>([])
  const startDate = searchParams.has('start_date') ? searchParams.get('start_date')! : last28Dates()[0]
  const endDate = searchParams.has('end_date') ? searchParams.get('end_date')! : last28Dates()[1]
  const contentType = searchParams.get('content_type') ?? ''
  const privacyStatus = searchParams.get('privacy_status') ?? ''
  const [stats, setStats] = useState<VideoStats | null>(null)
  const [topVideos, setTopVideos] = useState<TopVideo[]>([])
  const [publishedVideos, setPublishedVideos] = useState<PublishedVideo[]>([])
  const [recentVideos, setRecentVideos] = useState<TopVideo[]>([])
  const [recentShorts, setRecentShorts] = useState<TopVideo[]>([])
  const [topPerformingVideos, setTopPerformingVideos] = useState<TopVideo[]>([])
  const [topPerformingShorts, setTopPerformingShorts] = useState<TopVideo[]>([])
  const [trafficSources, setTrafficSources] = useState<TrafficSourceRow[]>([])
  const [topVideosBySource, setTopVideosBySource] = useState<Record<string, TrafficSourceTopVideo[]>>({})

  useEffect(() => {
    getVideos(1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'video', 'public')
      .then((data: { items: Video[] }) => setRecentVideos((data.items ?? []).map(toTopVideoShape)))
    getVideos(1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'short', 'public')
      .then((data: { items: Video[] }) => setRecentShorts((data.items ?? []).map(toTopVideoShape)))
    const [sevenStart, sevenEnd] = last7Dates()
    getTopVideosByViews(sevenStart, sevenEnd, 'video', 'public')
      .then((data: { items: TopVideo[] }) => setTopPerformingVideos(data.items ?? []))
    getTopVideosByViews(sevenStart, sevenEnd, 'short', 'public')
      .then((data: { items: TopVideo[] }) => setTopPerformingShorts(data.items ?? []))
  }, [])

  useEffect(() => {
    const params: Record<string, string> = {}
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    if (contentType) params.content_type = contentType
    if (privacyStatus) params.privacy_status = privacyStatus
    const sd = startDate || undefined
    const ed = endDate || undefined
    const ct = contentType || undefined
    const ps = privacyStatus || undefined
    getVideoStats(undefined, sd, ed, ct, ps).then((data: VideoStats) => setStats(data))
    getChannelAnalytics(params).then((data: { items: AnalyticsRow[] }) => setRows(data.items ?? []))
    getTopVideosByViews(sd, ed, ct, ps).then((data: { items: TopVideo[] }) => setTopVideos(data.items ?? []))
    getVideosPublished(sd, ed, ct, ps).then((data: { items: PublishedVideo[] }) => setPublishedVideos(data.items ?? []))
    getChannelTrafficSources(params).then((data: { items: TrafficSourceRow[] }) => setTrafficSources(data.items ?? []))
    getTopVideosByTrafficSource(params).then((data: { items: Record<string, TrafficSourceTopVideo[]> }) => setTopVideosBySource(data.items ?? {}))
  }, [startDate, endDate, contentType, privacyStatus])

  const updateParams = (updates: Record<string, string>) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        value ? next.set(key, value) : next.delete(key)
      }
      return next
    })
  }

  const updateDateParams = (updates: Record<string, string>) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        next.set(key, value)
      }
      return next
    })
  }

  const handleTabChange = (t: Tab) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('tab', t)
      return next
    })
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Analytics</h1>
      </div>

      <div className="tabs">
        <button
          type="button"
          className={`tab${tab === 'analytics' ? ' active' : ''}`}
          onClick={() => handleTabChange('analytics')}
        >
          Analytics
        </button>
        <button
          type="button"
          className={`tab${tab === 'traffic-sources' ? ' active' : ''}`}
          onClick={() => handleTabChange('traffic-sources')}
        >
          Traffic Sources
        </button>
      </div>

      <div className="filter-bar">
        <PeriodSelect
          startDate={startDate}
          endDate={endDate}
          onChange={(sd, ed) => updateDateParams({ start_date: sd, end_date: ed })}
        />
        <label>
          Start
          <input type="date" value={startDate} onChange={e => updateDateParams({ start_date: e.target.value })} />
        </label>
        <label>
          End
          <input type="date" value={endDate} onChange={e => updateDateParams({ end_date: e.target.value })} />
        </label>
        <div className="filter-bar-sep" />
        <label>
          Type
          <select value={contentType} onChange={e => updateParams({ content_type: e.target.value })}>
            <option value="">All</option>
            <option value="video">Video</option>
            <option value="short">Short</option>
          </select>
        </label>
        <div className="filter-bar-sep" />
        <label>
          Privacy
          <select value={privacyStatus} onChange={e => updateParams({ privacy_status: e.target.value })}>
            <option value="">All</option>
            <option value="public">Public</option>
            <option value="private">Private</option>
            <option value="unlisted">Unlisted</option>
          </select>
        </label>
      </div>

      {stats && <VideoStatsBar stats={stats} />}

      {tab === 'analytics' ? (
        <>
          <div className="analytics-layout">
            <div className="analytics-main">
              <AnalyticsChart rows={rows} uploadedVideos={publishedVideos} />
              <TopVideosList videos={topVideos} />
            </div>
            <div className="analytics-sidebar">
              <TopPerformersCard title="Top Videos (Last 7 Days)" videos={topPerformingVideos} />
              <TopPerformersCard title="Top Shorts (Last 7 Days)" videos={topPerformingShorts} />
              <VideoCarouselCard title="Latest Videos" videos={recentVideos} />
              <VideoCarouselCard title="Latest Shorts" videos={recentShorts} />
            </div>
          </div>
        </>
      ) : (
        <>
          <TrafficSourceChart rows={trafficSources} uploadedVideos={publishedVideos} />
          <TrafficSourcesTable rows={trafficSources} />
          <TrafficSourceTopVideosPanel rows={trafficSources} bySource={topVideosBySource} />
        </>
      )}
    </div>
  )
}
