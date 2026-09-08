import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getVideo, getVideoAnalytics, getVideoTrafficSources, getVideoSearchTerms, getVideoRelatedVideoReferrers, getRelatedVideoDestinations } from '@/api'
import type { Video, AnalyticsRow, TrafficSourceRow, SearchTermRow, RelatedReferrersResponse, RelatedDestinationRow } from '@/types'
import PeriodSelect, { last28Dates } from '@/components/PeriodSelect'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import AsyncCard from '@/components/AsyncCard'
import AnalyticsChart from '@/components/AnalyticsChart'
import CommentsPanel from '@/components/CommentsPanel'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import SearchTermsDonutCard from '@/components/SearchTermsDonutCard'
import RelatedReferrerBreakdownCard from '@/components/RelatedReferrerBreakdownCard'
import RelatedDestinationsByReferrerCard from '@/components/RelatedDestinationsByReferrerCard'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import '@/components/VideoMetaCard.css'
import './Analytics.css'
import './VideoAnalytics.css'

const RELATED_DESTINATIONS_LIMIT = 10
const EMPTY_RELATED_REFERRERS: RelatedReferrersResponse = { items: [], total_named_views: 0 }

type Tab = 'analytics' | 'traffic-sources' | 'comments'
type TrafficSourcesSubTab = 'sources' | 'search' | 'related'

function toTrafficSourcesSubTab(value: string | null): TrafficSourcesSubTab {
  return value === 'search' || value === 'related' ? value : 'sources'
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function DescriptionBlock({ text }: { text: string | null }) {
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)
  const ref = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    setOverflows(el.scrollHeight > el.clientHeight)
  }, [text])

  return (
    <div className="video-meta-desc-wrap">
      <p ref={ref} className={`video-meta-description${expanded ? ' expanded' : ''}`}>
        {text ?? <em>No description</em>}
      </p>
      {overflows && (
        <button type="button" className="video-meta-desc-toggle" onClick={() => setExpanded(e => !e)}>
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  )
}

export default function VideoAnalytics() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useReplaceSearchParams()
  const [video, setVideo] = useState<RequestState<Video | null>>(pending(null))
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'
  const startDate = searchParams.has('start_date') ? searchParams.get('start_date')! : last28Dates()[0]
  const endDate = searchParams.has('end_date') ? searchParams.get('end_date')! : last28Dates()[1]
  const [rows, setRows] = useState<RequestState<AnalyticsRow[]>>(pending([]))
  const [trafficSources, setTrafficSources] = useState<RequestState<TrafficSourceRow[]>>(pending([]))
  const tsTab = toTrafficSourcesSubTab(searchParams.get('ts_tab'))
  const [searchTerms, setSearchTerms] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [relatedReferrersMine, setRelatedReferrersMine] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedReferrersOther, setRelatedReferrersOther] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedDestinations, setRelatedDestinations] = useState<RequestState<RelatedDestinationRow[]>>(pending([]))

  useEffect(() => {
    if (!id) return
    let active = true
    track(getVideo(id)
      .then((data: { item: Video | null }) => data.item ?? null), setVideo, () => active, 'Could not load this video')
    return () => { active = false }
  }, [id])

  // The two data tabs each own their request, so a date change reloads only their cards.
  useEffect(() => {
    if (!id) return
    let active = true
    track(getVideoAnalytics(id, startDate || undefined, endDate || undefined)
      .then((data: { items: AnalyticsRow[] }) => data.items ?? []), setRows, () => active, 'Could not load analytics')
    track(getVideoTrafficSources(id, startDate || undefined, endDate || undefined)
      .then((data: { items: TrafficSourceRow[] }) => data.items ?? []), setTrafficSources, () => active, 'Could not load traffic sources')
    track(getVideoSearchTerms(id, startDate || undefined, endDate || undefined)
      .then((data: { items: SearchTermRow[] }) => data.items ?? []), setSearchTerms, () => active, 'Could not load search terms')
    return () => { active = false }
  }, [id, startDate, endDate])

  // The two referrer-breakdown cards each own one own-filtered, video-scoped referrers call.
  useEffect(() => {
    if (!id) return
    let active = true
    track(getVideoRelatedVideoReferrers(id, true, startDate || undefined, endDate || undefined, RELATED_DESTINATIONS_LIMIT)
      .then((data: RelatedReferrersResponse) => data), setRelatedReferrersMine, () => active, 'Could not load Related Video referrers')
    track(getVideoRelatedVideoReferrers(id, false, startDate || undefined, endDate || undefined, RELATED_DESTINATIONS_LIMIT)
      .then((data: RelatedReferrersResponse) => data), setRelatedReferrersOther, () => active, 'Could not load Related Video referrers')
    return () => { active = false }
  }, [id, startDate, endDate])

  // The outbound card has no dropdown: this video's own ID is always the referrer, via
  // the channel-scoped destinations route (no video-scoped destinations route exists).
  useEffect(() => {
    if (!id) return
    let active = true
    track(getRelatedVideoDestinations(id, startDate || undefined, endDate || undefined, RELATED_DESTINATIONS_LIMIT)
      .then((data: { items: RelatedDestinationRow[] }) => data.items ?? []), setRelatedDestinations, () => active, 'Could not load destinations')
    return () => { active = false }
  }, [id, startDate, endDate])

  const handleTsTabChange = (t: TrafficSourcesSubTab) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('ts_tab', t)
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
        loading={video.loading}
        error={video.error}
        empty={!video.data}
        emptyMessage="Video not found."
        className="video-meta-card"
        bodyClassName="video-meta-card-body"
      >
        {video.data && (
          <>
            <div className="video-meta-thumb-wrap">
              {video.data.thumbnail_url
                ? <img src={video.data.thumbnail_url} alt="" className="video-meta-thumb" />
                : <div className="video-meta-thumb video-meta-thumb-placeholder" />}
            </div>
            <div className="video-meta-info">
              <div className="video-meta-title-row">
                <h1 className="video-meta-title">{video.data.title}</h1>
                <span className={`badge${video.data.content_type === 'short' ? ' short' : ''}`}>
                  {video.data.content_type === 'short' ? 'Short' : 'Video'}
                </span>
              </div>
              <div className="video-meta-stats">
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.data.view_count.toLocaleString()}</span>
                  <span className="video-meta-stat-label">Views</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.data.like_count.toLocaleString()}</span>
                  <span className="video-meta-stat-label">Likes</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.data.comment_count.toLocaleString()}</span>
                  <span className="video-meta-stat-label">Comments</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.data.published_at.slice(0, 10)}</span>
                  <span className="video-meta-stat-label">Published</span>
                </div>
                {video.data.duration_seconds != null && (
                  <>
                    <div className="video-meta-stat-divider" />
                    <div className="video-meta-stat">
                      <span className="video-meta-stat-value">{formatDuration(video.data.duration_seconds)}</span>
                      <span className="video-meta-stat-label">Length</span>
                    </div>
                  </>
                )}
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">S${video.data.total_revenue_sgd.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  <span className="video-meta-stat-label">Earnings</span>
                </div>
              </div>
              <DescriptionBlock text={video.data.description} />
            </div>
          </>
        )}
      </AsyncCard>

      {/* The tabs and their data are suppressed only once the video is definitively
          missing — never while its metadata request is still in flight. */}
      {(video.loading || video.data) && (
        <>
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

          {/* Comments filter on their own publication dates and carry their own filter
              bar, so the shared analytics date range does not apply to that tab. */}
          {tab !== 'comments' && (
          <div className="filter-bar">
            <PeriodSelect
              startDate={startDate}
              endDate={endDate}
              onChange={(sd, ed) => setSearchParams(prev => {
                const next = new URLSearchParams(prev)
                next.set('start_date', sd)
                next.set('end_date', ed)
                return next
              })}
            />
            <label>
              Start
              <input type="date" value={startDate} onChange={e => setSearchParams(prev => {
                const next = new URLSearchParams(prev)
                next.set('start_date', e.target.value)
                return next
              })} />
            </label>
            <label>
              End
              <input type="date" value={endDate} onChange={e => setSearchParams(prev => {
                const next = new URLSearchParams(prev)
                next.set('end_date', e.target.value)
                return next
              })} />
            </label>
          </div>
          )}

          {tab === 'comments' ? (
            <CommentsPanel scope={{ kind: 'video', videoId: id! }} />
          ) : tab === 'analytics' ? (
            <AnalyticsChart rows={rows.data} loading={rows.loading} error={rows.error} />
          ) : (
            <>
              <TrafficSourceChart
                rows={trafficSources.data}
                loading={trafficSources.loading}
                error={trafficSources.error}
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
              ) : tsTab === 'search' ? (
                <div className="search-insights-columns">
                  <SearchTermsDonutCard
                    title="Top Search Terms"
                    rows={searchTerms.data}
                    loading={searchTerms.loading}
                    error={searchTerms.error}
                  />
                </div>
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
                      title="Top Destinations From This Video"
                      destinations={relatedDestinations.data}
                      loading={relatedDestinations.loading}
                      error={relatedDestinations.error}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
