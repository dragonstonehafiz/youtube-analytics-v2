import { useEffect, useState } from 'react'
import { getVideos, getVideoStats } from '@/api'
import type { Video, VideoStats } from '@/types'
import VideoTable, { PAGE_SIZE } from '@/components/VideoTable'
import type { SortKey, SortDir } from '@/components/VideoTable'
import VideoStatsBar from '@/components/VideoStatsBar'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'

interface VideoPage {
  items: Video[]
  total: number
}

export default function Videos() {
  const [searchParams, setParams] = useReplaceSearchParams()
  const page = Math.max(1, Number(searchParams.get('page') ?? 1))
  const sortKey = (searchParams.get('sort_by') as SortKey) ?? 'published_at'
  const sortDir = (searchParams.get('sort_dir') as SortDir) ?? 'desc'
  const title = searchParams.get('title') ?? ''
  const startDate = searchParams.get('start_date') ?? ''
  const endDate = searchParams.get('end_date') ?? ''
  const contentType = searchParams.get('content_type') ?? ''
  const privacyStatus = searchParams.get('privacy_status') ?? ''

  const [listing, setListing] = useState<RequestState<VideoPage>>(pending({ items: [], total: 0 }))
  const [stats, setStats] = useState<RequestState<VideoStats | null>>(pending(null))

  useEffect(() => {
    let active = true
    track(
      getVideos({ page, pageSize: PAGE_SIZE, sortBy: sortKey, sortDir, title, startDate, endDate, contentType, privacyStatus })
        .then((data: { items: Video[]; total: number }) => ({ items: data.items ?? [], total: data.total ?? 0 })),
      setListing,
      () => active,
      'Could not load videos',
    )
    return () => { active = false }
  }, [page, sortKey, sortDir, title, startDate, endDate, contentType, privacyStatus])

  // Statistics are their own request: they ignore paging and resolve independently of the table.
  useEffect(() => {
    let active = true
    track(
      getVideoStats({ title, startDate, endDate, contentType, privacyStatus })
        .then((data: VideoStats) => data),
      setStats,
      () => active,
      'Could not load statistics',
    )
    return () => { active = false }
  }, [title, startDate, endDate, contentType, privacyStatus])

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

  return (
    <div className="page">
      <div className="page-header">
        <h1>Videos</h1>
      </div>
      <VideoStatsBar stats={stats.data} loading={stats.loading} error={stats.error} />
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
    </div>
  )
}
