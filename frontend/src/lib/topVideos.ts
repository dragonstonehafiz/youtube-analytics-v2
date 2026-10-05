import type { Video, TopVideo } from '@/types'

/** Maps a lifetime Video record into the TopVideo shape used by ranked/carousel components. */
export function toTopVideoShape(v: Video): TopVideo {
  return {
    id: v.id,
    title: v.title,
    published_at: v.published_at,
    thumbnail_url: v.thumbnail_url,
    content_type: v.content_type,
    period_views: v.view_count,
    period_watch_time_hours: v.total_watch_time_hours,
    period_earnings_sgd: v.total_revenue_sgd,
  }
}
