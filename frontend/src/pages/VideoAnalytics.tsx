import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getVideo, getVideoAnalytics, getVideoTrafficSources, getVideoSearchTerms, getVideoRelatedVideoReferrers, getRelatedVideoDestinations } from '@/api'
import type { Video, AnalyticsRow, TrafficSourceRow, SearchTermRow, RelatedReferrersResponse, RelatedDestinationRow } from '@/types'
import Tabs from '@/components/Tabs'
import type { TabOption } from '@/components/Tabs'
import FilterBar from '@/components/FilterBar'
import DetailHeader from '@/components/DetailHeader'
import type { TrafficSourcesSubTab } from '@/lib/trafficSources'
import { VIDEO_TRAFFIC_SOURCES_SUB_TABS, toTrafficSourcesSubTab } from '@/lib/trafficSources'
import { lastNDates } from '@/lib/dates'
import { ALL_ROWS_LIMIT } from '@/lib/analyticsConstants'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import AnalyticsChart from '@/components/AnalyticsChart'
import CommentsTab from '@/components/CommentsTab'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import SearchTermsDonutCard from '@/components/SearchTermsDonutCard'
import RelatedReferrerBreakdownCard from '@/components/RelatedReferrerBreakdownCard'
import RelatedDestinationsByReferrerCard from '@/components/RelatedDestinationsByReferrerCard'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import '@/components/VideoMetaCard.css'
import './Analytics.css'
import './VideoAnalytics.css'

const EMPTY_RELATED_REFERRERS: RelatedReferrersResponse = { items: [], total_named_views: 0 }

type Tab = 'analytics' | 'traffic-sources' | 'comments'

const TABS: readonly TabOption<Tab>[] = [
  { value: 'analytics', label: 'Analytics' },
  { value: 'traffic-sources', label: 'Traffic Sources' },
  { value: 'comments', label: 'Comments' },
]

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

interface VideoTabProps {
  videoId: string
  startDate: string
  endDate: string
}

/** The Analytics tab: this video's daily chart. */
function VideoAnalyticsTab({ videoId, startDate, endDate }: VideoTabProps) {
  const [rows, setRows] = useState<RequestState<AnalyticsRow[]>>(pending([]))

  useEffect(() => {
    let active = true
    track(getVideoAnalytics(videoId, { startDate, endDate })
      .then((data: { items: AnalyticsRow[] }) => data.items ?? []), setRows, () => active, 'Could not load analytics')
    return () => { active = false }
  }, [videoId, startDate, endDate])

  return <AnalyticsChart rows={rows.data} loading={rows.loading} error={rows.error} />
}

/** The Traffic Sources tab: the traffic chart shared by every sub-tab, then the sub-tabs. */
function VideoTrafficSourcesTab({ videoId, startDate, endDate, subTab, onSubTabChange }: VideoTabProps & {
  subTab: TrafficSourcesSubTab
  onSubTabChange: (subTab: TrafficSourcesSubTab) => void
}) {
  const [trafficSources, setTrafficSources] = useState<RequestState<TrafficSourceRow[]>>(pending([]))

  useEffect(() => {
    let active = true
    track(getVideoTrafficSources(videoId, { startDate, endDate })
      .then((data: { items: TrafficSourceRow[] }) => data.items ?? []), setTrafficSources, () => active, 'Could not load traffic sources')
    return () => { active = false }
  }, [videoId, startDate, endDate])

  return (
    <>
      <TrafficSourceChart
        rows={trafficSources.data}
        loading={trafficSources.loading}
        error={trafficSources.error}
      />
      <Tabs
        options={VIDEO_TRAFFIC_SOURCES_SUB_TABS}
        value={subTab}
        onChange={onSubTabChange}
        className="ts-subtabs"
      />
      {subTab === 'sources' ? (
        <TrafficSourcesTable
          rows={trafficSources.data}
          loading={trafficSources.loading}
          error={trafficSources.error}
        />
      ) : subTab === 'search' ? (
        <VideoSearchInsights videoId={videoId} startDate={startDate} endDate={endDate} />
      ) : (
        <VideoRelatedVideos videoId={videoId} startDate={startDate} endDate={endDate} />
      )}
    </>
  )
}

function VideoSearchInsights({ videoId, startDate, endDate }: VideoTabProps) {
  const [searchTerms, setSearchTerms] = useState<RequestState<SearchTermRow[]>>(pending([]))

  useEffect(() => {
    let active = true
    track(getVideoSearchTerms(videoId, { startDate, endDate })
      .then((data: { items: SearchTermRow[] }) => data.items ?? []), setSearchTerms, () => active, 'Could not load search terms')
    return () => { active = false }
  }, [videoId, startDate, endDate])

  return (
    <div className="search-insights-columns">
      <SearchTermsDonutCard
        title="Top Search Terms"
        rows={searchTerms.data}
        loading={searchTerms.loading}
        error={searchTerms.error}
      />
    </div>
  )
}

function VideoRelatedVideos({ videoId, startDate, endDate }: VideoTabProps) {
  const [relatedReferrersMine, setRelatedReferrersMine] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedReferrersOther, setRelatedReferrersOther] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedDestinations, setRelatedDestinations] = useState<RequestState<RelatedDestinationRow[]>>(pending([]))

  // The two referrer-breakdown cards each own one own-filtered, video-scoped referrers call.
  useEffect(() => {
    let active = true
    const query = { startDate, endDate, limit: ALL_ROWS_LIMIT }
    track(getVideoRelatedVideoReferrers(videoId, { ...query, own: true })
      .then((data: RelatedReferrersResponse) => data), setRelatedReferrersMine, () => active, 'Could not load Related Video referrers')
    track(getVideoRelatedVideoReferrers(videoId, { ...query, own: false })
      .then((data: RelatedReferrersResponse) => data), setRelatedReferrersOther, () => active, 'Could not load Related Video referrers')
    return () => { active = false }
  }, [videoId, startDate, endDate])

  // The outbound card has no dropdown: this video's own ID is always the referrer, via
  // the channel-scoped destinations route (no video-scoped destinations route exists).
  useEffect(() => {
    let active = true
    track(getRelatedVideoDestinations({ referrerVideoId: videoId, startDate, endDate, limit: ALL_ROWS_LIMIT })
      .then((data: { items: RelatedDestinationRow[] }) => data.items ?? []), setRelatedDestinations, () => active, 'Could not load destinations')
    return () => { active = false }
  }, [videoId, startDate, endDate])

  return (
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
  )
}

export default function VideoAnalytics() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setParams] = useReplaceSearchParams()
  const [video, setVideo] = useState<RequestState<Video | null>>(pending(null))
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'
  const startDate = searchParams.has('start_date') ? searchParams.get('start_date')! : lastNDates(28)[0]
  const endDate = searchParams.has('end_date') ? searchParams.get('end_date')! : lastNDates(28)[1]
  const tsTab = toTrafficSourcesSubTab(searchParams.get('ts_tab'), VIDEO_TRAFFIC_SOURCES_SUB_TABS)

  useEffect(() => {
    if (!id) return
    let active = true
    track(getVideo(id)
      .then((data: { item: Video | null }) => data.item ?? null), setVideo, () => active, 'Could not load this video')
    return () => { active = false }
  }, [id])

  const videoData = video.data

  return (
    <div className="page analytics-page">
      <DetailHeader
        loading={video.loading}
        error={video.error}
        emptyMessage="Video not found."
        content={videoData && {
          thumbnailUrl: videoData.thumbnail_url,
          title: videoData.title,
          stats: [
            { label: 'Views', value: videoData.view_count.toLocaleString() },
            { label: 'Likes', value: videoData.like_count.toLocaleString() },
            { label: 'Comments', value: videoData.comment_count.toLocaleString() },
            { label: 'Published', value: videoData.published_at.slice(0, 10) },
            ...(videoData.duration_seconds != null ? [{ label: 'Length', value: formatDuration(videoData.duration_seconds) }] : []),
            { label: 'Earnings', value: `S$${videoData.total_revenue_sgd.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` },
          ],
        }}
        badge={videoData && (
          <span className={`badge${videoData.content_type === 'short' ? ' short' : ''}`}>
            {videoData.content_type === 'short' ? 'Short' : 'Video'}
          </span>
        )}
      >
        {videoData && <DescriptionBlock text={videoData.description} />}
      </DetailHeader>

      {/* The tabs and their data are suppressed only once the video is definitively
          missing — never while its metadata request is still in flight. */}
      {(video.loading || video.data) && (
        <>
          <Tabs options={TABS} value={tab} onChange={t => setParams({ tab: t })} />

          {/* Comments filter on their own publication dates and carry their own filter
              bar, so the shared analytics date range does not apply to that tab. */}
          {tab !== 'comments' && (
          <FilterBar
            dates={{
              startDate: { value: startDate, onChange: v => setParams({ start_date: v }) },
              endDate: { value: endDate, onChange: v => setParams({ end_date: v }) },
              onPeriodChange: (sd, ed) => setParams({ start_date: sd, end_date: ed }),
            }}
          />
          )}

          {tab === 'comments' ? (
            <CommentsTab scope={{ kind: 'video', videoId: id! }} />
          ) : tab === 'analytics' ? (
            <VideoAnalyticsTab videoId={id!} startDate={startDate} endDate={endDate} />
          ) : (
            <VideoTrafficSourcesTab
              videoId={id!}
              startDate={startDate}
              endDate={endDate}
              subTab={tsTab}
              onSubTabChange={t => setParams({ ts_tab: t })}
            />
          )}
        </>
      )}
    </div>
  )
}
