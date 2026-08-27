import type { ReactNode, Ref } from 'react'
import '@/components/AsyncCard.css'

/**
 * Which shell the card renders.
 *
 * - `card` — the shared glass `.card` surface, for content laid out inside padding.
 * - `table` — the same surface with the shell visuals moved off the `<table>`, so a
 *   card-style table scrolls inside a stable wrapper instead of being the card itself.
 * - `plain` — a stable wrapper with no surface of its own, for content that is already a
 *   stack of cards. Its loading and empty states carry the card surface instead.
 */
export type AsyncCardVariant = 'card' | 'table' | 'plain'

interface AsyncCardProps {
  /** True while the request backing this card is in flight, including every refetch. */
  loading: boolean
  /** Message for a rejected request. Rendered only once the request has finished. */
  error?: string | null
  /** True when the request succeeded with no results. Rendered only once it has finished. */
  empty?: boolean
  emptyMessage?: string
  loadingLabel?: string
  variant?: AsyncCardVariant
  /** Extra classes for the outer shell. */
  className?: string
  /** Extra classes for the inner state region. */
  bodyClassName?: string
  /** Rendered in the shell above the state region, so it stays visible while loading. */
  heading?: ReactNode
  /** Attached to the shell, which stays mounted across every state. */
  shellRef?: Ref<HTMLDivElement>
  children: ReactNode
}

const DEFAULT_LOADING_LABEL = 'Loading...'
const DEFAULT_EMPTY_MESSAGE = 'No data'

const SHELL_CLASSES: Readonly<Record<AsyncCardVariant, string>> = {
  card: 'async-card card',
  table: 'async-card card async-card--table',
  plain: 'async-card async-card--plain',
}

/**
 * A card whose outer shell is mounted from the first render and never branches away.
 *
 * Only the inner state region switches, in a fixed loading → error → empty → content
 * order, so a pending request can never show an empty or error message and a refetch
 * cannot drop the shell out of the layout.
 */
export default function AsyncCard({
  loading,
  error = null,
  empty = false,
  emptyMessage = DEFAULT_EMPTY_MESSAGE,
  loadingLabel = DEFAULT_LOADING_LABEL,
  variant = 'card',
  className,
  bodyClassName,
  heading,
  shellRef,
  children,
}: AsyncCardProps) {
  // A plain shell has no surface of its own, so its own states supply one.
  const stateSurface = variant === 'plain' ? ' card' : ''

  return (
    <div className={`${SHELL_CLASSES[variant]}${className ? ` ${className}` : ''}`} ref={shellRef}>
      {heading}
      <div className={`async-card-body${bodyClassName ? ` ${bodyClassName}` : ''}`}>
        {loading ? (
          <div className={`async-card-loading${stateSurface}`} role="status">
            <span className="async-card-spinner" aria-hidden="true" />
            <span className="async-card-loading-label">{loadingLabel}</span>
          </div>
        ) : error ? (
          <p className={`async-card-error${stateSurface}`} role="alert">{error}</p>
        ) : empty ? (
          <p className={`async-card-empty${stateSurface}`}>{emptyMessage}</p>
        ) : (
          children
        )}
      </div>
    </div>
  )
}
