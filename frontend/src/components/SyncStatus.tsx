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

  const running = status.active && !status.stop_requested
    ? status.stages.filter(stage => stage.state === 'running')
    : []
  const failed = status.stages.filter(stage => stage.state === 'failed')

  if (running.length + failed.length === 0) return null

  return (
    <div className="sync-status-group">
      {running.map(stage => (
        <div key={stage.key} className="sync-status syncing">
          <span className="sync-status-dot" />
          <span className="sync-status-message">{stage.message}</span>
        </div>
      ))}
      {failed.map(stage => (
        <div key={stage.key} className="sync-status failed">
          <span className="sync-status-message">{stage.message || 'Sync failed'}</span>
        </div>
      ))}
    </div>
  )
}
