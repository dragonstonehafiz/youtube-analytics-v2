import { useEffect, useState } from 'react'
import { getSyncStatus } from '@/api'
import type { SyncState } from '@/types'
import './SyncStatus.css'

const STATUS_POLL_MS = 5000

export default function SyncStatus() {
  const [status, setStatus] = useState<SyncState | null>(null)

  useEffect(() => {
    const poll = () => getSyncStatus().then(setStatus).catch(() => {})
    poll()
    const id = setInterval(poll, STATUS_POLL_MS)
    return () => clearInterval(id)
  }, [])

  if (!status) return null

  return (
    <div className={`sync-status${status.is_syncing ? ' syncing' : ''}`}>
      {status.is_syncing ? (
        <>
          <span className="sync-status-dot" />
          <span className="sync-status-message">{status.message || 'Syncing...'}</span>
        </>
      ) : (
        <span className="sync-status-idle">Not syncing</span>
      )}
    </div>
  )
}
