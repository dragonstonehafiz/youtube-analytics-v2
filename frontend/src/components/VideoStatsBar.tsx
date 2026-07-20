import type { VideoStats } from '@/types'
import '@/components/VideoStatsBar.css'

interface VideoStatsBarProps {
  stats: VideoStats
}

export default function VideoStatsBar({ stats }: VideoStatsBarProps) {
  const sgd = (v: number) => `S$${v.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const num = (v: number) => v.toLocaleString()

  return (
    <div className="video-stats-bar">
      <div className="video-stats-col">
        <span className="video-stats-heading">Legacy Videos</span>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.legacy_video_count)}</span><span className="video-stats-label">Count</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.legacy_video_views)}</span><span className="video-stats-label">Period Views</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{sgd(stats.legacy_video_earnings_sgd)}</span><span className="video-stats-label">Period Earnings</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <span className="video-stats-heading">Legacy Shorts</span>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.legacy_short_count)}</span><span className="video-stats-label">Count</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.legacy_short_views)}</span><span className="video-stats-label">Period Views</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{sgd(stats.legacy_short_earnings_sgd)}</span><span className="video-stats-label">Period Earnings</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <span className="video-stats-heading">New Videos</span>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.new_video_count)}</span><span className="video-stats-label">Count</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.new_video_views)}</span><span className="video-stats-label">Period Views</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{sgd(stats.new_video_earnings_sgd)}</span><span className="video-stats-label">Period Earnings</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <span className="video-stats-heading">New Shorts</span>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.new_short_count)}</span><span className="video-stats-label">Count</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.new_short_views)}</span><span className="video-stats-label">Period Views</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{sgd(stats.new_short_earnings_sgd)}</span><span className="video-stats-label">Period Earnings</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <span className="video-stats-heading">Lifetime Comments</span>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.total_comments)}</span><span className="video-stats-label">Total Comments</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.video_comments)}</span><span className="video-stats-label">Video Comments</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.short_comments)}</span><span className="video-stats-label">Short Comments</span></div>
      </div>
      <div className="video-stats-sep" />
      <div className="video-stats-col">
        <span className="video-stats-heading">Current Status</span>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.total_public)}</span><span className="video-stats-label">Public</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.total_private)}</span><span className="video-stats-label">Private</span></div>
        <div className="video-stats-item"><span className="video-stats-value">{num(stats.total_unlisted)}</span><span className="video-stats-label">Unlisted</span></div>
      </div>
    </div>
  )
}
