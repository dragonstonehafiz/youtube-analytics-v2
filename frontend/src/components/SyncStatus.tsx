import { useEffect, useState } from 'react'
import { getSyncStatus } from '@/api'
import type { SyncStatusResponse } from '@/types'
import './SyncStatus.css'

const STATUS_POLL_MS = 5000

export default function SyncStatus() {
  const [status, setStatus] = useState<SyncStatusResponse | null>(null)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    const poll = () =>
      getSyncStatus()
        .then(s => {
          setStatus(s)
          setUnavailable(false)
        })
        .catch(() => setUnavailable(true))
    poll()
    const id = setInterval(poll, STATUS_POLL_MS)
    return () => clearInterval(id)
  }, [])

  if (unavailable) {
    return (
      <div className="sync-status">
        <span className="sync-status-idle">Status unavailable</span>
      </div>
    )
  }

  if (!status) return null

  if (status.state === 'running') {
    return (
      <div className="sync-status syncing">
        <span className="sync-status-dot" />
        <span className="sync-status-message">{status.message || 'Syncing...'}</span>
      </div>
    )
  }

  if (status.state === 'failed') {
    return (
      <div className="sync-status failed">
        <span className="sync-status-message">{status.message || 'Sync failed'}</span>
      </div>
    )
  }

  if (status.state === 'success') {
    return (
      <div className="sync-status">
        <span className="sync-status-idle">{status.message || 'Sync complete'}</span>
      </div>
    )
  }

  return (
    <div className="sync-status">
      <span className="sync-status-idle">Not syncing</span>
    </div>
  )
}
