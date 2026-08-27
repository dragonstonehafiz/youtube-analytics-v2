import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getComments, getPlaylistComments, getVideoComments } from '@/api'
import type { CommentQuery } from '@/api'
import type { Comment, CommentSort, CommentsResponse } from '@/types'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import AsyncCard from '@/components/AsyncCard'
import '@/components/CommentsPanel.css'

export const PAGE_SIZE = 25

/**
 * Which comments the panel shows. The owning Analytics page fixes this; every other piece
 * of the panel's state lives in the URL.
 *
 * Unlike the other Analytics tab components, this one fetches its own data. The three
 * pages that host it share no comment state to hand down, so keeping the request, the
 * eight filter params and the paging in one place is what stops the same block being
 * repeated on each of them.
 */
export type CommentsScope =
  | { kind: 'channel' }
  | { kind: 'video'; videoId: string }
  | { kind: 'playlist'; playlistId: string }

/**
 * Comment state is prefixed so it can share an Analytics URL with the Analytics, Traffic
 * Sources and Videos tabs without either clobbering the other's filters on a tab switch.
 */
const PARAM = {
  page: 'comments_page',
  text: 'comments_text',
  videoTitle: 'comments_video_title',
  author: 'comments_author',
  startDate: 'comments_start_date',
  endDate: 'comments_end_date',
  contentType: 'comments_content_type',
  sortBy: 'comments_sort_by',
} as const

const SORT_LABELS: Record<CommentSort, string> = {
  newest: 'Newest first',
  oldest: 'Oldest first',
  likes: 'Most liked',
}

function isCommentSort(value: string | null): value is CommentSort {
  return value === 'newest' || value === 'oldest' || value === 'likes'
}

/** Fetch one page from whichever endpoint matches the panel's scope. */
function fetchForScope(scope: CommentsScope, query: CommentQuery): Promise<CommentsResponse> {
  if (scope.kind === 'video') return getVideoComments(scope.videoId, query)
  if (scope.kind === 'playlist') return getPlaylistComments(scope.playlistId, query)
  return getComments(query)
}

const MINUTE_MS = 60 * 1000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS
const MONTH_MS = 30 * DAY_MS
const YEAR_MS = 365 * DAY_MS

/** Render an absolute timestamp the way YouTube does: "3 hours ago", "2 months ago". */
function relativeTime(iso: string): string {
  const elapsed = Date.now() - new Date(iso).getTime()
  if (!Number.isFinite(elapsed) || elapsed < MINUTE_MS) return 'just now'

  const [amount, unit] =
    elapsed >= YEAR_MS ? [elapsed / YEAR_MS, 'year'] :
    elapsed >= MONTH_MS ? [elapsed / MONTH_MS, 'month'] :
    elapsed >= DAY_MS ? [elapsed / DAY_MS, 'day'] :
    elapsed >= HOUR_MS ? [elapsed / HOUR_MS, 'hour'] :
    [elapsed / MINUTE_MS, 'minute']

  const rounded = Math.floor(amount as number)
  return `${rounded} ${unit}${rounded === 1 ? '' : 's'} ago`
}

interface CommentGroup {
  videoId: string
  videoTitle: string
  videoThumbnailUrl: string | null
  comments: Comment[]
}

/**
 * Bucket a page of comments by their parent video, keeping both the page's sort order
 * within each group and the order the videos first appear in it.
 *
 * Grouping is applied to the fetched page only, so one video's comments can still span a
 * page boundary — the backend paginates over comments, not over videos.
 */
function groupByVideo(comments: Comment[]): CommentGroup[] {
  const groups = new Map<string, CommentGroup>()
  for (const comment of comments) {
    const existing = groups.get(comment.video_id)
    if (existing) {
      existing.comments.push(comment)
      continue
    }
    groups.set(comment.video_id, {
      videoId: comment.video_id,
      videoTitle: comment.video_title,
      videoThumbnailUrl: comment.video_thumbnail_url,
      comments: [comment],
    })
  }
  return [...groups.values()]
}

/**
 * One comment, laid out as a feed entry rather than a table row: a comment body is prose
 * of arbitrary length, which a fixed-layout cell either truncates or stretches.
 */
function CommentRow({ comment }: { comment: Comment }) {
  const edited = comment.youtube_updated_at !== comment.published_at

  return (
    <article className="comment">
      {comment.author_profile_image_url
        ? <img src={comment.author_profile_image_url} alt="" className="comment-avatar" />
        : <div className="comment-avatar comments-thumb-placeholder" />}
      <div className="comment-body">
        <div className="comment-meta">
          {comment.author_channel_url ? (
            <a
              href={comment.author_channel_url}
              target="_blank"
              rel="noreferrer"
              className="comment-author"
            >
              {comment.author_display_name}
            </a>
          ) : (
            <span className="comment-author">{comment.author_display_name}</span>
          )}
          <time className="comment-time" dateTime={comment.published_at}>
            {relativeTime(comment.published_at)}{edited ? ' (edited)' : ''}
          </time>
        </div>
        <p className="comment-text">{comment.text}</p>
        <div className="comment-stats">
          <span>
            {comment.like_count === 1
              ? '1 like'
              : `${comment.like_count.toLocaleString()} likes`}
          </span>
          <span>
            {comment.total_reply_count === 1
              ? '1 reply'
              : `${comment.total_reply_count.toLocaleString()} replies`}
          </span>
        </div>
      </div>
    </article>
  )
}

interface CommentsPanelProps {
  scope: CommentsScope
}

export default function CommentsPanel({ scope }: CommentsPanelProps) {
  const [searchParams, setSearchParams] = useReplaceSearchParams()
  const [comments, setComments] = useState<Comment[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const rawPage = Number(searchParams.get(PARAM.page))
  const page = Number.isFinite(rawPage) && rawPage >= 1 ? Math.floor(rawPage) : 1
  const text = searchParams.get(PARAM.text) ?? ''
  const videoTitle = searchParams.get(PARAM.videoTitle) ?? ''
  const author = searchParams.get(PARAM.author) ?? ''
  const startDate = searchParams.get(PARAM.startDate) ?? ''
  const endDate = searchParams.get(PARAM.endDate) ?? ''
  const contentType = searchParams.get(PARAM.contentType) ?? ''
  const rawSort = searchParams.get(PARAM.sortBy)
  const sortBy: CommentSort = isCommentSort(rawSort) ? rawSort : 'newest'

  // A video scope fixes the parent video, so its title and type are not filters there.
  const scopedToOneVideo = scope.kind === 'video'
  const scopeKey =
    scope.kind === 'video' ? scope.videoId : scope.kind === 'playlist' ? scope.playlistId : 'channel'

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    fetchForScope(scope, {
      page,
      pageSize: PAGE_SIZE,
      sortBy,
      text: text || undefined,
      videoTitle: scopedToOneVideo ? undefined : videoTitle || undefined,
      author: author || undefined,
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      contentType: scopedToOneVideo ? undefined : contentType || undefined,
    })
      .then(data => {
        if (!active) return
        setComments(data.items ?? [])
        setTotal(data.total ?? 0)
      })
      .catch((err: unknown) => {
        if (!active) return
        setComments([])
        setTotal(0)
        setError(err instanceof Error ? err.message : 'Could not load comments')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      // A scope or filter change mid-request must not let the stale response land.
      active = false
    }
    // `scope` is rebuilt on every render by its owner; scopeKey tracks its identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    scope.kind, scopeKey, page, sortBy, text, videoTitle, author, startDate, endDate,
    contentType, scopedToOneVideo,
  ])

  /** Apply filter or sort changes, always returning to the first page of the new result. */
  const updateFilter = (updates: Record<string, string>) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        if (value) {
          next.set(key, value)
        } else {
          next.delete(key)
        }
      }
      next.delete(PARAM.page)
      return next
    })
  }

  const goToPage = (nextPage: number) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (nextPage <= 1) {
        next.delete(PARAM.page)
      } else {
        next.set(PARAM.page, String(nextPage))
      }
      return next
    })
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  // A video scope has exactly one parent video, so grouping there would add a heading
  // repeating what the page already says.
  const groups = scopedToOneVideo ? [] : groupByVideo(comments)

  return (
    <div className="comments-panel">
      <div className="filter-bar">
        <label>
          From
          <input
            type="date"
            value={startDate}
            onChange={e => updateFilter({ [PARAM.startDate]: e.target.value })}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={endDate}
            onChange={e => updateFilter({ [PARAM.endDate]: e.target.value })}
          />
        </label>
        <div className="filter-bar-sep" />
        <label>
          Comment
          <input
            type="text"
            placeholder="Search…"
            value={text}
            onChange={e => updateFilter({ [PARAM.text]: e.target.value })}
          />
        </label>
        <label>
          Commenter
          <input
            type="text"
            placeholder="Search…"
            value={author}
            onChange={e => updateFilter({ [PARAM.author]: e.target.value })}
          />
        </label>
        {!scopedToOneVideo && (
          <>
            <label>
              Video
              <input
                type="text"
                placeholder="Search…"
                value={videoTitle}
                onChange={e => updateFilter({ [PARAM.videoTitle]: e.target.value })}
              />
            </label>
            <div className="filter-bar-sep" />
            <label>
              Type
              <select
                value={contentType}
                onChange={e => updateFilter({ [PARAM.contentType]: e.target.value })}
              >
                <option value="">All</option>
                <option value="video">Video</option>
                <option value="short">Short</option>
              </select>
            </label>
          </>
        )}
        <div className="filter-bar-sep" />
        <label>
          Sort
          <select value={sortBy} onChange={e => updateFilter({ [PARAM.sortBy]: e.target.value })}>
            {(Object.keys(SORT_LABELS) as CommentSort[]).map(value => (
              <option key={value} value={value}>{SORT_LABELS[value]}</option>
            ))}
          </select>
        </label>
      </div>

      {/* The results are one request-backed surface: a plain shell, because what it
          resolves to is itself a stack of cards. Its own states carry the card surface. */}
      <AsyncCard
        variant="plain"
        loading={loading}
        error={error}
        empty={comments.length === 0}
        emptyMessage="No comments found"
        bodyClassName="comments-results"
      >
        {scopedToOneVideo ? (
          <div className="card comments-list">
            {comments.map(comment => (
              <CommentRow key={comment.id} comment={comment} />
            ))}
          </div>
        ) : (
          groups.map(group => (
            <section className="card comments-group" key={group.videoId}>
              <header className="comments-group-header">
                <Link
                  to={`/analytics/videos/${group.videoId}?tab=comments`}
                  className="comments-group-video"
                >
                  {group.videoThumbnailUrl
                    ? <img src={group.videoThumbnailUrl} alt="" className="comments-group-thumb" />
                    : <div className="comments-group-thumb comments-thumb-placeholder" />}
                  <span className="comments-group-title">{group.videoTitle}</span>
                </Link>
                <span className="comments-group-count">
                  {group.comments.length === 1 ? '1 comment' : `${group.comments.length} comments`}
                </span>
              </header>
              <div className="comments-list">
                {group.comments.map(comment => (
                  <CommentRow key={comment.id} comment={comment} />
                ))}
              </div>
            </section>
          ))
        )}
        {totalPages > 1 && (
          <div className="pagination">
            <button
              type="button"
              className="btn-ghost"
              onClick={() => goToPage(page - 1)}
              disabled={page <= 1}
            >
              Previous
            </button>
            <span className="pagination-info">Page {page} of {totalPages}</span>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => goToPage(page + 1)}
              disabled={page >= totalPages}
            >
              Next
            </button>
          </div>
        )}
      </AsyncCard>
    </div>
  )
}
