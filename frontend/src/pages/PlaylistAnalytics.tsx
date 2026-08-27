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
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import AsyncCard from '@/components/AsyncCard'
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

type Tab = 'analytics' | 'traffic-sources' | 'comments' | 'videos'

interface VideoPage {
  items: Video[]
  total: number
}

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

  const [playlist, setPlaylist] = useState<RequestState<Playlist | null>>(pending(null))
  const [listing, setListing] = useState<RequestState<VideoPage>>(pending({ items: [], total: 0 }))
  const [stats, setStats] = useState<RequestState<VideoStats | null>>(pending(null))
  const analyticsStartDate = searchParams.has('analytics_start_date') ? searchParams.get('analytics_start_date')! : last28Dates()[0]
  const analyticsEndDate = searchParams.has('analytics_end_date') ? searchParams.get('analytics_end_date')! : last28Dates()[1]
  const analyticsTitle = searchParams.get('analytics_title') ?? ''
  const analyticsContentType = searchParams.get('analytics_content_type') ?? ''
  const analyticsPrivacyStatus = searchParams.get('analytics_privacy_status') ?? ''
  const rawTopVideosSortBy = searchParams.get('top_videos_sort_by')
  const topVideosSortBy: TopVideoSortBy = rawTopVideosSortBy === 'views' ? 'views' : 'watch_time'
  const [rows, setRows] = useState<RequestState<AnalyticsRow[]>>(pending([]))
  const [topVideos, setTopVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [publishedVideos, setPublishedVideos] = useState<RequestState<PublishedVideo[]>>(pending([]))
  const [trafficSources, setTrafficSources] = useState<RequestState<TrafficSourceRow[]>>(pending([]))
  const [topVideosBySource, setTopVideosBySource] = useState<RequestState<Record<string, TrafficSourceTopVideo[]>>>(pending({}))
  const [recentVideos, setRecentVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [recentShorts, setRecentShorts] = useState<RequestState<TopVideo[]>>(pending([]))
  const [topPerformingVideos, setTopPerformingVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [topPerformingShorts, setTopPerformingShorts] = useState<RequestState<TopVideo[]>>(pending([]))

  useEffect(() => {
    if (!id) return
    let active = true
    track(getPlaylist(id)
      .then((data: { item: Playlist }) => data.item ?? null), setPlaylist, () => active, 'Could not load this playlist')
    return () => { active = false }
  }, [id])

  // The four sidebar cards read fixed periods, so they never reload with the page filters.
  useEffect(() => {
    if (!id) return
    let active = true
    track(getPlaylistVideos(id, 1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'video', 'public')
      .then((data: { items: Video[] }) => (data.items ?? []).map(toTopVideoShape)), setRecentVideos, () => active)
    track(getPlaylistVideos(id, 1, RECENT_COUNT, 'published_at', 'desc', undefined, undefined, undefined, 'short', 'public')
      .then((data: { items: Video[] }) => (data.items ?? []).map(toTopVideoShape)), setRecentShorts, () => active)
    const [sevenStart, sevenEnd] = last7Dates()
    track(getPlaylistTopVideosByViews(id, 'views', sevenStart, sevenEnd, 'video', 'public')
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopPerformingVideos, () => active)
    track(getPlaylistTopVideosByViews(id, 'views', sevenStart, sevenEnd, 'short', 'public')
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopPerformingShorts, () => active)
    return () => { active = false }
  }, [id])

  useEffect(() => {
    if (!id) return
    let active = true
    track(
      getPlaylistVideos(id, page, PAGE_SIZE, sortKey, sortDir, title || undefined, startDate || undefined, endDate || undefined, contentType || undefined, privacyStatus || undefined)
        .then((data: { items: Video[]; total: number }) => ({ items: data.items ?? [], total: data.total ?? 0 })),
      setListing,
      () => active,
      'Could not load videos',
    )
    return () => { active = false }
  }, [id, page, sortKey, sortDir, title, startDate, endDate, contentType, privacyStatus])

  // One filter change starts five requests, each owning the state of the card it feeds.
  useEffect(() => {
    if (!id) return
    let active = true
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
    track(getPlaylistVideoStats(id, tt, sd, ed, ct, ps)
      .then((data: VideoStats) => data), setStats, () => active, 'Could not load statistics')
    track(getPlaylistAnalytics(id, params)
      .then((data: { items: AnalyticsRow[] }) => data.items ?? []), setRows, () => active, 'Could not load analytics')
    track(getVideosPublished(sd, ed, ct, ps, id, tt)
      .then((data: { items: PublishedVideo[] }) => data.items ?? []), setPublishedVideos, () => active, 'Could not load uploads')
    track(getPlaylistTrafficSources(id, params)
      .then((data: { items: TrafficSourceRow[] }) => data.items ?? []), setTrafficSources, () => active, 'Could not load traffic sources')
    track(getPlaylistTopVideosByTrafficSource(id, params)
      .then((data: { items: Record<string, TrafficSourceTopVideo[]> }) => data.items ?? {}), setTopVideosBySource, () => active, 'Could not load traffic sources')
    return () => { active = false }
  }, [id, analyticsStartDate, analyticsEndDate, analyticsContentType, analyticsPrivacyStatus, analyticsTitle])

  // The sortable top-video table reloads on its own sort change, and on nothing else's.
  useEffect(() => {
    if (!id) return
    let active = true
    const sd = analyticsStartDate || undefined
    const ed = analyticsEndDate || undefined
    const ct = analyticsContentType || undefined
    const ps = analyticsPrivacyStatus || undefined
    const tt = analyticsTitle || undefined
    track(getPlaylistTopVideosByViews(id, topVideosSortBy, sd, ed, ct, ps, tt)
      .then((data: { items: TopVideo[] }) => data.items ?? []), setTopVideos, () => active, 'Could not load top videos')
    return () => { active = false }
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
      <AsyncCard
        loading={playlist.loading}
        error={playlist.error}
        empty={!playlist.data}
        emptyMessage="Playlist not found."
        className="video-meta-card"
        bodyClassName="video-meta-card-body"
      >
        {playlist.data && (
          <>
            <div className="video-meta-thumb-wrap">
              {playlist.data.thumbnail_url
                ? <img src={playlist.data.thumbnail_url} alt="" className="video-meta-thumb" />
                : <div className="video-meta-thumb video-meta-thumb-placeholder" />}
            </div>
            <div className="video-meta-info">
              <div className="video-meta-title-row">
                <h1 className="video-meta-title">{playlist.data.title}</h1>
              </div>
              <div className="video-meta-stats">
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{playlist.data.total_views.toLocaleString()}</span>
                  <span className="video-meta-stat-label">Views</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">S${playlist.data.total_earnings_sgd.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  <span className="video-meta-stat-label">Earnings</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{playlist.data.item_count}</span>
                  <span className="video-meta-stat-label">Videos</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{playlist.data.last_item_added?.slice(0, 10) ?? '—'}</span>
                  <span className="video-meta-stat-label">Last Added</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{playlist.data.published_at?.slice(0, 10)}</span>
                  <span className="video-meta-stat-label">Created</span>
                </div>
              </div>
            </div>
          </>
        )}
      </AsyncCard>

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
        <button
          type="button"
          className={`tab${tab === 'videos' ? ' active' : ''}`}
          onClick={() => handleTabChange('videos')}
        >
          Videos {listing.data.total > 0 && `(${listing.data.total})`}
        </button>
      </div>

      {tab === 'comments' ? (
        <CommentsPanel scope={{ kind: 'playlist', playlistId: id! }} />
      ) : tab === 'videos' ? (
        <VideoTable
          videos={listing.data.items}
          total={listing.data.total}
          loading={listing.loading}
          error={listing.error}
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
        </>
      )}
    </div>
  )
}
