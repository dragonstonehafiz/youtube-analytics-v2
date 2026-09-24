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

  // The navbar only surfaces a sync in progress or one that just failed; a completed,
  // cancelled, stopping, or idle sync leaves nothing that still needs the user's attention.
  if (status.state === 'running') {
    const items = status.stages.length > 0
      ? status.stages
      : [{ key: 'running', message: status.message || 'Syncing...' }]
    return (
      <div className="sync-status-group">
        {items.map(item => (
          <div key={item.key} className="sync-status syncing">
            <span className="sync-status-dot" />
            <span className="sync-status-message">{item.message}</span>
          </div>
        ))}
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

  return null
}
