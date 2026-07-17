import { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { getVideo, getVideoAnalytics, getVideoTrafficSources } from '@/api'
import type { Video, AnalyticsRow, TrafficSourceRow } from '@/types'
import PeriodSelect, { last28Dates } from '@/components/PeriodSelect'
import AnalyticsChart from '@/components/AnalyticsChart'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import './VideoAnalytics.css'

type Tab = 'analytics' | 'traffic-sources'

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
  const [searchParams, setSearchParams] = useSearchParams()
  const [video, setVideo] = useState<Video | null>(null)
  const [loading, setLoading] = useState(true)
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'
  const startDate = searchParams.has('start_date') ? searchParams.get('start_date')! : last28Dates()[0]
  const endDate = searchParams.has('end_date') ? searchParams.get('end_date')! : last28Dates()[1]
  const [rows, setRows] = useState<AnalyticsRow[]>([])
  const [trafficSources, setTrafficSources] = useState<TrafficSourceRow[]>([])

  useEffect(() => {
    if (!id) return
    getVideo(id)
      .then(data => setVideo(data.item ?? null))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    if (!id) return
    getVideoAnalytics(id, startDate || undefined, endDate || undefined)
      .then((data: { items: AnalyticsRow[] }) => setRows(data.items ?? []))
    getVideoTrafficSources(id, startDate || undefined, endDate || undefined)
      .then((data: { items: TrafficSourceRow[] }) => setTrafficSources(data.items ?? []))
  }, [id, startDate, endDate])

  const handleTabChange = (t: Tab) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('tab', t)
      return next
    })
  }

  return (
    <div className="page">
      {loading ? (
        <p className="loading">Loading...</p>
      ) : video ? (
        <>
          <div className="card video-meta-card">
            <div className="video-meta-thumb-wrap">
              {video.thumbnail_url
                ? <img src={video.thumbnail_url} alt="" className="video-meta-thumb" />
                : <div className="video-meta-thumb video-meta-thumb-placeholder" />}
            </div>
            <div className="video-meta-info">
              <div className="video-meta-title-row">
                <h1 className="video-meta-title">{video.title}</h1>
                <span className={`badge${video.content_type === 'short' ? ' short' : ''}`}>
                  {video.content_type === 'short' ? 'Short' : 'Video'}
                </span>
              </div>
              <div className="video-meta-stats">
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.view_count.toLocaleString()}</span>
                  <span className="video-meta-stat-label">Views</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.like_count.toLocaleString()}</span>
                  <span className="video-meta-stat-label">Likes</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.comment_count.toLocaleString()}</span>
                  <span className="video-meta-stat-label">Comments</span>
                </div>
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">{video.published_at.slice(0, 10)}</span>
                  <span className="video-meta-stat-label">Published</span>
                </div>
                {video.duration_seconds != null && (
                  <>
                    <div className="video-meta-stat-divider" />
                    <div className="video-meta-stat">
                      <span className="video-meta-stat-value">{formatDuration(video.duration_seconds)}</span>
                      <span className="video-meta-stat-label">Length</span>
                    </div>
                  </>
                )}
                <div className="video-meta-stat-divider" />
                <div className="video-meta-stat">
                  <span className="video-meta-stat-value">S${video.total_revenue_sgd.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  <span className="video-meta-stat-label">Earnings</span>
                </div>
              </div>
              <DescriptionBlock text={video.description} />
            </div>
          </div>

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
          </div>

          {tab === 'analytics' ? (
            <AnalyticsChart rows={rows} />
          ) : (
            <>
              <TrafficSourceChart rows={trafficSources} />
              <TrafficSourcesTable rows={trafficSources} />
            </>
          )}
        </>
      ) : (
        <p>Video not found.</p>
      )}
    </div>
  )
}
