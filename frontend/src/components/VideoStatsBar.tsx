import type { VideoStats } from '@/types'
import '@/components/VideoStatsBar.css'

interface VideoStatsBarProps {
  stats: VideoStats
}

export default function VideoStatsBar({ stats }: VideoStatsBarProps) {
  const sgd = (v: number) => `S$${v.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  return (
    <div className="video-stats-bar">
      <div className="video-stats-col">
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_uploads.toLocaleString()}</span><span className="video-stats-label">Total Uploads</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_views.toLocaleString()}</span><span className="video-stats-label">Total Views</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{sgd(stats.total_earnings_sgd)}</span><span className="video-stats-label">Total Earnings</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_videos.toLocaleString()}</span><span className="video-stats-label">Videos</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_video_views.toLocaleString()}</span><span className="video-stats-label">Video Views</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{sgd(stats.total_video_earnings_sgd)}</span><span className="video-stats-label">Video Earnings</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_shorts.toLocaleString()}</span><span className="video-stats-label">Shorts</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_short_views.toLocaleString()}</span><span className="video-stats-label">Short Views</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{sgd(stats.total_short_earnings_sgd)}</span><span className="video-stats-label">Short Earnings</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_comments.toLocaleString()}</span><span className="video-stats-label">Comments</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_public.toLocaleString()}</span><span className="video-stats-label">Public</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_private.toLocaleString()}</span><span className="video-stats-label">Private</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{stats.total_unlisted.toLocaleString()}</span><span className="video-stats-label">Unlisted</span></div>
      </div>
    </div>
  )
}
