import type { SyncStageStatus, SyncStatusResponse } from '@/types'
import { stageLabel } from '@/lib/syncStages'
import './SyncStatusBanner.css'

interface SyncStatusBannerProps {
  status: SyncStatusResponse | null
  unavailable: boolean
}

/**
 * Shows only what the user couldn't otherwise know: a stage actively syncing (live
 * progress), a stage that just failed (needs attention), or a stage that just finished
 * successfully (they'd otherwise have to go check the data directly to know it's done).
 * A stage the user cancelled themselves, or one still waiting its turn, tells them
 * nothing they don't already know, so neither is rendered — and there is deliberately no
 * separate "stopping"/"stop requested" row, for the same reason.
 */
export default function SyncStatusBanner({ status, unavailable }: SyncStatusBannerProps) {
  if (unavailable) {
    return (
      <div className="sync-status-banner">
        <div className="sync-status-banner-row sync-status-banner-idle">Status unavailable</div>
      </div>
    )
  }

  if (!status) return null

  const visible = status.stages.filter(stage => VISIBLE_STATES.has(stage.state))
  if (visible.length === 0) return null

  return (
    <div className="sync-status-banner">
      {visible.map(renderStage)}
    </div>
  )
}

const VISIBLE_STATES: ReadonlySet<SyncStageStatus['state']> = new Set(['running', 'success', 'failed'])

function renderStage(stage: SyncStageStatus) {
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
  return <div key={stage.key} className="sync-status-banner-row success">{label} synced</div>
}
