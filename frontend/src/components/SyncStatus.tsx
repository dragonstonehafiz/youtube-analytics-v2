import { useEffect, useState } from 'react'
import { getSyncStatus, triggerSync, getDateRange } from '@/api'
import type { SyncState } from '@/types'
import './SyncStatus.css'

export default function SyncStatus() {
  const [status, setStatus] = useState<SyncState | null>(null)
  const [earliestYear, setEarliestYear] = useState<number | null>(null)
  const [scopeValue, setScopeValue] = useState('incremental')

  useEffect(() => {
    const poll = () => getSyncStatus().then(setStatus).catch(() => {})
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    getDateRange().then((data: { earliest_year: number | null }) => {
      setEarliestYear(data.earliest_year)
    })
  }, [])

  const currentYear = new Date().getFullYear()
  const years = earliestYear
    ? Array.from({ length: currentYear - earliestYear + 1 }, (_, i) => currentYear - i)
    : []

  const handleTrigger = () => {
    const scope = scopeValue === 'all' ? 'all' : scopeValue === 'incremental' ? 'incremental' : 'year'
    const year = scope === 'year' ? Number(scopeValue) : undefined
    triggerSync(scope, year).then(() => getSyncStatus().then(setStatus)).catch(() => {})
  }

  if (!status) return null

  return (
    <div className={`sync-status${status.is_syncing ? ' syncing' : ''}`}>
      {status.is_syncing ? (
        <>
          <span className="sync-status-dot" />
          <span className="sync-status-message">{status.message || 'Syncing...'}</span>
        </>
      ) : (
        <>
          <span className="sync-status-label">
            {status.last_synced_at ? `Last synced ${status.last_synced_at}` : 'Never synced'}
          </span>
          <select className="sync-scope-select" value={scopeValue} onChange={e => setScopeValue(e.target.value)}>
            <option value="incremental">New data only</option>
            <option value="all">Full resync</option>
            {years.map(y => (
              <option key={y} value={String(y)}>{y}</option>
            ))}
          </select>
          <button type="button" className="btn-primary sync-trigger-btn" onClick={handleTrigger}>
            Sync now
          </button>
        </>
      )}
    </div>
  )
}
