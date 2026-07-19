import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { SetURLSearchParams } from 'react-router-dom'

/**
 * Wraps useSearchParams() so query-only updates always replace the current
 * history entry instead of pushing a new one. Pathname navigation (Link,
 * navigate()) is unaffected and continues to push history as usual.
 */
export function useReplaceSearchParams(): [URLSearchParams, SetURLSearchParams] {
  const [searchParams, setSearchParams] = useSearchParams()

  const setReplaceSearchParams: SetURLSearchParams = useCallback((nextInit, navigateOpts) => {
    setSearchParams(nextInit, { ...navigateOpts, replace: true })
  }, [setSearchParams])

  return [searchParams, setReplaceSearchParams]
}
