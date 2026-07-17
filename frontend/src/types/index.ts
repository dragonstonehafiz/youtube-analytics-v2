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

export interface AnalyticsRow {
  date: string
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
  total_uploads: number
  total_videos: number
  total_shorts: number
  total_views: number
  total_video_views: number
  total_short_views: number
  total_comments: number
  total_earnings_sgd: number
  total_video_earnings_sgd: number
  total_short_earnings_sgd: number
  total_public: number
  total_private: number
  total_unlisted: number
}
