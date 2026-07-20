export interface Video {
  id: string
  title: string
  description: string | null
  published_at: string
  duration_seconds: number | null
  thumbnail_url: string | null
  content_type: string
  view_count: number
  like_count: number
  comment_count: number
  total_revenue_sgd: number
  total_watch_time_hours: number
}

export interface Playlist {
  id: string
  title: string
  published_at: string
  thumbnail_url: string | null
  item_count: number
  last_item_added: string | null
  total_views: number
  total_earnings_sgd: number
}

export type ContentType = 'video' | 'short'

export interface AnalyticsRow {
  date: string
  content_type: ContentType
  views: number
  watch_time_minutes: number
  estimated_revenue: number
  estimated_revenue_sgd: number
  average_view_duration_seconds: number
  average_view_percentage: number
  likes: number
  subscribers_gained: number
  subscribers_lost: number
}

export interface SyncState {
  is_syncing: boolean
  last_synced_at: string | null
  message: string
}

export interface TopVideo {
  id: string
  title: string
  published_at: string
  thumbnail_url: string | null
  content_type: string
  period_views: number
  period_earnings_sgd: number
  period_watch_time_hours: number
}

export interface TrafficSourceRow {
  date: string
  traffic_source_type: string
  views: number
  watch_time_minutes: number
}

export interface TrafficSourceTopVideo {
  id: string
  title: string
  thumbnail_url: string | null
  content_type: string
  views: number
  watch_time_minutes: number
}

export interface PublishedVideo {
  id: string
  title: string
  published_at: string
  thumbnail_url: string | null
  content_type: string
}

export interface VideoStats {
  legacy_video_count: number
  legacy_video_views: number
  legacy_video_earnings_sgd: number
  legacy_short_count: number
  legacy_short_views: number
  legacy_short_earnings_sgd: number
  new_video_count: number
  new_video_views: number
  new_video_earnings_sgd: number
  new_short_count: number
  new_short_views: number
  new_short_earnings_sgd: number
  total_comments: number
  video_comments: number
  short_comments: number
  total_public: number
  total_private: number
  total_unlisted: number
}
