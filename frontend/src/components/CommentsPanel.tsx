import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getComments, getPlaylistComments, getVideoComments } from '@/api'
import type { CommentQuery } from '@/api'
import type { Comment, CommentSort, CommentsResponse } from '@/types'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
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
  const columnCount = scopedToOneVideo ? 5 : 6

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

      {error && <p className="comments-error" role="alert">{error}</p>}

      {loading ? (
        <p className="loading">Loading...</p>
      ) : (
        <>
          <div className="table-overflow-wrap">
            <table className="data-table comments-table">
              <colgroup>
                <col className="comments-col-author" />
                <col className="comments-col-text" />
                {!scopedToOneVideo && <col className="comments-col-video" />}
                <col className="comments-col-date" />
                <col className="comments-col-count" />
                <col className="comments-col-count" />
              </colgroup>
              <thead>
                <tr>
                  <th>Commenter</th>
                  <th>Comment</th>
                  {!scopedToOneVideo && <th>Video</th>}
                  <th>Published</th>
                  <th>Likes</th>
                  <th>Replies</th>
                </tr>
              </thead>
              <tbody>
                {comments.length === 0 && (
                  <tr>
                    <td colSpan={columnCount} className="table-empty">
                      {error ? 'Comments unavailable' : 'No comments found'}
                    </td>
                  </tr>
                )}
                {comments.map(comment => (
                  <tr key={comment.id}>
                    <td>
                      <div className="comments-author">
                        {comment.author_profile_image_url
                          ? <img src={comment.author_profile_image_url} alt="" className="comments-avatar" />
                          : <div className="comments-avatar-placeholder" />}
                        {comment.author_channel_url ? (
                          <a
                            href={comment.author_channel_url}
                            target="_blank"
                            rel="noreferrer"
                            className="comments-author-name"
                          >
                            {comment.author_display_name}
                          </a>
                        ) : (
                          <span className="comments-author-name">{comment.author_display_name}</span>
                        )}
                      </div>
                    </td>
                    <td className="comments-text">{comment.text}</td>
                    {!scopedToOneVideo && (
                      <td className="cell-title">
                        <Link to={`/analytics/videos/${comment.video_id}?tab=comments`}>
                          {comment.video_title}
                        </Link>
                        <span className={`badge${comment.video_content_type === 'short' ? ' short' : ''}`}>
                          {comment.video_content_type === 'short' ? 'Short' : 'Video'}
                        </span>
                      </td>
                    )}
                    <td>{comment.published_at?.slice(0, 10)}</td>
                    <td>{comment.like_count?.toLocaleString()}</td>
                    <td>{comment.total_reply_count?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
        </>
      )}
    </div>
  )
}
