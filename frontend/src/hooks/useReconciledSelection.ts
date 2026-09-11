import { useEffect, useState } from 'react'

/**
 * Tracks one dropdown's explicit selection, but only while it remains among the
 * current `options`. When the options change such that the selection is no longer
 * present, the selection resets to null so the caller naturally falls back to the new
 * options list's own first (highest-ranked) entry instead of showing a stale value.
 */
export function useReconciledSelection(options: readonly string[]): [string | null, (id: string) => void] {
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    if (selected !== null && !options.includes(selected)) {
      setSelected(null)
    }
  }, [options, selected])

  return [selected, setSelected]
}
