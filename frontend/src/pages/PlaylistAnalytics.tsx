import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getPlaylist, getPlaylistVideos, getPlaylistVideoStats, getPlaylistAnalytics, getPlaylistTopVideosByViews, getVideosPublished, getPlaylistTrafficSources, getPlaylistTopVideosByTrafficSource } from '@/api'
import type { Video, VideoStats, AnalyticsRow, Playlist, TopVideo, TopVideoSortBy, PublishedVideo, TrafficSourceRow, TrafficSourceTopVideo } from '@/types'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import VideoStatsBar from '@/components/VideoStatsBar'
import VideoTable, { PAGE_SIZE } from '@/components/VideoTable'
import type { SortKey, SortDir } from '@/components/VideoTable'
import PeriodSelect, { last28Dates } from '@/components/PeriodSelect'
import { toTopVideoShape, last7Dates } from '@/lib/topVideos'
import AnalyticsChart from '@/components/AnalyticsChart'
import TopVideosList from '@/components/TopVideosList'
import VideoCarouselCard from '@/components/VideoCarouselCard'
import TopPerformersCard from '@/components/TopPerformersCard'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import TrafficSourceTopVideosPanel from '@/components/TrafficSourceTopVideosPanel'
import CommentsPanel from '@/components/CommentsPanel'
import '@/components/VideoMetaCard.css'
import './Analytics.css'

const RECENT_COUNT = 10

type Tab = 'analytics' | 'videos' | 'traffic-sources' | 'comments'

export default function PlaylistAnalytics() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useReplaceSearchParams()
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'
  const page = Math.max(1, Number(searchParams.get('page') ?? 1))
  const sortKey = (searchParams.get('sort_by') as SortKey) ?? 'published_at'
  const sortDir = (searchParams.get('sort_dir') as SortDir) ?? 'desc'
  const title = searchParams.get('title') ?? ''
  const startDate = searchParams.get('start_date') ?? ''
  const endDate = searchParams.get('end_date') ?? ''
  const contentType = searchParams.get('content_type') ?? ''
  const privacyStatus = searchParams.get('privacy_status') ?? ''

  const [playlist, setPlaylist] = useState<Playlist | null>(null)
  const [videos, setVideos] = useState<Video[]>([])
  const [total, setTotal] = useState(0)
  const [initialLoading, setInitialLoading] = useState(true)
  const [stats, setStats] = useState<VideoStats | null>(null)
  const analyticsStartDate = searchParams.has('analytics_start_date') ? searchParams.get('analytics_start_date')! : last28Dates()[0]
  const analyticsEndDate = searchParams.has('analytics_end_date') ? searchParams.get('analytics_end_date')! : last28Dates()[1]
  const analyticsTitle = searchParams.get('analytics_title') ?? ''
  const analyticsContentType = searchParams.get('analytics_content_type') ?? ''
  const analyticsPrivacyStatus = searchParams.get('analytics_privacy_status') ?? ''
  const rawTopVideosSortBy = searchParams.get('top_videos_sort_by')
  const topVideosSortBy: TopVideoSortBy = rawTopVideosSortBy === 'views' ? 'views' : 'watch_time'
  const [rows, setRows] = useState<AnalyticsRow[]>([])
  const [topVideos, setTopVideos] = useState<TopVideo[]>([])
  const [publishedVideos, setPublishedVideos] = useState<PublishedVideo[]>([])
  const [trafficSources, setTrafficSources] = useState<TrafficSourceRow[]>([])
  const [topVideosBySource, setTopVideosBySource] = useState<Record<string, TrafficSourceTopVideo[]>>({})
  const [recentVideos, setRecentVideos] = useState<TopVideo[]>([])
  const [recentShorts, setRecentShorts] = useState<TopVideo[]>([])
  const [topPerformingVideos, setTopPerformingVideos] = useState<TopVideo[]>([])
  const [topPerformingShorts, setTopPerformingShorts] = useState<TopVideo[]>([])

  useEffect(() => {
    if (!id) return
    getPlaylist(id).then((data: { item: Playlist }) => setPlaylist(data.item ?? null))
  }, [id])

  useEffect(() => {
    if (!id) return
    getPlaylistVideos(id, 1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'video', 'public')
      .then((data: { items: Video[] }) => setRecentVideos((data.items ?? []).map(toTopVideoShape)))
    getPlaylistVideos(id, 1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'short', 'public')
      .then((data: { items: Video[] }) => setRecentShorts((data.items ?? []).map(toTopVideoShape)))
    const [sevenStart, sevenEnd] = last7Dates()
    getPlaylistTopVideosByViews(id, 'views', sevenStart, sevenEnd, 'video', 'public')
      .then((data: { items: TopVideo[] }) => setTopPerformingVideos(data.items ?? []))
    getPlaylistTopVideosByViews(id, 'views', sevenStart, sevenEnd, 'short', 'public')
      .then((data: { items: TopVideo[] }) => setTopPerformingShorts(data.items ?? []))
  }, [id])

  useEffect(() => {
    if (!id) return
    getPlaylistVideos(id, page, PAGE_SIZE, sortKey, sortDir, title || undefined, startDate || undefined, endDate || undefined, contentType || undefined, privacyStatus || undefined)
      .then((data: { items: Video[]; total: number }) => {
        setVideos(data.items ?? [])
        setTotal(data.total ?? 0)
      })
      .finally(() => setInitialLoading(false))
  }, [id, page, sortKey, sortDir, title, startDate, endDate, contentType, privacyStatus])

  useEffect(() => {
    if (!id) return
    const params: Record<string, string> = {}
    if (analyticsStartDate) params.start_date = analyticsStartDate
    if (analyticsEndDate) params.end_date = analyticsEndDate
    if (analyticsContentType) params.content_type = analyticsContentType
    if (analyticsPrivacyStatus) params.privacy_status = analyticsPrivacyStatus
    if (analyticsTitle) params.title = analyticsTitle
    const sd = analyticsStartDate || undefined
    const ed = analyticsEndDate || undefined
    const ct = analyticsContentType || undefined
    const ps = analyticsPrivacyStatus || undefined
    const tt = analyticsTitle || undefined
    getPlaylistVideoStats(id, tt, sd, ed, ct, ps).then((data: VideoStats) => setStats(data))
    getPlaylistAnalytics(id, params).then((data: { items: AnalyticsRow[] }) => setRows(data.items ?? []))
    getVideosPublished(sd, ed, ct, ps, id, tt).then((data: { items: PublishedVideo[] }) => setPublishedVideos(data.items ?? []))
    getPlaylistTrafficSources(id, params).then((data: { items: TrafficSourceRow[] }) => setTrafficSources(data.items ?? []))
    getPlaylistTopVideosByTrafficSource(id, params).then((data: { items: Record<string, TrafficSourceTopVideo[]> }) => setTopVideosBySource(data.items ?? {}))
  }, [id, analyticsStartDate, analyticsEndDate, analyticsContentType, analyticsPrivacyStatus, analyticsTitle])

  useEffect(() => {
    if (!id) return
    const sd = analyticsStartDate || undefined
    const ed = analyticsEndDate || undefined
    const ct = analyticsContentType || undefined
    const ps = analyticsPrivacyStatus || undefined
    const tt = analyticsTitle || undefined
    getPlaylistTopVideosByViews(id, topVideosSortBy, sd, ed, ct, ps, tt).then((data: { items: TopVideo[] }) => setTopVideos(data.items ?? []))
  }, [id, analyticsStartDate, analyticsEndDate, analyticsContentType, analyticsPrivacyStatus, topVideosSortBy, analyticsTitle])

  const setPage = (p: number) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('page', String(p))
      return next
    })
  }

  const handleSort = (key: SortKey) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      const currentDir = (prev.get('sort_dir') as SortDir) ?? 'desc'
      const currentKey = prev.get('sort_by') ?? 'published_at'
      next.set('sort_by', key)
      next.set('sort_dir', currentKey === key && currentDir === 'desc' ? 'asc' : 'desc')
      next.set('page', '1')
      return next
    })
  }

  const handleFilterChange = (t: string, sd: string, ed: string, ct: string, ps: string) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      t ? next.set('title', t) : next.delete('title')
      sd ? next.set('start_date', sd) : next.delete('start_date')
      ed ? next.set('end_date', ed) : next.delete('end_date')
      ct ? next.set('content_type', ct) : next.delete('content_type')
      ps ? next.set('privacy_status', ps) : next.delete('privacy_status')
      next.set('page', '1')
      return next
    })
  }

  const updateAnalyticsParams = (updates: Record<string, string>) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        value ? next.set(key, value) : next.delete(key)
      }
      return next
    })
  }

  const updateAnalyticsDateParams = (updates: Record<string, string>) => {
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
      {playlist && (
        <div className="card video-meta-card">
          <div className="video-meta-thumb-wrap">
            {playlist.thumbnail_url
              ? <img src={playlist.thumbnail_url} alt="" className="video-meta-thumb" />
              : <div className="video-meta-thumb video-meta-thumb-placeholder" />}
          </div>
          <div className="video-meta-info">
            <div className="video-meta-title-row">
              <h1 className="video-meta-title">{playlist.title}</h1>
            </div>
            <div className="video-meta-stats">
              <div className="video-meta-stat">
                <span className="video-meta-stat-value">{playlist.total_views.toLocaleString()}</span>
                <span className="video-meta-stat-label">Views</span>
              </div>
              <div className="video-meta-stat-divider" />
              <div className="video-meta-stat">
                <span className="video-meta-stat-value">S${playlist.total_earnings_sgd.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                <span className="video-meta-stat-label">Earnings</span>
              </div>
              <div className="video-meta-stat-divider" />
              <div className="video-meta-stat">
                <span className="video-meta-stat-value">{playlist.item_count}</span>
                <span className="video-meta-stat-label">Videos</span>
              </div>
              <div className="video-meta-stat-divider" />
              <div className="video-meta-stat">
                <span className="video-meta-stat-value">{playlist.last_item_added?.slice(0, 10) ?? '—'}</span>
                <span className="video-meta-stat-label">Last Added</span>
              </div>
              <div className="video-meta-stat-divider" />
              <div className="video-meta-stat">
                <span className="video-meta-stat-value">{playlist.published_at?.slice(0, 10)}</span>
                <span className="video-meta-stat-label">Created</span>
              </div>
            </div>
          </div>
        </div>
      )}

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
          className={`tab${tab === 'videos' ? ' active' : ''}`}
          onClick={() => handleTabChange('videos')}
        >
          Videos {total > 0 && `(${total})`}
        </button>
        <button
          type="button"
          className={`tab${tab === 'comments' ? ' active' : ''}`}
          onClick={() => handleTabChange('comments')}
        >
          Comments
        </button>
      </div>

      {tab === 'comments' ? (
        <CommentsPanel scope={{ kind: 'playlist', playlistId: id! }} />
      ) : tab === 'videos' ? (
        <VideoTable
          videos={videos}
          total={total}
          initialLoading={initialLoading}
          page={page}
          sortKey={sortKey}
          sortDir={sortDir}
          title={title}
          startDate={startDate}
          endDate={endDate}
          contentType={contentType}
          privacyStatus={privacyStatus}
          onPageChange={setPage}
          onSort={handleSort}
          onFilterChange={handleFilterChange}
        />
      ) : (
        <>
          <div className="filter-bar">
            <PeriodSelect
              startDate={analyticsStartDate}
              endDate={analyticsEndDate}
              onChange={(sd, ed) => updateAnalyticsDateParams({ analytics_start_date: sd, analytics_end_date: ed })}
            />
            <label>
              Start
              <input type="date" value={analyticsStartDate} onChange={e => updateAnalyticsDateParams({ analytics_start_date: e.target.value })} />
            </label>
            <label>
              End
              <input type="date" value={analyticsEndDate} onChange={e => updateAnalyticsDateParams({ analytics_end_date: e.target.value })} />
            </label>
            <div className="filter-bar-sep" />
            <label>
              Title
              <input
                type="text"
                placeholder="Search…"
                value={analyticsTitle}
                onChange={e => updateAnalyticsParams({ analytics_title: e.target.value })}
              />
            </label>
            <div className="filter-bar-sep" />
            <label>
              Type
              <select value={analyticsContentType} onChange={e => updateAnalyticsParams({ analytics_content_type: e.target.value })}>
                <option value="">All</option>
                <option value="video">Video</option>
                <option value="short">Short</option>
              </select>
            </label>
            <div className="filter-bar-sep" />
            <label>
              Privacy
              <select value={analyticsPrivacyStatus} onChange={e => updateAnalyticsParams({ analytics_privacy_status: e.target.value })}>
                <option value="">All</option>
                <option value="public">Public</option>
                <option value="private">Private</option>
                <option value="unlisted">Unlisted</option>
              </select>
            </label>
          </div>

          {tab === 'analytics' ? (
            rows.length === 0 ? (
              <div className="chart-placeholder">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 3v18h18"/><path d="M7 16l4-4 4 4 4-8"/>
                </svg>
                <p>No data for this period</p>
              </div>
            ) : (
              <>
                {stats && <VideoStatsBar stats={stats} />}
                <div className="analytics-layout">
                  <div className="analytics-main">
                    <AnalyticsChart rows={rows} uploadedVideos={publishedVideos} />
                    <TopVideosList videos={topVideos} sortBy={topVideosSortBy} onSort={handleTopVideosSort} />
                  </div>
                  <div className="analytics-sidebar">
                    <TopPerformersCard title="Top Videos (Last 7 Days)" videos={topPerformingVideos} />
                    <TopPerformersCard title="Top Shorts (Last 7 Days)" videos={topPerformingShorts} />
                    <VideoCarouselCard title="Latest Videos" videos={recentVideos} />
                    <VideoCarouselCard title="Latest Shorts" videos={recentShorts} />
                  </div>
                </div>
              </>
            )
          ) : (
            trafficSources.length === 0 ? (
              <div className="chart-placeholder">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 3v18h18"/><path d="M7 16l4-4 4 4 4-8"/>
                </svg>
                <p>No data for this period</p>
              </div>
            ) : (
              <>
                {stats && <VideoStatsBar stats={stats} />}
                <TrafficSourceChart rows={trafficSources} uploadedVideos={publishedVideos} />
                <TrafficSourcesTable rows={trafficSources} />
                <TrafficSourceTopVideosPanel rows={trafficSources} bySource={topVideosBySource} />
              </>
            )
          )}
        </>
      )}
    </div>
  )
}
