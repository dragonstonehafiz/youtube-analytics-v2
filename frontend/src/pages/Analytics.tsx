import { useEffect, useState } from 'react'
import { getVideoStats, getChannelAnalytics, getTopVideosByViews, getVideosPublished, getVideos, getChannelTrafficSources, getTopVideosByTrafficSource } from '@/api'
import type { AnalyticsRow, VideoStats, TopVideo, TopVideoSortBy, PublishedVideo, Video, TrafficSourceRow, TrafficSourceTopVideo } from '@/types'
import PeriodSelect, { last28Dates } from '@/components/PeriodSelect'
import { toTopVideoShape, last7Dates } from '@/lib/topVideos'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import VideoStatsBar from '@/components/VideoStatsBar'
import AnalyticsChart from '@/components/AnalyticsChart'
import TopVideosList from '@/components/TopVideosList'
import VideoCarouselCard from '@/components/VideoCarouselCard'
import TopPerformersCard from '@/components/TopPerformersCard'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import TrafficSourceTopVideosPanel from '@/components/TrafficSourceTopVideosPanel'
import CommentsPanel from '@/components/CommentsPanel'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import './Analytics.css'

const RECENT_COUNT = 10

type Tab = 'analytics' | 'traffic-sources' | 'comments'

export default function Analytics() {
  const [searchParams, setSearchParams] = useReplaceSearchParams()
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'
  const [rows, setRows] = useState<RequestState<AnalyticsRow[]>>(pending([]))
  const startDate = searchParams.has('start_date') ? searchParams.get('start_date')! : last28Dates()[0]
  const endDate = searchParams.has('end_date') ? searchParams.get('end_date')! : last28Dates()[1]
  const title = searchParams.get('title') ?? ''
  const contentType = searchParams.get('content_type') ?? ''
  const privacyStatus = searchParams.get('privacy_status') ?? ''
  const rawTopVideosSortBy = searchParams.get('top_videos_sort_by')
  const topVideosSortBy: TopVideoSortBy = rawTopVideosSortBy === 'views' ? 'views' : 'watch_time'
  const [stats, setStats] = useState<RequestState<VideoStats | null>>(pending(null))
  const [topVideos, setTopVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [publishedVideos, setPublishedVideos] = useState<RequestState<PublishedVideo[]>>(pending([]))
  const [recentVideos, setRecentVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [recentShorts, setRecentShorts] = useState<RequestState<TopVideo[]>>(pending([]))
  const [topPerformingVideos, setTopPerformingVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [topPerformingShorts, setTopPerformingShorts] = useState<RequestState<TopVideo[]>>(pending([]))
  const [trafficSources, setTrafficSources] = useState<RequestState<TrafficSourceRow[]>>(pending([]))
  const [topVideosBySource, setTopVideosBySource] = useState<RequestState<Record<string, TrafficSourceTopVideo[]>>>(pending({}))

  // The four sidebar cards read fixed periods, so they never reload with the page filters.
  useEffect(() => {
    let active = true
    track(getVideos(1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'video', 'public')
      .then((data: { items: Video[] }) => (data.items ?? []).map(toTopVideoShape)), setRecentVideos, () => active)
    track(getVideos(1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'short', 'public')
      .then((data: { items: Video[] }) => (data.items ?? []).map(toTopVideoShape)), setRecentShorts, () => active)
    const [sevenStart, sevenEnd] = last7Dates()
    track(getTopVideosByViews('views', sevenStart, sevenEnd, 'video', 'public')
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopPerformingVideos, () => active)
    track(getTopVideosByViews('views', sevenStart, sevenEnd, 'short', 'public')
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopPerformingShorts, () => active)
    return () => { active = false }
  }, [])

  // One filter change starts five requests, each owning the state of the card it feeds.
  useEffect(() => {
    let active = true
    const params: Record<string, string> = {}
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    if (contentType) params.content_type = contentType
    if (privacyStatus) params.privacy_status = privacyStatus
    if (title) params.title = title
    const sd = startDate || undefined
    const ed = endDate || undefined
    const ct = contentType || undefined
    const ps = privacyStatus || undefined
    const tt = title || undefined
    track(getVideoStats(tt, sd, ed, ct, ps)
      .then((data: VideoStats) => data), setStats, () => active, 'Could not load statistics')
    track(getChannelAnalytics(params)
      .then((data: { items: AnalyticsRow[] }) => data.items ?? []), setRows, () => active, 'Could not load analytics')
    track(getVideosPublished(sd, ed, ct, ps, undefined, tt)
      .then((data: { items: PublishedVideo[] }) => data.items ?? []), setPublishedVideos, () => active, 'Could not load uploads')
    track(getChannelTrafficSources(params)
      .then((data: { items: TrafficSourceRow[] }) => data.items ?? []), setTrafficSources, () => active, 'Could not load traffic sources')
    track(getTopVideosByTrafficSource(params)
      .then((data: { items: Record<string, TrafficSourceTopVideo[]> }) => data.items ?? {}), setTopVideosBySource, () => active, 'Could not load traffic sources')
    return () => { active = false }
  }, [startDate, endDate, contentType, privacyStatus, title])

  // The sortable top-video table reloads on its own sort change, and on nothing else's.
  useEffect(() => {
    let active = true
    const sd = startDate || undefined
    const ed = endDate || undefined
    const ct = contentType || undefined
    const ps = privacyStatus || undefined
    const tt = title || undefined
    track(getTopVideosByViews(topVideosSortBy, sd, ed, ct, ps, tt)
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopVideos, () => active, 'Could not load top videos')
    return () => { active = false }
  }, [startDate, endDate, contentType, privacyStatus, topVideosSortBy, title])

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

  const handleTopVideosSort = (sortBy: TopVideoSortBy) => {
    if (sortBy === topVideosSortBy) return
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('top_videos_sort_by', sortBy)
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
    <div className="page analytics-page">
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
        <button
          type="button"
          className={`tab${tab === 'comments' ? ' active' : ''}`}
          onClick={() => handleTabChange('comments')}
        >
          Comments
        </button>
      </div>

      {/* Comments filter on their own publication dates and carry their own filter bar,
          so the shared analytics date range does not apply to that tab. */}
      {tab !== 'comments' && (
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
          Title
          <input
            type="text"
            placeholder="Search…"
            value={title}
            onChange={e => updateParams({ title: e.target.value })}
          />
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
      )}

      {tab === 'comments' ? (
        <CommentsPanel scope={{ kind: 'channel' }} />
      ) : tab === 'analytics' ? (
        <>
          <VideoStatsBar stats={stats.data} loading={stats.loading} error={stats.error} />
          <div className="analytics-layout">
            <div className="analytics-main">
              <AnalyticsChart
                rows={rows.data}
                uploadedVideos={publishedVideos.data}
                loading={rows.loading || publishedVideos.loading}
                error={rows.error ?? publishedVideos.error}
              />
              <TopVideosList
                videos={topVideos.data}
                sortBy={topVideosSortBy}
                onSort={handleTopVideosSort}
                loading={topVideos.loading}
                error={topVideos.error}
              />
            </div>
            <div className="analytics-sidebar">
              <TopPerformersCard
                title="Top Videos (Last 7 Days)"
                videos={topPerformingVideos.data}
                loading={topPerformingVideos.loading}
                error={topPerformingVideos.error}
              />
              <TopPerformersCard
                title="Top Shorts (Last 7 Days)"
                videos={topPerformingShorts.data}
                loading={topPerformingShorts.loading}
                error={topPerformingShorts.error}
              />
              <VideoCarouselCard
                title="Latest Videos"
                videos={recentVideos.data}
                loading={recentVideos.loading}
                error={recentVideos.error}
              />
              <VideoCarouselCard
                title="Latest Shorts"
                videos={recentShorts.data}
                loading={recentShorts.loading}
                error={recentShorts.error}
              />
            </div>
          </div>
        </>
      ) : (
        <>
          <VideoStatsBar stats={stats.data} loading={stats.loading} error={stats.error} />
          <TrafficSourceChart
            rows={trafficSources.data}
            uploadedVideos={publishedVideos.data}
            loading={trafficSources.loading || publishedVideos.loading}
            error={trafficSources.error ?? publishedVideos.error}
          />
          <TrafficSourcesTable
            rows={trafficSources.data}
            loading={trafficSources.loading}
            error={trafficSources.error}
          />
          <TrafficSourceTopVideosPanel
            rows={trafficSources.data}
            bySource={topVideosBySource.data}
            loading={trafficSources.loading || topVideosBySource.loading}
            error={trafficSources.error ?? topVideosBySource.error}
          />
        </>
      )}
    </div>
  )
}
