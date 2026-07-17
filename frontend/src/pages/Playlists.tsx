import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getPlaylists } from '@/api'
import type { Playlist } from '@/types'

type SortKey = 'published_at' | 'item_count' | 'last_item_added' | 'total_views' | 'total_earnings_sgd'
type SortDir = 'asc' | 'desc'

const PAGE_SIZE = 25

export default function Playlists() {
  const [searchParams, setSearchParams] = useSearchParams()
  const page = Math.max(1, Number(searchParams.get('page') ?? 1))
  const sortKey = (searchParams.get('sort_by') as SortKey) ?? 'last_item_added'
  const sortDir = (searchParams.get('sort_dir') as SortDir) ?? 'desc'
  const title = searchParams.get('title') ?? ''

  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [total, setTotal] = useState(0)
  const [initialLoading, setInitialLoading] = useState(true)

  useEffect(() => {
    getPlaylists(page, PAGE_SIZE, sortKey, sortDir, title || undefined)
      .then((data: { items: Playlist[]; total: number }) => {
        setPlaylists(data.items ?? [])
        setTotal(data.total ?? 0)
      })
      .finally(() => setInitialLoading(false))
  }, [page, sortKey, sortDir, title])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const setPage = (p: number) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      next.set('page', String(p))
      return next
    })
  }

  const handleSort = (key: SortKey) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      const currentDir = (prev.get('sort_dir') as SortDir) ?? 'desc'
      const currentKey = prev.get('sort_by') ?? 'published_at'
      next.set('sort_by', key)
      next.set('sort_dir', currentKey === key && currentDir === 'desc' ? 'asc' : 'desc')
      next.set('page', '1')
      return next
    })
  }

  const handleFilterChange = (t: string) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      t ? next.set('title', t) : next.delete('title')
      next.set('page', '1')
      return next
    })
  }

  const arrow = (key: SortKey) => sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''

  return (
    <div className="page">
      <div className="page-header">
        <h1>Playlists</h1>
      </div>
      <div className="filter-bar">
        <label>
          Title
          <input
            type="text"
            placeholder="Search…"
            value={title}
            onChange={e => handleFilterChange(e.target.value)}
          />
        </label>
      </div>
      {initialLoading ? (
        <p className="loading">Loading...</p>
      ) : (
        <>
          <table className="data-table">
            <colgroup>
              <col style={{ width: 110 }} />
              <col />
              <col style={{ width: 120 }} />
              <col style={{ width: 120 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 120 }} />
              <col style={{ width: 80 }} />
            </colgroup>
            <thead>
              <tr>
                <th>Thumbnail</th>
                <th>Title</th>
                <th className="sortable" onClick={() => handleSort('last_item_added')}>Last Added{arrow('last_item_added')}</th>
                <th className="sortable" onClick={() => handleSort('published_at')}>Created{arrow('published_at')}</th>
                <th className="sortable" onClick={() => handleSort('total_views')}>Views{arrow('total_views')}</th>
                <th className="sortable" onClick={() => handleSort('total_earnings_sgd')}>Earnings (SGD){arrow('total_earnings_sgd')}</th>
                <th className="sortable" onClick={() => handleSort('item_count')}>Videos{arrow('item_count')}</th>
              </tr>
            </thead>
            <tbody>
              {playlists.map(p => (
                <tr key={p.id}>
                  <td>
                    {p.thumbnail_url
                      ? <img src={p.thumbnail_url} alt="" className="table-thumb" />
                      : <div className="table-thumb-placeholder" />}
                  </td>
                  <td className="cell-title">
                    <Link to={`/analytics/playlists/${p.id}`}>{p.title}</Link>
                  </td>
                  <td>{p.last_item_added?.slice(0, 10) ?? '—'}</td>
                  <td>{p.published_at?.slice(0, 10)}</td>
                  <td>{p.total_views.toLocaleString()}</td>
                  <td>S${p.total_earnings_sgd.toLocaleString('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                  <td>{p.item_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div className="pagination">
              <button type="button" className="btn-ghost" onClick={() => setPage(page - 1)} disabled={page <= 1}>
                Previous
              </button>
              <span className="pagination-info">Page {page} of {totalPages}</span>
              <button type="button" className="btn-ghost" onClick={() => setPage(page + 1)} disabled={page >= totalPages}>
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
