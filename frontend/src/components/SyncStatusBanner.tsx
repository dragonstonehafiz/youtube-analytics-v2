import type { SyncStatusResponse } from '@/types'
import './SyncStatusBanner.css'

interface SyncStatusBannerProps {
  status: SyncStatusResponse | null
  unavailable: boolean
  stopRequested: boolean
}

/**
 * The Sync page's own large status readout, shown above the tab selector. Unlike the
 * navbar's `SyncStatus` — which only surfaces a sync that's running or has failed — this
 * shows every lifecycle state, since a visitor to this page is here specifically to check
 * on syncing. Concurrent stages stack vertically rather than side by side, so each one's
 * full text stays readable at this larger size.
 */
export default function SyncStatusBanner({ status, unavailable, stopRequested }: SyncStatusBannerProps) {
  if (unavailable) {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row sync-status-banner-idle">Status unavailable</div>
      </div>
    )
  }

  if (!status) return null

  if (status.state === 'stopping' || (status.state === 'running' && stopRequested)) {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row stopping">
          <span className="sync-status-banner-dot" />
          <span className="sync-status-banner-message">
            {status.state === 'stopping' ? status.message || 'Stopping sync...' : 'Stopping sync...'}
          </span>
        </div>
      </div>
    )
  }

  if (status.state === 'running') {
    const items = status.stages.length > 0
      ? status.stages
      : [{ key: 'running', message: status.message || 'Syncing...' }]
    return (
      <div className="sync-status-banner">
        {items.map(item => (
          <div key={item.key} className="sync-status-banner-row syncing">
            <span className="sync-status-banner-dot" />
            <span className="sync-status-banner-message">{item.message}</span>
          </div>
        ))}
      </div>
    )
  }

  if (status.state === 'failed') {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row failed">
          <span className="sync-status-banner-message">{status.message || 'Sync failed'}</span>
        </div>
      </div>
    )
  }

  if (status.state === 'cancelled') {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row sync-status-banner-idle">{status.message || 'Sync cancelled'}</div>
      </div>
    )
  }

  if (status.state === 'success') {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row sync-status-banner-idle">{status.message || 'Sync complete'}</div>
      </div>
    )
  }

  return (
    <div className="sync-status-banner">
      <div className="sync-status-banner-row sync-status-banner-idle">Not syncing</div>
    </div>
  )
}
