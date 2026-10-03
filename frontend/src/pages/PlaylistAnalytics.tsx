import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getPlaylist, getPlaylistVideos } from '@/api'
import type { Video, Playlist, TopVideoSortBy } from '@/types'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import VideoTable, { PAGE_SIZE } from '@/components/VideoTable'
import type { SortKey, SortDir } from '@/components/VideoTable'
import Tabs from '@/components/Tabs'
import type { TabOption } from '@/components/Tabs'
import FilterBar from '@/components/FilterBar'
import DetailHeader from '@/components/DetailHeader'
import AnalyticsTab from '@/components/AnalyticsTab'
import TrafficSourcesTab from '@/components/TrafficSourcesTab'
import CommentsTab from '@/components/CommentsTab'
import { TRAFFIC_SOURCES_SUB_TABS, toTrafficSourcesSubTab } from '@/lib/trafficSources'
import { lastNDates } from '@/lib/dates'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import { useCollectionAnalytics } from '@/hooks/useCollectionAnalytics'
import { useDebouncedInput } from '@/hooks/useDebouncedInput'
import './Analytics.css'

type Tab = 'analytics' | 'traffic-sources' | 'comments' | 'videos'

interface VideoPage {
  items: Video[]
  total: number
}

export default function PlaylistAnalytics() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setParams] = useReplaceSearchParams()
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'

  // The Videos tab's own listing params.
  const page = Math.max(1, Number(searchParams.get('page') ?? 1))
  const sortKey = (searchParams.get('sort_by') as SortKey) ?? 'published_at'
  const sortDir = (searchParams.get('sort_dir') as SortDir) ?? 'desc'
  const title = searchParams.get('title') ?? ''
  const startDate = searchParams.get('start_date') ?? ''
  const endDate = searchParams.get('end_date') ?? ''
  const contentType = searchParams.get('content_type') ?? ''
  const privacyStatus = searchParams.get('privacy_status') ?? ''

  // The Analytics and Traffic Sources tabs' filters, prefixed so they don't collide with the Videos tab's.
  const analyticsStartDate = searchParams.has('analytics_start_date') ? searchParams.get('analytics_start_date')! : lastNDates(28)[0]
  const analyticsEndDate = searchParams.has('analytics_end_date') ? searchParams.get('analytics_end_date')! : lastNDates(28)[1]
  const analyticsTitle = searchParams.get('analytics_title') ?? ''
  const analyticsContentType = searchParams.get('analytics_content_type') ?? ''
  const analyticsPrivacyStatus = searchParams.get('analytics_privacy_status') ?? ''
  const rawTopVideosSortBy = searchParams.get('top_videos_sort_by')
  const topVideosSortBy: TopVideoSortBy = rawTopVideosSortBy === 'views' ? 'views' : 'watch_time'
  const tsTab = toTrafficSourcesSubTab(searchParams.get('ts_tab'), TRAFFIC_SOURCES_SUB_TABS)

  const [playlist, setPlaylist] = useState<RequestState<Playlist | null>>(pending(null))
  const [listing, setListing] = useState<RequestState<VideoPage>>(pending({ items: [], total: 0 }))

  const data = useCollectionAnalytics(
    { kind: 'playlist', id: id! },
    {
      startDate: analyticsStartDate,
      endDate: analyticsEndDate,
      title: analyticsTitle,
      contentType: analyticsContentType,
      privacyStatus: analyticsPrivacyStatus,
    },
    topVideosSortBy,
    tab === 'traffic-sources' && tsTab === 'related',
  )

  useEffect(() => {
    if (!id) return
    let active = true
    track(getPlaylist(id)
      .then((data: { item: Playlist | null }) => data.item ?? null), setPlaylist, () => active, 'Could not load this playlist')
    return () => { active = false }
  }, [id])

  useEffect(() => {
    if (!id) return
    let active = true
    track(
      getPlaylistVideos(id, { page, pageSize: PAGE_SIZE, sortBy: sortKey, sortDir, title, startDate, endDate, contentType, privacyStatus })
        .then((data: { items: Video[]; total: number }) => ({ items: data.items ?? [], total: data.total ?? 0 })),
      setListing,
      () => active,
      'Could not load videos',
    )
    return () => { active = false }
  }, [id, page, sortKey, sortDir, title, startDate, endDate, contentType, privacyStatus])

  const setPage = (p: number) => setParams({ page: String(p) })

  const handleSort = (key: SortKey) => setParams({
    sort_by: key,
    sort_dir: sortKey === key && sortDir === 'desc' ? 'asc' : 'desc',
    page: '1',
  })

  const handleFilterChange = (t: string, sd: string, ed: string, ct: string, ps: string) => setParams({
    title: t || null,
    start_date: sd || null,
    end_date: ed || null,
    content_type: ct || null,
    privacy_status: ps || null,
    page: '1',
  })

  const [analyticsTitleDraft, setAnalyticsTitleDraft] = useDebouncedInput(
    analyticsTitle,
    t => setParams({ analytics_title: t || null }),
  )

  const handleTopVideosSort = (sortBy: TopVideoSortBy) => {
    if (sortBy !== topVideosSortBy) setParams({ top_videos_sort_by: sortBy })
  }

  const tabs: readonly TabOption<Tab>[] = [
    { value: 'analytics', label: 'Analytics' },
    { value: 'traffic-sources', label: 'Traffic Sources' },
    { value: 'comments', label: 'Comments' },
    { value: 'videos', label: listing.data.total > 0 ? `Videos (${listing.data.total})` : 'Videos' },
  ]

  const playlistData = playlist.data

  return (
    <div className="page analytics-page">
      <DetailHeader
        loading={playlist.loading}
        error={playlist.error}
        emptyMessage="Playlist not found."
        content={playlistData && {
          thumbnailUrl: playlistData.thumbnail_url,
          title: playlistData.title,
          stats: [
            { label: 'Views', value: playlistData.total_views.toLocaleString() },
            { label: 'Earnings', value: `S$${playlistData.total_earnings_sgd.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` },
            { label: 'Videos', value: String(playlistData.item_count) },
            { label: 'Last Added', value: playlistData.last_item_added?.slice(0, 10) ?? '—' },
            { label: 'Created', value: playlistData.published_at?.slice(0, 10) ?? '' },
          ],
        }}
      />

      <Tabs options={tabs} value={tab} onChange={t => setParams({ tab: t })} />

      {tab === 'comments' ? (
        <CommentsTab scope={{ kind: 'playlist', playlistId: id! }} />
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
          <FilterBar
            dates={{
              startDate: { value: analyticsStartDate, onChange: v => setParams({ analytics_start_date: v }) },
              endDate: { value: analyticsEndDate, onChange: v => setParams({ analytics_end_date: v }) },
              onPeriodChange: (sd, ed) => setParams({ analytics_start_date: sd, analytics_end_date: ed }),
            }}
            title={{ value: analyticsTitleDraft, onChange: setAnalyticsTitleDraft }}
            contentType={{ value: analyticsContentType, onChange: v => setParams({ analytics_content_type: v || null }) }}
            privacyStatus={{ value: analyticsPrivacyStatus, onChange: v => setParams({ analytics_privacy_status: v || null }) }}
          />
          {tab === 'analytics' ? (
            <AnalyticsTab data={data} topVideosSortBy={topVideosSortBy} onTopVideosSort={handleTopVideosSort} />
          ) : (
            <TrafficSourcesTab data={data} subTab={tsTab} onSubTabChange={t => setParams({ ts_tab: t })} />
          )}
        </>
      )}
    </div>
  )
}
