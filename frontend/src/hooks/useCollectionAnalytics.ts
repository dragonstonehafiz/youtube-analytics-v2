import { useEffect, useState } from 'react'
import {
  getVideoStats, getChannelAnalytics, getTopVideosByViews, getVideosPublished, getVideos, getChannelTrafficSources,
  getTopVideosByTrafficSource, getSearchTerms, getVideosBySearchTerm, getRelatedVideoReferrers, getRelatedVideoDestinations,
  getPlaylistVideoStats, getPlaylistAnalytics, getPlaylistTopVideosByViews, getPlaylistVideos, getPlaylistTrafficSources,
  getPlaylistTopVideosByTrafficSource, getPlaylistSearchTerms, getPlaylistVideosBySearchTerm,
  getPlaylistRelatedVideoReferrers, getPlaylistRelatedVideoDestinations,
} from '@/api'
import type {
  CatalogFilters, VideoListQuery, TopVideosQuery, SearchTermVideosQuery, RelatedReferrersQuery, RelatedDestinationsQuery,
} from '@/api'
import type {
  AnalyticsRow, VideoStats, TopVideo, TopVideoSortBy, PublishedVideo, Video, TrafficSourceRow, TrafficSourceTopVideo,
  SearchTermRow, SearchTermVideo, RelatedReferrersResponse, RelatedDestinationRow,
} from '@/types'
import { toTopVideoShape } from '@/lib/topVideos'
import { lastNDates } from '@/lib/dates'
import { ALL_ROWS_LIMIT, RECENT_COUNT } from '@/lib/analyticsConstants'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import { useReconciledSelection } from '@/hooks/useReconciledSelection'

/** Whose analytics the Analytics and Traffic Sources tabs show. */
export type CollectionScope = { kind: 'channel' } | { kind: 'playlist'; id: string }

export interface CollectionFilters {
  startDate: string
  endDate: string
  title: string
  contentType: string
  privacyStatus: string
}

/** The API calls behind the two tabs, bound to one scope. */
interface CollectionApi {
  videoStats: (f: CatalogFilters) => Promise<VideoStats>
  analytics: (f: CatalogFilters) => Promise<{ items: AnalyticsRow[] }>
  published: (f: CatalogFilters) => Promise<{ items: PublishedVideo[] }>
  trafficSources: (f: CatalogFilters) => Promise<{ items: TrafficSourceRow[] }>
  topVideosBySource: (f: CatalogFilters) => Promise<{ items: Record<string, TrafficSourceTopVideo[]> }>
  topVideos: (q: TopVideosQuery) => Promise<{ items: TopVideo[] }>
  videos: (q: VideoListQuery) => Promise<{ items: Video[] }>
  searchTerms: (f: CatalogFilters) => Promise<{ items: SearchTermRow[] }>
  videosBySearchTerm: (q: SearchTermVideosQuery) => Promise<{ items: SearchTermVideo[] }>
  relatedReferrers: (q: RelatedReferrersQuery) => Promise<RelatedReferrersResponse>
  relatedDestinations: (q: RelatedDestinationsQuery) => Promise<{ items: RelatedDestinationRow[] }>
}

function collectionApi(playlistId: string | null): CollectionApi {
  if (playlistId === null) {
    return {
      videoStats: getVideoStats,
      analytics: getChannelAnalytics,
      published: getVideosPublished,
      trafficSources: getChannelTrafficSources,
      topVideosBySource: getTopVideosByTrafficSource,
      topVideos: getTopVideosByViews,
      videos: getVideos,
      searchTerms: getSearchTerms,
      videosBySearchTerm: getVideosBySearchTerm,
      relatedReferrers: getRelatedVideoReferrers,
      relatedDestinations: getRelatedVideoDestinations,
    }
  }
  return {
    videoStats: f => getPlaylistVideoStats(playlistId, f),
    analytics: f => getPlaylistAnalytics(playlistId, f),
    published: f => getVideosPublished({ ...f, playlistId }),
    trafficSources: f => getPlaylistTrafficSources(playlistId, f),
    topVideosBySource: f => getPlaylistTopVideosByTrafficSource(playlistId, f),
    topVideos: q => getPlaylistTopVideosByViews(playlistId, q),
    videos: q => getPlaylistVideos(playlistId, q),
    searchTerms: f => getPlaylistSearchTerms(playlistId, f),
    videosBySearchTerm: q => getPlaylistVideosBySearchTerm(playlistId, q),
    relatedReferrers: q => getPlaylistRelatedVideoReferrers(playlistId, q),
    relatedDestinations: q => getPlaylistRelatedVideoDestinations(playlistId, q),
  }
}

const EMPTY_RELATED_REFERRERS: RelatedReferrersResponse = { items: [], total_named_views: 0 }
const EMPTY_RESOLVED = { data: [], loading: false, error: null }

/**
 * Every request and selection behind the Analytics and Traffic Sources tabs of the channel or a
 * playlist. Call it at page level: requests run whichever tab is shown, except Related Videos,
 * which waits for `relatedTabVisible`.
 */
export function useCollectionAnalytics(
  scope: CollectionScope,
  filters: CollectionFilters,
  topVideosSortBy: TopVideoSortBy,
  relatedTabVisible: boolean,
) {
  const playlistId = scope.kind === 'playlist' ? scope.id : null
  const { startDate, endDate, title, contentType, privacyStatus } = filters

  const [stats, setStats] = useState<RequestState<VideoStats | null>>(pending(null))
  const [rows, setRows] = useState<RequestState<AnalyticsRow[]>>(pending([]))
  const [publishedVideos, setPublishedVideos] = useState<RequestState<PublishedVideo[]>>(pending([]))
  const [trafficSources, setTrafficSources] = useState<RequestState<TrafficSourceRow[]>>(pending([]))
  const [topVideosBySource, setTopVideosBySource] = useState<RequestState<Record<string, TrafficSourceTopVideo[]>>>(pending({}))
  const [topVideos, setTopVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [recentVideos, setRecentVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [recentShorts, setRecentShorts] = useState<RequestState<TopVideo[]>>(pending([]))
  const [topPerformingVideos, setTopPerformingVideos] = useState<RequestState<TopVideo[]>>(pending([]))
  const [topPerformingShorts, setTopPerformingShorts] = useState<RequestState<TopVideo[]>>(pending([]))
  const [searchTerms, setSearchTerms] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [searchTermsByVideo, setSearchTermsByVideo] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [searchTermsByShort, setSearchTermsByShort] = useState<RequestState<SearchTermRow[]>>(pending([]))
  const [videoTermSelected, setVideoTerm] = useState<string | null>(null)
  const [shortTermSelected, setShortTerm] = useState<string | null>(null)
  const [videosForVideoTerm, setVideosForVideoTerm] = useState<RequestState<SearchTermVideo[]>>(pending([]))
  const [videosForShortTerm, setVideosForShortTerm] = useState<RequestState<SearchTermVideo[]>>(pending([]))
  const [relatedReferrersMine, setRelatedReferrersMine] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedReferrersOther, setRelatedReferrersOther] = useState<RequestState<RelatedReferrersResponse>>(pending(EMPTY_RELATED_REFERRERS))
  const [relatedDestinationsMine, setRelatedDestinationsMine] = useState<RequestState<RelatedDestinationRow[]>>(pending([]))
  const [relatedDestinationsOther, setRelatedDestinationsOther] = useState<RequestState<RelatedDestinationRow[]>>(pending([]))
  const [mineReferrerSelected, setMineReferrer] = useReconciledSelection(
    relatedReferrersMine.data.items.map(r => r.referrer_video_id),
  )
  const [otherReferrerSelected, setOtherReferrer] = useReconciledSelection(
    relatedReferrersOther.data.items.map(r => r.referrer_video_id),
  )
  const videoTerm = videoTermSelected || searchTermsByVideo.data[0]?.search_term || null
  const shortTerm = shortTermSelected || searchTermsByShort.data[0]?.search_term || null
  const mineReferrerId = mineReferrerSelected ?? relatedReferrersMine.data.items[0]?.referrer_video_id ?? null
  const otherReferrerId = otherReferrerSelected ?? relatedReferrersOther.data.items[0]?.referrer_video_id ?? null

  // The four sidebar cards keep their fixed periods (no date filter for Latest, last-7-days for Top)
  // but otherwise track the title/type/privacy filters, with each card kept to its Video/Short identity.
  useEffect(() => {
    let active = true
    const api = collectionApi(playlistId)
    const recent = { page: 1, pageSize: RECENT_COUNT, sortBy: 'published_at', sortDir: 'desc', title, privacyStatus }
    const [sevenStart, sevenEnd] = lastNDates(7)
    if (contentType === 'short') {
      setRecentVideos(EMPTY_RESOLVED)
      setTopPerformingVideos(EMPTY_RESOLVED)
    } else {
      track(api.videos({ ...recent, contentType: 'video' })
        .then(data => (data.items ?? []).map(toTopVideoShape)), setRecentVideos, () => active)
      track(api.topVideos({ sortBy: 'views', startDate: sevenStart, endDate: sevenEnd, contentType: 'video', privacyStatus, title })
        .then(data => data.items ?? []), setTopPerformingVideos, () => active)
    }
    if (contentType === 'video') {
      setRecentShorts(EMPTY_RESOLVED)
      setTopPerformingShorts(EMPTY_RESOLVED)
    } else {
      track(api.videos({ ...recent, contentType: 'short' })
        .then(data => (data.items ?? []).map(toTopVideoShape)), setRecentShorts, () => active)
      track(api.topVideos({ sortBy: 'views', startDate: sevenStart, endDate: sevenEnd, contentType: 'short', privacyStatus, title })
        .then(data => data.items ?? []), setTopPerformingShorts, () => active)
    }
    return () => { active = false }
  }, [playlistId, contentType, privacyStatus, title])

  // One filter change starts five requests, each owning the state of the card it feeds.
  useEffect(() => {
    let active = true
    const api = collectionApi(playlistId)
    const query = { startDate, endDate, contentType, privacyStatus, title }
    track(api.videoStats(query), setStats, () => active, 'Could not load statistics')
    track(api.analytics(query).then(data => data.items ?? []), setRows, () => active, 'Could not load analytics')
    track(api.published(query).then(data => data.items ?? []), setPublishedVideos, () => active, 'Could not load uploads')
    track(api.trafficSources(query).then(data => data.items ?? []), setTrafficSources, () => active, 'Could not load traffic sources')
    track(api.topVideosBySource(query).then(data => data.items ?? {}), setTopVideosBySource, () => active, 'Could not load traffic sources')
    return () => { active = false }
  }, [playlistId, startDate, endDate, contentType, privacyStatus, title])

  // Search Insights ignores the content_type filter — these three columns always show the
  // All/Video/Short split regardless of it, since that split is the point.
  useEffect(() => {
    let active = true
    const api = collectionApi(playlistId)
    const query = { startDate, endDate, title, privacyStatus }
    track(api.searchTerms(query).then(data => data.items ?? []), setSearchTerms, () => active, 'Could not load search terms')
    track(api.searchTerms({ ...query, contentType: 'video' }).then(data => data.items ?? []), setSearchTermsByVideo, () => active, 'Could not load search terms')
    track(api.searchTerms({ ...query, contentType: 'short' }).then(data => data.items ?? []), setSearchTermsByShort, () => active, 'Could not load search terms')
    return () => { active = false }
  }, [playlistId, startDate, endDate, title, privacyStatus])

  // Each Search Insights video card owns its own term selection independently.
  useEffect(() => {
    let active = true
    const term = videoTermSelected || searchTermsByVideo.data[0]?.search_term
    if (!term) { setVideosForVideoTerm(EMPTY_RESOLVED); return }
    track(collectionApi(playlistId).videosBySearchTerm({ searchTerm: term, startDate, endDate, title, privacyStatus, contentType: 'video', limit: ALL_ROWS_LIMIT })
      .then(data => data.items ?? []), setVideosForVideoTerm, () => active, 'Could not load videos')
    return () => { active = false }
  }, [playlistId, videoTermSelected, searchTermsByVideo.data, startDate, endDate, title, privacyStatus])

  useEffect(() => {
    let active = true
    const term = shortTermSelected || searchTermsByShort.data[0]?.search_term
    if (!term) { setVideosForShortTerm(EMPTY_RESOLVED); return }
    track(collectionApi(playlistId).videosBySearchTerm({ searchTerm: term, startDate, endDate, title, privacyStatus, contentType: 'short', limit: ALL_ROWS_LIMIT })
      .then(data => data.items ?? []), setVideosForShortTerm, () => active, 'Could not load videos')
    return () => { active = false }
  }, [playlistId, shortTermSelected, searchTermsByShort.data, startDate, endDate, title, privacyStatus])

  // The two referrer-breakdown cards each own one own-filtered referrers call. Deferred
  // until the Related Videos sub-tab is visible, and refetched whenever the filters change
  // while it's visible, so entering the sub-tab always fetches fresh data.
  useEffect(() => {
    if (!relatedTabVisible) return
    let active = true
    const api = collectionApi(playlistId)
    const query = { startDate, endDate, title, contentType, privacyStatus, limit: ALL_ROWS_LIMIT }
    track(api.relatedReferrers({ ...query, own: true }), setRelatedReferrersMine, () => active, 'Could not load Related Video referrers')
    track(api.relatedReferrers({ ...query, own: false }), setRelatedReferrersOther, () => active, 'Could not load Related Video referrers')
    return () => { active = false }
  }, [playlistId, relatedTabVisible, startDate, endDate, contentType, privacyStatus, title])

  // Each destination card owns its own referrer selection, deferred the same way.
  useEffect(() => {
    if (!relatedTabVisible) return
    let active = true
    if (!mineReferrerId) { setRelatedDestinationsMine(EMPTY_RESOLVED); return }
    track(collectionApi(playlistId).relatedDestinations({ referrerVideoId: mineReferrerId, startDate, endDate, limit: ALL_ROWS_LIMIT })
      .then(data => data.items ?? []), setRelatedDestinationsMine, () => active, 'Could not load destinations')
    return () => { active = false }
  }, [playlistId, relatedTabVisible, mineReferrerId, startDate, endDate])

  useEffect(() => {
    if (!relatedTabVisible) return
    let active = true
    if (!otherReferrerId) { setRelatedDestinationsOther(EMPTY_RESOLVED); return }
    track(collectionApi(playlistId).relatedDestinations({ referrerVideoId: otherReferrerId, startDate, endDate, limit: ALL_ROWS_LIMIT })
      .then(data => data.items ?? []), setRelatedDestinationsOther, () => active, 'Could not load destinations')
    return () => { active = false }
  }, [playlistId, relatedTabVisible, otherReferrerId, startDate, endDate])

  // The sortable top-video table reloads on its own sort change, and on nothing else's.
  useEffect(() => {
    let active = true
    track(collectionApi(playlistId).topVideos({ sortBy: topVideosSortBy, startDate, endDate, contentType, privacyStatus, title })
      .then(data => data.items ?? []), setTopVideos, () => active, 'Could not load top videos')
    return () => { active = false }
  }, [playlistId, startDate, endDate, contentType, privacyStatus, topVideosSortBy, title])

  return {
    stats, rows, publishedVideos, trafficSources, topVideosBySource, topVideos,
    recentVideos, recentShorts, topPerformingVideos, topPerformingShorts,
    searchTerms, searchTermsByVideo, searchTermsByShort,
    videoTerm, setVideoTerm, videosForVideoTerm,
    shortTerm, setShortTerm, videosForShortTerm,
    relatedReferrersMine, relatedReferrersOther,
    mineReferrerId, setMineReferrer, relatedDestinationsMine,
    otherReferrerId, setOtherReferrer, relatedDestinationsOther,
  }
}

export type CollectionAnalytics = ReturnType<typeof useCollectionAnalytics>
