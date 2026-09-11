import { useEffect, useState } from 'react'
import { getVideoStats, getChannelAnalytics, getTopVideosByViews, getVideosPublished, getVideos, getChannelTrafficSources, getTopVideosByTrafficSource, getSearchTerms, getVideosBySearchTerm, getRelatedVideoReferrers, getRelatedVideoDestinations } from '@/api'
import type { AnalyticsRow, VideoStats, TopVideo, TopVideoSortBy, PublishedVideo, Video, TrafficSourceRow, TrafficSourceTopVideo, SearchTermRow, SearchTermVideo, RelatedReferrersResponse, RelatedDestinationRow } from '@/types'
import PeriodSelect, { last28Dates } from '@/components/PeriodSelect'
import { toTopVideoShape, last7Dates } from '@/lib/topVideos'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import { useReconciledSelection } from '@/hooks/useReconciledSelection'
import VideoStatsBar from '@/components/VideoStatsBar'
import AnalyticsChart from '@/components/AnalyticsChart'
import TopVideosList from '@/components/TopVideosList'
import VideoCarouselCard from '@/components/VideoCarouselCard'
import TopPerformersCard from '@/components/TopPerformersCard'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import TrafficSourceTopVideosPanel from '@/components/TrafficSourceTopVideosPanel'
import SearchTermsDonutCard from '@/components/SearchTermsDonutCard'
import SearchTermVideosDonutCard from '@/components/SearchTermVideosDonutCard'
import RelatedReferrerBreakdownCard from '@/components/RelatedReferrerBreakdownCard'
import RelatedDestinationsByReferrerCard from '@/components/RelatedDestinationsByReferrerCard'
import CommentsPanel from '@/components/CommentsPanel'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import { useDebouncedInput } from '@/hooks/useDebouncedInput'
import './Analytics.css'

const RECENT_COUNT = 10
// Show every video with views for the selected term, not just a "top" handful.
const ALL_VIDEOS_FOR_TERM_LIMIT = 1000
const RELATED_VIDEOS_FETCH_LIMIT = 1000
const EMPTY_RELATED_REFERRERS: RelatedReferrersResponse = { items: [], total_named_views: 0 }

type Tab = 'analytics' | 'traffic-sources' | 'comments'
type TrafficSourcesSubTab = 'sources' | 'top-videos' | 'search' | 'related'

function toTrafficSourcesSubTab(value: string | null): TrafficSourcesSubTab {
  return value === 'top-videos' || value === 'search' || value === 'related' ? value : 'sources'
}

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
  const tsTab = toTrafficSourcesSubTab(searchParams.get('ts_tab'))
  const relatedTabVisible = tab === 'traffic-sources' && tsTab === 'related'
  const [videoTerm, setVideoTerm] = useState<string | null>(null)
  const [shortTerm, setShortTerm] = useState<string | null>(null)
  const [searchTerms, setSearchTerms] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [searchTermsByVideo, setSearchTermsByVideo] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [searchTermsByShort, setSearchTermsByShort] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [videosForVideoTerm, setVideosForVideoTerm] = useState<RequestState<SearchTermVideo[]>>(pending([]))
  const [videosForShortTerm, setVideosForShortTerm] = useState<RequestState<SearchTermVideo[]>>(pending([]))
  const [relatedReferrersMine, setRelatedReferrersMine] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedReferrersOther, setRelatedReferrersOther] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedDestinationsMine, setRelatedDestinationsMine] = useState<RequestState<RelatedDestinationRow[]>>(pending([]))
  const [relatedDestinationsOther, setRelatedDestinationsOther] = useState<RequestState<RelatedDestinationRow[]>>(pending([]))
  const [mineReferrerSelected, setMineReferrerSelected] = useReconciledSelection(
    relatedReferrersMine.data.items.map(r => r.referrer_video_id),
  )
  const [otherReferrerSelected, setOtherReferrerSelected] = useReconciledSelection(
    relatedReferrersOther.data.items.map(r => r.referrer_video_id),
  )
  const mineReferrerId = mineReferrerSelected ?? relatedReferrersMine.data.items[0]?.referrer_video_id ?? null
  const otherReferrerId = otherReferrerSelected ?? relatedReferrersOther.data.items[0]?.referrer_video_id ?? null

  // A bare route has no explicit tab; write the derived default back so the URL matches what renders.
  useEffect(() => {
    if (searchParams.has('tab')) return
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('tab', 'analytics')
      return next
    })
  }, [searchParams, setSearchParams])

  // The four sidebar cards keep their fixed periods (no date filter for Latest, last-7-days for Top)
  // but otherwise track the page's title/type/privacy filters, with each card kept to its Video/Short identity.
  useEffect(() => {
    let active = true
    const tt = title || undefined
    const ps = privacyStatus || undefined
    const emptyResolved = { data: [], loading: false, error: null }
    if (contentType === 'short') {
      setRecentVideos(emptyResolved)
      setTopPerformingVideos(emptyResolved)
    } else {
      track(getVideos(1, RECENT_COUNT, 'published_at', 'desc', tt, undefined, undefined, 'video', ps)
        .then((data: { items: Video[] }) => (data.items ?? []).map(toTopVideoShape)), setRecentVideos, () => active)
      const [sevenStart, sevenEnd] = last7Dates()
      track(getTopVideosByViews('views', sevenStart, sevenEnd, 'video', ps, tt)
        .then((data: { items: TopVideo[] }) => data.items ?? []), setTopPerformingVideos, () => active)
    }
    if (contentType === 'video') {
      setRecentShorts(emptyResolved)
      setTopPerformingShorts(emptyResolved)
    } else {
      track(getVideos(1, RECENT_COUNT, 'published_at', 'desc', tt, undefined, undefined, 'short', ps)
        .then((data: { items: Video[] }) => (data.items ?? []).map(toTopVideoShape)), setRecentShorts, () => active)
      const [sevenStart, sevenEnd] = last7Dates()
      track(getTopVideosByViews('views', sevenStart, sevenEnd, 'short', ps, tt)
        .then((data: { items: TopVideo[] }) => data.items ?? []), setTopPerformingShorts, () => active)
    }
    return () => { active = false }
  }, [contentType, privacyStatus, title])

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

  // Search Insights ignores the page's own content_type filter — these three columns
  // always show the All/Video/Short split regardless of it, since that split is the point.
  useEffect(() => {
    let active = true
    const query = { startDate: startDate || undefined, endDate: endDate || undefined, title: title || undefined, privacyStatus: privacyStatus || undefined }
    track(getSearchTerms(query)
      .then((data: { items: SearchTermRow[] }) => data.items ?? []), setSearchTerms, () => active, 'Could not load search terms')
    track(getSearchTerms({ ...query, contentType: 'video' })
      .then((data: { items: SearchTermRow[] }) => data.items ?? []), setSearchTermsByVideo, () => active, 'Could not load search terms')
    track(getSearchTerms({ ...query, contentType: 'short' })
      .then((data: { items: SearchTermRow[] }) => data.items ?? []), setSearchTermsByShort, () => active, 'Could not load search terms')
    return () => { active = false }
  }, [startDate, endDate, title, privacyStatus])

  // Each Search Insights video card owns its own term selection independently.
  useEffect(() => {
    let active = true
    const term = videoTerm || searchTermsByVideo.data[0]?.search_term
    if (!term) { setVideosForVideoTerm({ data: [], loading: false, error: null }); return }
    track(getVideosBySearchTerm(term, { startDate: startDate || undefined, endDate: endDate || undefined, title: title || undefined, privacyStatus: privacyStatus || undefined, contentType: 'video' }, ALL_VIDEOS_FOR_TERM_LIMIT)
      .then((data: { items: SearchTermVideo[] }) => data.items ?? []), setVideosForVideoTerm, () => active, 'Could not load videos')
    return () => { active = false }
  }, [videoTerm, searchTermsByVideo.data, startDate, endDate, title, privacyStatus])

  useEffect(() => {
    let active = true
    const term = shortTerm || searchTermsByShort.data[0]?.search_term
    if (!term) { setVideosForShortTerm({ data: [], loading: false, error: null }); return }
    track(getVideosBySearchTerm(term, { startDate: startDate || undefined, endDate: endDate || undefined, title: title || undefined, privacyStatus: privacyStatus || undefined, contentType: 'short' }, ALL_VIDEOS_FOR_TERM_LIMIT)
      .then((data: { items: SearchTermVideo[] }) => data.items ?? []), setVideosForShortTerm, () => active, 'Could not load videos')
    return () => { active = false }
  }, [shortTerm, searchTermsByShort.data, startDate, endDate, title, privacyStatus])

  // The two referrer-breakdown cards each own one own-filtered referrers call. Deferred
  // until the Related Videos sub-tab is actually visible, and refetched whenever the
  // filters change while it's visible — switching into the sub-tab fetches fresh data
  // rather than relying on whatever was current the last time it was open.
  useEffect(() => {
    if (!relatedTabVisible) return
    let active = true
    const query = { startDate: startDate || undefined, endDate: endDate || undefined, title: title || undefined, contentType: contentType || undefined, privacyStatus: privacyStatus || undefined }
    track(getRelatedVideoReferrers(true, query, RELATED_VIDEOS_FETCH_LIMIT)
      .then((data: RelatedReferrersResponse) => data), setRelatedReferrersMine, () => active, 'Could not load Related Video referrers')
    track(getRelatedVideoReferrers(false, query, RELATED_VIDEOS_FETCH_LIMIT)
      .then((data: RelatedReferrersResponse) => data), setRelatedReferrersOther, () => active, 'Could not load Related Video referrers')
    return () => { active = false }
  }, [relatedTabVisible, startDate, endDate, contentType, privacyStatus, title])

  // Each destination-drill-down card owns its own referrer selection independently,
  // deferred the same way as the referrer-breakdown cards above.
  useEffect(() => {
    if (!relatedTabVisible) return
    let active = true
    if (!mineReferrerId) { setRelatedDestinationsMine({ data: [], loading: false, error: null }); return }
    track(getRelatedVideoDestinations(mineReferrerId, startDate || undefined, endDate || undefined, RELATED_VIDEOS_FETCH_LIMIT)
      .then((data: { items: RelatedDestinationRow[] }) => data.items ?? []), setRelatedDestinationsMine, () => active, 'Could not load destinations')
    return () => { active = false }
  }, [relatedTabVisible, mineReferrerId, startDate, endDate])

  useEffect(() => {
    if (!relatedTabVisible) return
    let active = true
    if (!otherReferrerId) { setRelatedDestinationsOther({ data: [], loading: false, error: null }); return }
    track(getRelatedVideoDestinations(otherReferrerId, startDate || undefined, endDate || undefined, RELATED_VIDEOS_FETCH_LIMIT)
      .then((data: { items: RelatedDestinationRow[] }) => data.items ?? []), setRelatedDestinationsOther, () => active, 'Could not load destinations')
    return () => { active = false }
  }, [relatedTabVisible, otherReferrerId, startDate, endDate])

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

  const handleTsTabChange = (t: TrafficSourcesSubTab) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('ts_tab', t)
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

  const [titleDraft, setTitleDraft] = useDebouncedInput(title, t => updateParams({ title: t }))

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
            value={titleDraft}
            onChange={e => setTitleDraft(e.target.value)}
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
          <div className="tabs ts-subtabs">
            <button
              type="button"
              className={`tab${tsTab === 'sources' ? ' active' : ''}`}
              onClick={() => handleTsTabChange('sources')}
            >
              Traffic Sources
            </button>
            <button
              type="button"
              className={`tab${tsTab === 'top-videos' ? ' active' : ''}`}
              onClick={() => handleTsTabChange('top-videos')}
            >
              Top Videos by Traffic Source
            </button>
            <button
              type="button"
              className={`tab${tsTab === 'search' ? ' active' : ''}`}
              onClick={() => handleTsTabChange('search')}
            >
              Search Insights
            </button>
            <button
              type="button"
              className={`tab${tsTab === 'related' ? ' active' : ''}`}
              onClick={() => handleTsTabChange('related')}
            >
              Related Videos
            </button>
          </div>
          {tsTab === 'sources' ? (
            <TrafficSourcesTable
              rows={trafficSources.data}
              loading={trafficSources.loading}
              error={trafficSources.error}
            />
          ) : tsTab === 'top-videos' ? (
            <TrafficSourceTopVideosPanel
              rows={trafficSources.data}
              bySource={topVideosBySource.data}
              loading={trafficSources.loading || topVideosBySource.loading}
              error={trafficSources.error ?? topVideosBySource.error}
            />
          ) : tsTab === 'search' ? (
            <>
              <div className="search-insights-columns">
                <SearchTermsDonutCard
                  title="Top Search Terms"
                  rows={searchTerms.data}
                  loading={searchTerms.loading}
                  error={searchTerms.error}
                />
                <SearchTermsDonutCard
                  title="Top Search Terms — Videos"
                  rows={searchTermsByVideo.data}
                  loading={searchTermsByVideo.loading}
                  error={searchTermsByVideo.error}
                />
                <SearchTermsDonutCard
                  title="Top Search Terms — Shorts"
                  rows={searchTermsByShort.data}
                  loading={searchTermsByShort.loading}
                  error={searchTermsByShort.error}
                />
              </div>
              <div className="search-insights-videos">
                <SearchTermVideosDonutCard
                  title="Top Videos by Search Term"
                  terms={searchTermsByVideo.data}
                  termsLoading={searchTermsByVideo.loading}
                  selectedTerm={videoTerm || searchTermsByVideo.data[0]?.search_term || null}
                  onSelectTerm={setVideoTerm}
                  videos={videosForVideoTerm.data}
                  loading={videosForVideoTerm.loading}
                  error={videosForVideoTerm.error}
                />
                <SearchTermVideosDonutCard
                  title="Top Shorts by Search Term"
                  terms={searchTermsByShort.data}
                  termsLoading={searchTermsByShort.loading}
                  selectedTerm={shortTerm || searchTermsByShort.data[0]?.search_term || null}
                  onSelectTerm={setShortTerm}
                  videos={videosForShortTerm.data}
                  loading={videosForShortTerm.loading}
                  error={videosForShortTerm.error}
                />
              </div>
            </>
          ) : (
            <>
              <div className="related-videos-columns">
                <RelatedReferrerBreakdownCard
                  title="Related Traffic from My Channel"
                  referrers={relatedReferrersMine.data.items}
                  loading={relatedReferrersMine.loading}
                  error={relatedReferrersMine.error}
                />
                <RelatedReferrerBreakdownCard
                  title="Related Traffic from Other Channels"
                  referrers={relatedReferrersOther.data.items}
                  loading={relatedReferrersOther.loading}
                  error={relatedReferrersOther.error}
                />
              </div>
              <div className="related-videos-columns">
                <RelatedDestinationsByReferrerCard
                  title="Top Destinations — My Channel"
                  referrerOptions={relatedReferrersMine.data.items}
                  referrerOptionsLoading={relatedReferrersMine.loading}
                  selectedReferrerId={mineReferrerId}
                  onSelectReferrer={setMineReferrerSelected}
                  destinations={relatedDestinationsMine.data}
                  loading={relatedDestinationsMine.loading}
                  error={relatedDestinationsMine.error}
                />
                <RelatedDestinationsByReferrerCard
                  title="Top Destinations — Other Channels"
                  referrerOptions={relatedReferrersOther.data.items}
                  referrerOptionsLoading={relatedReferrersOther.loading}
                  selectedReferrerId={otherReferrerId}
                  onSelectReferrer={setOtherReferrerSelected}
                  destinations={relatedDestinationsOther.data}
                  loading={relatedDestinationsOther.loading}
                  error={relatedDestinationsOther.error}
                />
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
