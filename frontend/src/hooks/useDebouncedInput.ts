import { useEffect, useRef, useState } from 'react'

/** Idle interval before a typed search draft commits. */
export const SEARCH_DEBOUNCE_MS = 300

/**
 * Holds an immediately-editable draft that mirrors `committedValue`, and calls
 * `onDebouncedChange` with the latest draft once the user has been idle for
 * `SEARCH_DEBOUNCE_MS`.
 *
 * The timer restarts on every draft change, external changes to `committedValue`
 * (URL navigation, a parent rerender) resynchronize the draft and cancel any
 * pending commit, and `onDebouncedChange` is read from a ref so a changing
 * callback identity never restarts an otherwise valid timer.
 */
export function useDebouncedInput(
  committedValue: string,
  onDebouncedChange: (value: string) => void,
): [string, (value: string) => void] {
  const [draft, setDraft] = useState(committedValue)
  const onDebouncedChangeRef = useRef(onDebouncedChange)
  onDebouncedChangeRef.current = onDebouncedChange

  useEffect(() => {
    setDraft(committedValue)
  }, [committedValue])

  useEffect(() => {
    if (draft === committedValue) return
    const timer = setTimeout(() => {
      onDebouncedChangeRef.current(draft)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [draft, committedValue])

  return [draft, setDraft]
}

/**
 * Same contract as {@link useDebouncedInput}, but for a fixed set of fields that must settle
 * on one shared timer instead of one independent timer each: typing in any field restarts the
 * single timer, and once idle for `SEARCH_DEBOUNCE_MS` all fields commit together in one
 * `onDebouncedChange` call. Use this when several draft fields feed the same commit handler
 * and committing them one at a time could race (e.g. several `setSearchParams` calls landing
 * in the same tick, each built from the same pre-commit params).
 */
export function useDebouncedFields<T extends Record<string, string>>(
  committedValues: T,
  onDebouncedChange: (values: T) => void,
): [T, (key: keyof T, value: string) => void] {
  const [drafts, setDrafts] = useState(committedValues)
  const onDebouncedChangeRef = useRef(onDebouncedChange)
  onDebouncedChangeRef.current = onDebouncedChange

  const committedKey = JSON.stringify(committedValues)
  const draftsKey = JSON.stringify(drafts)

  useEffect(() => {
    setDrafts(committedValues)
    // committedKey is the content-based identity of committedValues; committedValues itself
    // is a fresh object every render and would defeat the comparison.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [committedKey])

  useEffect(() => {
    if (draftsKey === committedKey) return
    const timer = setTimeout(() => {
      onDebouncedChangeRef.current(drafts)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftsKey, committedKey])

  const setDraft = (key: keyof T, value: string) => {
    setDrafts(prev => ({ ...prev, [key]: value }))
  }

  return [drafts, setDraft]
}
