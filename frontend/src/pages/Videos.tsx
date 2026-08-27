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
  const [searchParams, setSearchParams] = useReplaceSearchParams()
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
      getVideos(page, PAGE_SIZE, sortKey, sortDir, title || undefined, startDate || undefined, endDate || undefined, contentType || undefined, privacyStatus || undefined)
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
      getVideoStats(title || undefined, startDate || undefined, endDate || undefined, contentType || undefined, privacyStatus || undefined)
        .then((data: VideoStats) => data),
      setStats,
      () => active,
      'Could not load statistics',
    )
    return () => { active = false }
  }, [title, startDate, endDate, contentType, privacyStatus])

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
