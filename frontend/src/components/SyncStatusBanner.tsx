import type { SyncStageStatus, SyncStatusResponse } from '@/types'
import { stageLabel } from '@/lib/syncStages'
import './SyncStatusBanner.css'

interface SyncStatusBannerProps {
  status: SyncStatusResponse | null
  unavailable: boolean
}

const VISIBLE_STATES: ReadonlySet<SyncStageStatus['state']> = new Set(['running', 'success', 'failed'])

/**
 * A fixed-size, bordered strip above the tab selector — its own card-style container,
 * like every other section of this page — so the rest of the page never shifts as sync
 * activity starts, changes, or ends. Each stage is a small square card rather than a wide
 * row, so several sit side by side; the full progress/failure text lives in the card's
 * `title` tooltip rather than being crammed into the square itself.
 *
 * Shows only what the user couldn't otherwise know: a stage actively syncing (live
 * progress), a stage that just failed (needs attention), or a stage that just finished
 * successfully (they'd otherwise have to go check the data directly to know it's done).
 * A stage the user cancelled themselves, or one still waiting its turn, tells them
 * nothing they don't already know, so neither is rendered — and there is deliberately no
 * separate "stopping"/"stop requested" card either, for the same reason.
 */
export default function SyncStatusBanner({ status, unavailable }: SyncStatusBannerProps) {
  if (unavailable) {
    return (
      <div className="sync-status-banner-shell">
        <div className="sync-status-banner">
          <span className="sync-status-banner-empty">Status unavailable</span>
        </div>
      </div>
    )
  }

  const cards = (status?.stages.filter(stage => VISIBLE_STATES.has(stage.state)) ?? []).map(renderCard)

  return (
    <div className="sync-status-banner-shell">
      <div className="sync-status-banner">
        {cards.length > 0 ? cards : <span className="sync-status-banner-empty">No sync in progress</span>}
      </div>
    </div>
  )
}

function renderCard(stage: SyncStageStatus) {
  const label = stageLabel(stage.key)
  if (stage.state === 'running') {
    return (
      <div key={stage.key} className="sync-status-card syncing" title={stage.message}>
        <span className="sync-status-card-label">Syncing {label}</span>
        <span className="sync-status-card-dot" />
      </div>
    )
  }
  if (stage.state === 'failed') {
    return (
      <div key={stage.key} className="sync-status-card failed" title={stage.message || `${label} failed`}>
        <span className="sync-status-card-label">{label} Failed</span>
      </div>
    )
  }
  return (
    <div key={stage.key} className="sync-status-card success">
      <span className="sync-status-card-label">{label} Synced</span>
    </div>
  )
}
