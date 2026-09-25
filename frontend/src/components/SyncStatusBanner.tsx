import type { SyncStageStatus, SyncStatusResponse } from '@/types'
import { stageLabel } from '@/lib/syncStages'
import './SyncStatusBanner.css'

interface SyncStatusBannerProps {
  status: SyncStatusResponse | null
  unavailable: boolean
  stopRequested: boolean
}

/** Show each selected stage's own state and retain the stop-request advisory. */
export default function SyncStatusBanner({ status, unavailable, stopRequested }: SyncStatusBannerProps) {
  if (unavailable) {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row sync-status-banner-idle">Status unavailable</div>
      </div>
    )
  }

  if (!status) return null
  if (status.stages.length === 0) {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row sync-status-banner-idle">Not syncing</div>
      </div>
    )
  }

  const showStopping = status.active && (status.stop_requested || stopRequested)
  const showStopped = !status.active && status.stop_requested
  return (
    <div className="sync-status-banner">
      {showStopping && (
        <div className="sync-status-banner-row stopping">
          <span className="sync-status-banner-dot" />
          <span className="sync-status-banner-message">Stopping sync...</span>
        </div>
      )}
      {showStopped && (
        <div className="sync-status-banner-row cancelled">Stop request received</div>
      )}
      {status.stages.map(stage => renderStage(stage, status.active))}
    </div>
  )
}

function renderStage(stage: SyncStageStatus, active: boolean) {
  const label = stageLabel(stage.key)
  if (stage.state === 'running') {
    return (
      <div key={stage.key} className="sync-status-banner-row syncing">
        <span className="sync-status-banner-dot" />
        <span className="sync-status-banner-message">{stage.message}</span>
      </div>
    )
  }
  if (stage.state === 'failed') {
    return (
      <div key={stage.key} className="sync-status-banner-row failed">
        <span className="sync-status-banner-message">{stage.message || `${label} failed`}</span>
      </div>
    )
  }
  if (stage.state === 'pending') {
    return <div key={stage.key} className="sync-status-banner-row pending">{active ? `Waiting to sync ${label}` : `${label} not run`}</div>
  }
  if (stage.state === 'success') {
    return <div key={stage.key} className="sync-status-banner-row success">{label} synced</div>
  }
  return <div key={stage.key} className="sync-status-banner-row cancelled">{label} cancelled</div>
}
