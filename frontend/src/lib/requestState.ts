import type { Dispatch, SetStateAction } from 'react'

/**
 * One request-backed surface's state: the data it has resolved, whether a request for it
 * is currently in flight, and the message for a request that failed.
 *
 * Every card that fetches its own data holds one of these, so a page can put several
 * independent requests on screen without one of them gating another's card.
 */
export interface RequestState<T> {
  data: T
  loading: boolean
  error: string | null
}

const DEFAULT_ERROR = 'Could not load this data'

/** The starting state for a surface whose first request has not resolved yet. */
export function pending<T>(data: T): RequestState<T> {
  return { data, loading: true, error: null }
}

/**
 * Drive one surface's state from one promise: loading immediately, then either the
 * resolved data or an in-card error.
 *
 * `isActive` is the owning effect's cleanup flag. A superseded request — a filter, sort,
 * page or tab change mid-flight — must not clear the newer request's indicator or replace
 * its results, so a stale completion is dropped entirely.
 */
export function track<T>(
  promise: Promise<T>,
  setState: Dispatch<SetStateAction<RequestState<T>>>,
  isActive: () => boolean,
  errorMessage: string = DEFAULT_ERROR,
): void {
  setState(prev => ({ ...prev, loading: true, error: null }))
  promise
    .then(data => {
      if (isActive()) setState({ data, loading: false, error: null })
    })
    .catch((err: unknown) => {
      if (!isActive()) return
      setState(prev => ({
        data: prev.data,
        loading: false,
        error: err instanceof Error ? err.message : errorMessage,
      }))
    })
}
