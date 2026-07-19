import { useEffect, useState } from 'react'
import { getVideos, getVideoStats } from '@/api'
import type { Video, VideoStats } from '@/types'
import VideoTable, { PAGE_SIZE } from '@/components/VideoTable'
import type { SortKey, SortDir } from '@/components/VideoTable'
import VideoStatsBar from '@/components/VideoStatsBar'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'

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

  const [videos, setVideos] = useState<Video[]>([])
  const [total, setTotal] = useState(0)
  const [initialLoading, setInitialLoading] = useState(true)
  const [stats, setStats] = useState<VideoStats | null>(null)

  useEffect(() => {
    getVideos(page, PAGE_SIZE, sortKey, sortDir, title || undefined, startDate || undefined, endDate || undefined, contentType || undefined, privacyStatus || undefined)
      .then((data: { items: Video[]; total: number }) => {
        setVideos(data.items ?? [])
        setTotal(data.total ?? 0)
      })
      .finally(() => setInitialLoading(false))
  }, [page, sortKey, sortDir, title, startDate, endDate, contentType, privacyStatus])

  useEffect(() => {
    getVideoStats(title || undefined, startDate || undefined, endDate || undefined, contentType || undefined, privacyStatus || undefined)
      .then((data: VideoStats) => setStats(data))
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
      {stats && <VideoStatsBar stats={stats} />}
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
    </div>
  )
}
