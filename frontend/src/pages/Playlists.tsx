import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPlaylists } from '@/api'
import type { Playlist } from '@/types'
import type { RequestState } from '@/lib/requestState'
import { pending, track } from '@/lib/requestState'
import AsyncCard from '@/components/AsyncCard'
import Pagination from '@/components/Pagination'
import FilterBar from '@/components/FilterBar'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import { useDebouncedInput } from '@/hooks/useDebouncedInput'

type SortKey = 'published_at' | 'item_count' | 'last_item_added' | 'total_views' | 'total_earnings_sgd'
type SortDir = 'asc' | 'desc'

const PAGE_SIZE = 25

interface PlaylistPage {
  items: Playlist[]
  total: number
}

export default function Playlists() {
  const [searchParams, setParams] = useReplaceSearchParams()
  const page = Math.max(1, Number(searchParams.get('page') ?? 1))
  const sortKey = (searchParams.get('sort_by') as SortKey) ?? 'last_item_added'
  const sortDir = (searchParams.get('sort_dir') as SortDir) ?? 'desc'
  const title = searchParams.get('title') ?? ''

  const [listing, setListing] = useState<RequestState<PlaylistPage>>(pending({ items: [], total: 0 }))

  useEffect(() => {
    let active = true
    track(
      getPlaylists({ page, pageSize: PAGE_SIZE, sortBy: sortKey, sortDir, title })
        .then((data: { items: Playlist[]; total: number }) => ({ items: data.items ?? [], total: data.total ?? 0 })),
      setListing,
      () => active,
      'Could not load playlists',
    )
    return () => { active = false }
  }, [page, sortKey, sortDir, title])

  const playlists = listing.data.items
  const totalPages = Math.ceil(listing.data.total / PAGE_SIZE)

  const setPage = (p: number) => setParams({ page: String(p) })

  const handleSort = (key: SortKey) => setParams({
    sort_by: key,
    sort_dir: sortKey === key && sortDir === 'desc' ? 'asc' : 'desc',
    page: '1',
  })

  const handleFilterChange = (t: string) => setParams({ title: t || null, page: '1' })

  const arrow = (key: SortKey) => sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''
  const [titleDraft, setTitleDraft] = useDebouncedInput(title, handleFilterChange)

  return (
    <div className="page">
      <div className="page-header">
        <h1>Playlists</h1>
      </div>
      <FilterBar title={{ value: titleDraft, onChange: setTitleDraft }} />
      <AsyncCard
        variant="table"
        loading={listing.loading}
        error={listing.error}
        className="playlists-table-card"
      >
        <div className="table-overflow-wrap">
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
              {playlists.length === 0 && (
                <tr>
                  <td colSpan={7} className="table-empty">No playlists found</td>
                </tr>
              )}
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
        </div>
        {totalPages > 1 && (
          <Pagination page={page} totalPages={totalPages} onChange={setPage} />
        )}
      </AsyncCard>
    </div>
  )
}
