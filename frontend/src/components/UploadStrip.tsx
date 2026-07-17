import { Link } from 'react-router-dom'
import type { PublishedVideo } from '@/types'

export const YAXIS_WIDTH = 56
export const CHART_RIGHT = 16
export const BUCKET_WIDTH = 52

export function daysBetween(a: string, b: string): number {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000)
}

export function addDays(date: string, days: number): string {
  const d = new Date(date)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function formatCompact(v: number): string {
  const sign = v < 0 ? '-' : ''
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}M`
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}K`
  return v.toLocaleString()
}

export function getMarks(rows: { date: string }[]): { date: string; label: string }[] {
  const seen = new Set<string>()
  const marks: { date: string; label: string }[] = []
  const quarters = new Set(rows.map(r => {
    const d = new Date(r.date)
    return `${d.getUTCFullYear()}-Q${Math.floor(d.getUTCMonth() / 3)}`
  }))
  const useYearly = quarters.size > 8
  for (const row of rows) {
    const d = new Date(row.date)
    const month = d.getUTCMonth()
    if (useYearly ? month === 0 : month % 3 === 0) {
      const key = useYearly ? `${d.getUTCFullYear()}` : `${d.getUTCFullYear()}-${month}`
      if (!seen.has(key)) {
        seen.add(key)
        const label = useYearly
          ? `${d.getUTCFullYear()}`
          : `${d.toLocaleString('default', { month: 'short', timeZone: 'UTC' })} ${d.getUTCFullYear()}`
        marks.push({ date: row.date, label })
      }
    }
  }
  return marks
}

export interface UploadBucket {
  bucketStart: string
  videos: PublishedVideo[]
  shorts: PublishedVideo[]
  leftPct: number
}

export function computeUploadBuckets(
  rows: { date: string }[],
  uploadedVideos: PublishedVideo[] | undefined,
  cardWidth: number,
): UploadBucket[] {
  if (!uploadedVideos || uploadedVideos.length === 0 || rows.length === 0) return []
  const firstDate = rows[0].date
  const lastDate = rows[rows.length - 1].date
  const totalDays = daysBetween(firstDate, lastDate)
  if (totalDays <= 0) return []

  const chartAreaWidth = cardWidth - YAXIS_WIDTH - CHART_RIGHT
  if (chartAreaWidth <= 0) return []

  const maxBuckets = Math.floor(chartAreaWidth / BUCKET_WIDTH)
  if (maxBuckets <= 0) return []

  const bucketDays = Math.max(1, Math.ceil(totalDays / maxBuckets))

  const bucketMap = new Map<string, { videos: PublishedVideo[]; shorts: PublishedVideo[] }>()
  for (const v of uploadedVideos) {
    const pub = v.published_at.slice(0, 10)
    if (pub < firstDate || pub > lastDate) continue
    const offset = Math.floor(daysBetween(firstDate, pub) / bucketDays)
    const key = addDays(firstDate, offset * bucketDays)
    if (!bucketMap.has(key)) bucketMap.set(key, { videos: [], shorts: [] })
    const bucket = bucketMap.get(key)!
    if (v.content_type === 'short') bucket.shorts.push(v)
    else bucket.videos.push(v)
  }

  return Array.from(bucketMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([bucketStart, { videos, shorts }]) => {
      const offset = daysBetween(firstDate, bucketStart)
      const leftPct = Math.min((offset + bucketDays / 2) / totalDays, 1)
      return { bucketStart, videos, shorts, leftPct }
    })
}

function VideoPopover({ videos, label }: { videos: PublishedVideo[]; label: string }) {
  return (
    <div className="upload-popover">
      <div className="upload-popover-header">{videos.length} {label} uploaded</div>
      <ul className="upload-popover-list">
        {videos.map(v => (
          <li key={v.id} className="upload-popover-item">
            {v.thumbnail_url
              ? <img src={v.thumbnail_url} alt="" className="upload-popover-thumb" />
              : <div className="upload-popover-thumb upload-popover-thumb--placeholder" />
            }
            <div className="upload-popover-info">
              <Link to={`/analytics/videos/${v.id}`} className="upload-popover-title">
                {v.title}
              </Link>
              <span className="upload-popover-date">{v.published_at.slice(0, 10)}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function UploadStrip({ buckets }: { buckets: UploadBucket[] }) {
  if (buckets.length === 0) return null

  return (
    <div className="upload-strip">
      {buckets.map(({ bucketStart, videos, shorts, leftPct }) => {
        const hasBoth = videos.length > 0 && shorts.length > 0
        return (
          <div
            key={bucketStart}
            className="upload-bucket"
            style={{ left: `calc(${YAXIS_WIDTH}px + ${leftPct} * (100% - ${YAXIS_WIDTH + CHART_RIGHT}px))` }}
          >
            {videos.length > 0 && (
              <div className={`upload-badge-slot${!hasBoth ? ' upload-badge-slot--solo' : ''}`}>
                <div className="upload-badge upload-badge--video">{videos.length}</div>
                <VideoPopover videos={videos} label="video" />
              </div>
            )}
            {shorts.length > 0 && (
              <div className={`upload-badge-slot${!hasBoth ? ' upload-badge-slot--solo' : ''}`}>
                <div className="upload-badge upload-badge--short">{shorts.length}</div>
                <VideoPopover videos={shorts} label="short" />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
