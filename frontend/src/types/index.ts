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

/**
 * The commenter snapshot joined onto every comment row. `author_youtube_channel_id` is
 * null for a commenter whose channel no longer resolves, which is also why the backend
 * keys those authors per comment rather than merging them by display name.
 */
export interface CommentAuthor {
  author_id: string
  author_youtube_channel_id: string | null
  author_display_name: string
  author_profile_image_url: string | null
  author_channel_url: string | null
}

/** One top-level comment with its author and parent video joined in. Replies are never stored. */
export interface Comment extends CommentAuthor {
  id: string
  thread_id: string
  video_id: string
  text: string
  like_count: number
  total_reply_count: number
  published_at: string
  youtube_updated_at: string
  updated_at: string
  video_title: string
  video_content_type: ContentType
  video_thumbnail_url: string | null
}

export type CommentSort = 'newest' | 'oldest' | 'likes'

export interface CommentsResponse {
  items: Comment[]
  total: number
  page: number
  page_size: number
}

export type SyncLifecycleState = 'idle' | 'running' | 'success' | 'failed'

export interface SyncStatusResponse {
  state: SyncLifecycleState
  message: string
}

/** Sync stages whose date range is configurable. */
export type PeriodAwareSyncStage = 'video_analytics' | 'video_traffic_sources'

/** Sync stages that choose how far back to scan but have no per-year view. */
export type ScopeAwareSyncStage = 'comments'

/** Sync stages that are always incremental and accept no scope or year. */
export type IncrementalOnlySyncStage = 'videos' | 'playlists' | 'pruning' | 'fx_rates'

export type SyncStage = PeriodAwareSyncStage | ScopeAwareSyncStage | IncrementalOnlySyncStage

export type SyncScope = 'incremental' | 'year' | 'all'

/** A year is required for — and only allowed with — the 'year' scope. */
export type SyncPeriod =
  | { scope: 'incremental' }
  | { scope: 'all' }
  | { scope: 'year'; year: number }

/** The two scopes a scope-aware stage accepts. 'all' is labelled Full data in the UI. */
export type ScopeAwareSyncScope = 'incremental' | 'all'

/**
 * One stage of a manual sync plan. Period-aware stages must carry a period, scope-aware
 * stages carry a scope but never a year, and the always-incremental stages carry neither.
 */
export type SyncPlanStage =
  | ({ stage: PeriodAwareSyncStage } & SyncPeriod)
  | { stage: ScopeAwareSyncStage; scope: ScopeAwareSyncScope; year?: never }
  | { stage: IncrementalOnlySyncStage; scope?: never; year?: never }

export interface SyncPlan {
  stages: SyncPlanStage[]
}

export interface SyncQueuedResponse {
  queued: boolean
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

export type TopVideoSortBy = 'views' | 'watch_time'

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
