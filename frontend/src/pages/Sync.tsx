import { useEffect, useState } from 'react'
import { getDateRange, getSyncRuns, getSyncStatus, triggerSync } from '@/api'
import type {
  PeriodAwareSyncStage,
  ScopeAwareSyncScope,
  ScopeAwareSyncStage,
  SyncPlan,
  SyncPlanStage,
  SyncRun,
  SyncRunStatus,
  SyncStage,
  SyncStatusResponse,
} from '@/types'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import './Sync.css'

const STATUS_POLL_MS = 5000
const HISTORY_PAGE_SIZE = 25

/** Rendered wherever a stored value is absent or unrecognised. */
const EMPTY_CELL = '—'

type Tab = 'sync' | 'history'

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
  { stage: 'comments', label: 'Comments', description: 'Top-level comments and commenters on stored videos' },
  { stage: 'pruning', label: 'Pruning', description: 'Removes videos no longer found during complete discovery' },
  { stage: 'video_analytics', label: 'Video Analytics', description: 'Daily per-video metrics' },
  { stage: 'video_traffic_sources', label: 'Traffic Sources', description: 'Daily video traffic metrics' },
  { stage: 'fx_rates', label: 'FX Rates', description: 'USD to SGD conversion rates' },
]

const PERIOD_AWARE_STAGES: readonly PeriodAwareSyncStage[] = ['video_analytics', 'video_traffic_sources']

const SCOPE_AWARE_STAGES: readonly ScopeAwareSyncStage[] = ['comments']

function isPeriodAware(stage: SyncStage): stage is PeriodAwareSyncStage {
  return (PERIOD_AWARE_STAGES as readonly SyncStage[]).includes(stage)
}

function isScopeAware(stage: SyncStage): stage is ScopeAwareSyncStage {
  return (SCOPE_AWARE_STAGES as readonly SyncStage[]).includes(stage)
}

type IncludedMap = Record<SyncStage, boolean>
type PeriodMap = Record<PeriodAwareSyncStage, string>
type ScopeMap = Record<ScopeAwareSyncStage, ScopeAwareSyncScope>

const ALL_INCLUDED: IncludedMap = {
  playlists: true,
  videos: true,
  comments: true,
  pruning: false,
  video_analytics: true,
  video_traffic_sources: true,
  fx_rates: true,
}

const DEFAULT_PERIODS: PeriodMap = {
  video_analytics: INCREMENTAL,
  video_traffic_sources: INCREMENTAL,
}

const DEFAULT_SCOPES: ScopeMap = {
  comments: INCREMENTAL,
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

interface ScopeSelectProps {
  stage: ScopeAwareSyncStage
  label: string
  value: ScopeAwareSyncScope
  disabled: boolean
  onChange: (stage: ScopeAwareSyncStage, value: ScopeAwareSyncScope) => void
}

/**
 * Scope selector for one scope-aware stage. Deliberately offers no year: a comments scan
 * walks each video's threads newest-first to a boundary, so a single year cannot be
 * requested without reading everything newer than it anyway.
 */
function StageScopeSelect({ stage, label, value, disabled, onChange }: ScopeSelectProps) {
  return (
    <select
      className="sync-period-select"
      aria-label={`${label} scope`}
      value={value}
      disabled={disabled}
      onChange={e => onChange(stage, e.target.value as ScopeAwareSyncScope)}
    >
      <option value={INCREMENTAL}>Incremental</option>
      <option value={ALL}>All</option>
    </select>
  )
}

/** Convert one selector value into the stage entry the API expects. */
function toPlanStage(stage: SyncStage, period: string): SyncPlanStage {
  if (isScopeAware(stage)) {
    return { stage, scope: period === ALL ? ALL : INCREMENTAL }
  }
  if (!isPeriodAware(stage)) return { stage }
  if (period === INCREMENTAL) return { stage, scope: INCREMENTAL }
  if (period === ALL) return { stage, scope: ALL }
  return { stage, scope: 'year', year: Number(period) }
}

const STAGE_LABELS: Readonly<Record<string, string>> = Object.fromEntries(
  STAGE_ROWS.map(row => [row.stage, row.label]),
)

const RUN_STATUS_LABELS: Readonly<Record<SyncRunStatus, string>> = {
  running: 'Running',
  success: 'Success',
  failed: 'Failed',
}

/** Human stage name, falling back to the stored value for a stage the UI no longer offers. */
function stageLabel(syncType: string): string {
  return STAGE_LABELS[syncType] ?? syncType
}

/** A selected year takes precedence; otherwise describe the stored scope. */
function scopeLabel(run: SyncRun): string {
  if (run.year !== null) return String(run.year)
  if (run.scope === INCREMENTAL) return 'Incremental'
  if (run.scope === ALL) return 'All'
  return EMPTY_CELL
}

function runStatusLabel(status: SyncRunStatus): string {
  return RUN_STATUS_LABELS[status] ?? status
}

/** Render a stored UTC timestamp in the browser's locale, or an em dash when absent. */
function formatTimestamp(value: string | null): string {
  if (!value) return EMPTY_CELL
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? EMPTY_CELL : parsed.toLocaleString()
}

/** Parse a URL page value, ignoring zero, negative, fractional, and non-numeric input. */
function parsePage(raw: string | null): number {
  const parsed = Number(raw)
  if (!Number.isInteger(parsed) || parsed < 1) return 1
  return parsed
}

export default function Sync() {
  const [searchParams, setSearchParams] = useReplaceSearchParams()
  const tab: Tab = searchParams.get('tab') === 'history' ? 'history' : 'sync'
  const historyPage = parsePage(searchParams.get('history_page'))

  const [historyItems, setHistoryItems] = useState<SyncRun[]>([])
  const [historyTotal, setHistoryTotal] = useState(0)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)

  const [included, setIncluded] = useState<IncludedMap>(ALL_INCLUDED)
  const [periods, setPeriods] = useState<PeriodMap>(DEFAULT_PERIODS)
  const [scopes, setScopes] = useState<ScopeMap>(DEFAULT_SCOPES)
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

  // History is fetched only while its tab is open, and a superseded request is discarded so
  // stale rows or errors cannot overwrite the view the user has since moved to.
  useEffect(() => {
    if (tab !== 'history') return
    let active = true
    setHistoryLoading(true)
    setHistoryError(null)
    getSyncRuns(historyPage, HISTORY_PAGE_SIZE)
      .then(data => {
        if (!active) return
        setHistoryItems(data.items ?? [])
        setHistoryTotal(data.total ?? 0)
      })
      .catch((err: unknown) => {
        if (!active) return
        setHistoryItems([])
        setHistoryTotal(0)
        setHistoryError(err instanceof Error ? err.message : 'Could not load sync history')
      })
      .finally(() => {
        if (active) setHistoryLoading(false)
      })
    return () => { active = false }
  }, [tab, historyPage])

  const currentYear = new Date().getFullYear()
  const years = earliestYear && earliestYear <= currentYear
    ? Array.from({ length: currentYear - earliestYear + 1 }, (_, i) => currentYear - i)
    : []

  const isSyncing = status?.state === 'running'
  const awaitingFirstStatus = status === null
  const locked = isSyncing || submitting || awaitingFirstStatus || statusUnavailable
  const selectedCount = STAGE_ROWS.filter(row => included[row.stage]).length

  /** The selector value backing one stage row, or the incremental default when it has none. */
  const selectorValue = (stage: SyncStage): string => {
    if (isPeriodAware(stage)) return periods[stage]
    if (isScopeAware(stage)) return scopes[stage]
    return INCREMENTAL
  }

  const buildPlan = (): SyncPlan => ({
    stages: STAGE_ROWS
      .filter(row => included[row.stage])
      .map(row => toPlanStage(row.stage, selectorValue(row.stage))),
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

  const setScope = (stage: ScopeAwareSyncStage, value: ScopeAwareSyncScope) => {
    setScopes(prev => ({ ...prev, [stage]: value }))
  }

  /** Switching tabs changes only `tab`; a non-default history page is kept for the return trip. */
  const handleTabChange = (next: Tab) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev)
      if (next === 'history') params.set('tab', next)
      else params.delete('tab')
      return params
    })
  }

  const setHistoryPage = (page: number) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev)
      if (page > 1) params.set('history_page', String(page))
      else params.delete('history_page')
      return params
    })
  }

  const historyTotalPages = Math.ceil(historyTotal / HISTORY_PAGE_SIZE)

  return (
    <div className="page">
      <div className="page-header">
        <h1>Sync</h1>
      </div>

      <div className="tabs">
        <button
          type="button"
          className={`tab${tab === 'sync' ? ' active' : ''}`}
          onClick={() => handleTabChange('sync')}
        >
          Sync
        </button>
        <button
          type="button"
          className={`tab${tab === 'history' ? ' active' : ''}`}
          onClick={() => handleTabChange('history')}
        >
          History
        </button>
      </div>

      {tab === 'sync' ? (
        <>
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
                    ) : isScopeAware(stage) ? (
                      <StageScopeSelect
                        stage={stage}
                        label={label}
                        value={scopes[stage]}
                        disabled={locked || !included[stage]}
                        onChange={setScope}
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
            Sync selected
          </button>
        </>
      ) : historyLoading ? (
        <p className="loading">Loading...</p>
      ) : historyError ? (
        <p className="sync-error" role="alert">{historyError}</p>
      ) : historyItems.length === 0 ? (
        <p className="sync-history-empty">No sync runs recorded.</p>
      ) : (
        <>
          <div className="table-overflow-wrap">
            <table className="data-table sync-history-table">
              <colgroup>
                <col className="sync-history-col-stage" />
                <col className="sync-history-col-scope" />
                <col className="sync-history-col-status" />
                <col className="sync-history-col-time" />
                <col className="sync-history-col-time" />
                <col className="sync-history-col-count" />
                <col className="sync-history-col-count" />
                <col className="sync-history-col-count" />
              </colgroup>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Scope</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Completed</th>
                  <th>Fetched</th>
                  <th>Written</th>
                  <th>Deleted</th>
                </tr>
              </thead>
              <tbody>
                {historyItems.map(run => (
                  <tr key={run.id}>
                    <td>{stageLabel(run.sync_type)}</td>
                    <td>{scopeLabel(run)}</td>
                    <td>
                      <span className={`sync-history-status sync-history-status-${run.status}`}>
                        {runStatusLabel(run.status)}
                      </span>
                    </td>
                    <td>{formatTimestamp(run.started_at)}</td>
                    <td>{formatTimestamp(run.completed_at)}</td>
                    <td>{run.rows_fetched.toLocaleString()}</td>
                    <td>{run.rows_written.toLocaleString()}</td>
                    <td>{run.rows_deleted.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setHistoryPage(historyPage - 1)}
              disabled={historyPage <= 1}
            >
              Previous
            </button>
            <span className="pagination-info">Page {historyPage} of {historyTotalPages}</span>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setHistoryPage(historyPage + 1)}
              disabled={historyPage >= historyTotalPages}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
