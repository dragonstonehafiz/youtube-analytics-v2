import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/** Param changes for `setParams`: a string sets the key (an empty string is kept), `null` deletes it. */
export type ParamUpdates = Record<string, string | null>

/**
 * Wraps useSearchParams() with a setter that merges updates into the current params
 * and replaces the current history entry instead of pushing a new one. Pathname
 * navigation (Link, navigate()) is unaffected and continues to push history as usual.
 */
export function useReplaceSearchParams(): [URLSearchParams, (updates: ParamUpdates) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const setParams = useCallback((updates: ParamUpdates) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        if (value === null) next.delete(key)
        else next.set(key, value)
      }
      return next
    }, { replace: true })
  }, [setSearchParams])

  return [searchParams, setParams]
}
