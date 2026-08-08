import { useEffect, useState } from 'react'
import { getDateRange, getSyncStatus, triggerSync } from '@/api'
import type {
  PeriodAwareSyncStage,
  SyncPlan,
  SyncPlanStage,
  SyncStage,
  SyncStatusResponse,
} from '@/types'
import './Sync.css'

const STATUS_POLL_MS = 5000

/** Period selector values: the two fixed scopes, or a year rendered as its own value. */
const INCREMENTAL = 'incremental'
const ALL = 'all'

interface StageRow {
  stage: SyncStage
  label: string
  description: string
}

const STAGE_ROWS: readonly StageRow[] = [
  { stage: 'playlists', label: 'Playlists', description: 'Playlists metadata and playlist items' },
  { stage: 'videos', label: 'Videos', description: 'Video and video metadata' },
  { stage: 'pruning', label: 'Pruning', description: 'Removes videos no longer found during complete discovery' },
  { stage: 'video_analytics', label: 'Video Analytics', description: 'Daily per-video metrics' },
  { stage: 'video_traffic_sources', label: 'Traffic Sources', description: 'Daily video traffic metrics' },
  { stage: 'fx_rates', label: 'FX Rates', description: 'USD to SGD conversion rates' },
]

const PERIOD_AWARE_STAGES: readonly PeriodAwareSyncStage[] = ['video_analytics', 'video_traffic_sources']

function isPeriodAware(stage: SyncStage): stage is PeriodAwareSyncStage {
  return (PERIOD_AWARE_STAGES as readonly SyncStage[]).includes(stage)
}

type IncludedMap = Record<SyncStage, boolean>
type PeriodMap = Record<PeriodAwareSyncStage, string>

const ALL_INCLUDED: IncludedMap = {
  playlists: true,
  videos: true,
  pruning: false,
  video_analytics: true,
  video_traffic_sources: true,
  fx_rates: true,
}

const DEFAULT_PERIODS: PeriodMap = {
  video_analytics: INCREMENTAL,
  video_traffic_sources: INCREMENTAL,
}

interface PeriodSelectProps {
  stage: PeriodAwareSyncStage
  label: string
  value: string
  years: readonly number[]
  disabled: boolean
  onChange: (stage: PeriodAwareSyncStage, value: string) => void
}

/** Period selector for one period-aware stage. Kept separate so the stage stays narrowed. */
function StagePeriodSelect({ stage, label, value, years, disabled, onChange }: PeriodSelectProps) {
  return (
    <select
      className="sync-period-select"
      aria-label={`${label} period`}
      value={value}
      disabled={disabled}
      onChange={e => onChange(stage, e.target.value)}
    >
      <option value={INCREMENTAL}>New data only</option>
      <option value={ALL}>Full history</option>
      {years.map(year => (
        <option key={year} value={String(year)}>{year}</option>
      ))}
    </select>
  )
}

/** Convert one selector value into the stage entry the API expects. */
function toPlanStage(stage: SyncStage, period: string): SyncPlanStage {
  if (!isPeriodAware(stage)) return { stage }
  if (period === INCREMENTAL) return { stage, scope: INCREMENTAL }
  if (period === ALL) return { stage, scope: ALL }
  return { stage, scope: 'year', year: Number(period) }
}

export default function Sync() {
  const [included, setIncluded] = useState<IncludedMap>(ALL_INCLUDED)
  const [periods, setPeriods] = useState<PeriodMap>(DEFAULT_PERIODS)
  const [earliestYear, setEarliestYear] = useState<number | null>(null)
  const [status, setStatus] = useState<SyncStatusResponse | null>(null)
  const [statusUnavailable, setStatusUnavailable] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const poll = () =>
      getSyncStatus()
        .then(s => {
          setStatus(s)
          setStatusUnavailable(false)
        })
        .catch(() => setStatusUnavailable(true))
    poll()
    const id = setInterval(poll, STATUS_POLL_MS)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    getDateRange()
      .then((data: { earliest_year: number | null }) => setEarliestYear(data.earliest_year))
      .catch(() => {})
  }, [])

  const currentYear = new Date().getFullYear()
  const years = earliestYear && earliestYear <= currentYear
    ? Array.from({ length: currentYear - earliestYear + 1 }, (_, i) => currentYear - i)
    : []

  const isSyncing = status?.state === 'running'
  const awaitingFirstStatus = status === null
  const locked = isSyncing || submitting || awaitingFirstStatus || statusUnavailable
  const selectedCount = STAGE_ROWS.filter(row => included[row.stage]).length

  const buildPlan = (): SyncPlan => ({
    stages: STAGE_ROWS
      .filter(row => included[row.stage])
      .map(row => toPlanStage(row.stage, isPeriodAware(row.stage) ? periods[row.stage] : INCREMENTAL)),
  })

  const handleSubmit = () => {
    setSubmitting(true)
    setError(null)
    triggerSync(buildPlan())
      .then(() =>
        getSyncStatus()
          .then(s => {
            setStatus(s)
            setStatusUnavailable(false)
          })
          .catch(() => setStatusUnavailable(true))
      )
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Could not start sync')
      })
      .finally(() => setSubmitting(false))
  }

  const toggleStage = (stage: SyncStage) => {
    setIncluded(prev => {
      const next = { ...prev, [stage]: !prev[stage] }
      if (stage === 'pruning' && next.pruning) {
        next.playlists = true
        next.videos = true
      }
      if ((stage === 'playlists' || stage === 'videos') && !next[stage]) {
        next.pruning = false
      }
      return next
    })
  }

  const setPeriod = (stage: PeriodAwareSyncStage, value: string) => {
    setPeriods(prev => ({ ...prev, [stage]: value }))
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Sync</h1>
      </div>

      {(statusUnavailable || awaitingFirstStatus) && (
        <div className="sync-status-banner" role="status">
          {statusUnavailable ? 'Status unavailable' : 'Checking sync status...'}
        </div>
      )}

      {status && !isSyncing && (status.state === 'success' || status.state === 'failed') && (
        <div className={`sync-result sync-result-${status.state}`} role="status">
          {status.message}
        </div>
      )}

      <table className="data-table sync-table">
        <colgroup>
          <col className="sync-col-include" />
          <col />
          <col className="sync-col-period" />
        </colgroup>
        <thead>
          <tr>
            <th>Include</th>
            <th>Stage</th>
            <th>Period</th>
          </tr>
        </thead>
        <tbody>
          {STAGE_ROWS.map(({ stage, label, description }) => (
            <tr key={stage}>
              <td>
                <input
                  type="checkbox"
                  className="sync-checkbox"
                  id={`sync-include-${stage}`}
                  checked={included[stage]}
                  disabled={locked}
                  onChange={() => toggleStage(stage)}
                />
              </td>
              <td>
                <label className="sync-stage-label" htmlFor={`sync-include-${stage}`}>
                  {label}
                </label>
                <span className="sync-stage-description">{description}</span>
              </td>
              <td>
                {isPeriodAware(stage) ? (
                  <StagePeriodSelect
                    stage={stage}
                    label={label}
                    value={periods[stage]}
                    years={years}
                    disabled={locked || !included[stage]}
                    onChange={setPeriod}
                  />
                ) : (
                  <span className="sync-period-na">Not applicable</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {error && <p className="sync-error" role="alert">{error}</p>}

      <button
        type="button"
        className="btn-primary sync-submit"
        disabled={locked || selectedCount === 0}
        onClick={handleSubmit}
      >
        {isSyncing
          ? 'Sync in progress'
          : statusUnavailable
            ? 'Status unavailable'
            : awaitingFirstStatus
              ? 'Waiting for status...'
              : submitting
                ? 'Starting...'
                : 'Sync selected'}
      </button>
    </div>
  )
}
