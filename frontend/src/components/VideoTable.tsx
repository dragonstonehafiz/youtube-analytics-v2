import { Link } from 'react-router-dom'
import type { Video } from '@/types'
import PeriodSelect from '@/components/PeriodSelect'
import '@/components/VideoTable.css'

export type SortKey = 'published_at' | 'view_count' | 'comment_count' | 'total_revenue_sgd'
export type SortDir = 'asc' | 'desc'

export const PAGE_SIZE = 25

interface VideoTableProps {
  videos: Video[]
  total: number
  initialLoading: boolean
  page: number
  sortKey: SortKey
  sortDir: SortDir
  title: string
  startDate: string
  endDate: string
  contentType: string
  privacyStatus: string
  onPageChange: (page: number) => void
  onSort: (key: SortKey) => void
  onFilterChange: (title: string, startDate: string, endDate: string, contentType: string, privacyStatus: string) => void
}

export default function VideoTable({
  videos,
  total,
  initialLoading,
  page,
  sortKey,
  sortDir,
  title,
  startDate,
  endDate,
  contentType,
  privacyStatus,
  onPageChange,
  onSort,
  onFilterChange,
}: VideoTableProps) {
  const totalPages = Math.ceil(total / PAGE_SIZE)
  const arrow = (key: SortKey) => sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''

  return (
    <>
      <div className="filter-bar">
        <PeriodSelect
          startDate={startDate}
          endDate={endDate}
          onChange={(sd, ed) => onFilterChange(title, sd, ed, contentType, privacyStatus)}
        />
        <label>
          From
          <input type="date" value={startDate} onChange={e => onFilterChange(title, e.target.value, endDate, contentType, privacyStatus)} />
        </label>
        <label>
          To
          <input type="date" value={endDate} onChange={e => onFilterChange(title, startDate, e.target.value, contentType, privacyStatus)} />
        </label>
        <div className="filter-bar-sep" />
        <label>
          Title
          <input
            type="text"
            placeholder="Search…"
            value={title}
            onChange={e => onFilterChange(e.target.value, startDate, endDate, contentType, privacyStatus)}
          />
        </label>
        <div className="filter-bar-sep" />
        <label>
          Type
          <select value={contentType} onChange={e => onFilterChange(title, startDate, endDate, e.target.value, privacyStatus)}>
            <option value="">All</option>
            <option value="video">Video</option>
            <option value="short">Short</option>
          </select>
        </label>
        <div className="filter-bar-sep" />
        <label>
          Privacy
          <select value={privacyStatus} onChange={e => onFilterChange(title, startDate, endDate, contentType, e.target.value)}>
            <option value="">All</option>
            <option value="public">Public</option>
            <option value="private">Private</option>
            <option value="unlisted">Unlisted</option>
          </select>
        </label>
      </div>

      {initialLoading ? (
        <p className="loading">Loading...</p>
      ) : (
        <>
          <table className="data-table">
            <colgroup>
              <col style={{ width: 110 }} />
              <col style={{ width: '35%' }} />
              <col style={{ width: 120 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 110 }} />
            </colgroup>
            <thead>
              <tr>
                <th>Thumbnail</th>
                <th>Title</th>
                <th className="sortable" onClick={() => onSort('published_at')}>Upload Date{arrow('published_at')}</th>
                <th>Type</th>
                <th className="sortable" onClick={() => onSort('view_count')}>Views{arrow('view_count')}</th>
                <th className="sortable" onClick={() => onSort('comment_count')}>Comments{arrow('comment_count')}</th>
                <th className="sortable" onClick={() => onSort('total_revenue_sgd')}>Earnings (SGD){arrow('total_revenue_sgd')}</th>
              </tr>
            </thead>
            <tbody>
              {videos.length === 0 && (
                <tr>
                  <td colSpan={7} className="table-empty">No videos found</td>
                </tr>
              )}
              {videos.map(v => (
                <tr key={v.id}>
                  <td>
                    {v.thumbnail_url
                      ? <img src={v.thumbnail_url} alt="" className="table-thumb" />
                      : <div className="table-thumb-placeholder" />}
                  </td>
                  <td className="cell-title">
                    <Link to={`/analytics/videos/${v.id}`}>{v.title}</Link>
                  </td>
                  <td>{v.published_at?.slice(0, 10)}</td>
                  <td>
                    <span className={`badge${v.content_type === 'short' ? ' short' : ''}`}>
                      {v.content_type === 'short' ? 'Short' : 'Video'}
                    </span>
                  </td>
                  <td>{v.view_count?.toLocaleString()}</td>
                  <td>{v.comment_count?.toLocaleString()}</td>
                  <td>S${v.total_revenue_sgd?.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div className="pagination">
              <button type="button" className="btn-ghost" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
                Previous
              </button>
              <span className="pagination-info">Page {page} of {totalPages}</span>
              <button type="button" className="btn-ghost" onClick={() => onPageChange(page + 1)} disabled={page >= totalPages}>
                Next
              </button>
            </div>
          )}
        </>
      )}
    </>
  )
}
