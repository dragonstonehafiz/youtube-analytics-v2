// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import { SEARCH_DEBOUNCE_MS, useDebouncedFields, useDebouncedInput } from '@/hooks/useDebouncedInput'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('useDebouncedInput', () => {
  it('reflects a draft update immediately without committing', () => {
    const onDebouncedChange = vi.fn()
    const { result } = renderHook(() => useDebouncedInput('', onDebouncedChange))

    act(() => result.current[1]('a'))

    expect(result.current[0]).toBe('a')
    expect(onDebouncedChange).not.toHaveBeenCalled()
  })

  it('commits only the final value after the idle interval', () => {
    const onDebouncedChange = vi.fn()
    const { result, rerender } = renderHook(
      ({ committed }) => useDebouncedInput(committed, onDebouncedChange),
      { initialProps: { committed: '' } },
    )

    act(() => result.current[1]('a'))
    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1) })
    act(() => result.current[1]('ab'))
    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1) })
    expect(onDebouncedChange).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(1) })
    expect(onDebouncedChange).toHaveBeenCalledTimes(1)
    expect(onDebouncedChange).toHaveBeenCalledWith('ab')

    rerender({ committed: '' })
  })

  it('restarts the timer on every newer keystroke', () => {
    const onDebouncedChange = vi.fn()
    const { result } = renderHook(() => useDebouncedInput('', onDebouncedChange))

    act(() => result.current[1]('a'))
    act(() => { vi.advanceTimersByTime(200) })
    act(() => result.current[1]('ab'))
    act(() => { vi.advanceTimersByTime(200) })
    expect(onDebouncedChange).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(onDebouncedChange).toHaveBeenCalledTimes(1)
    expect(onDebouncedChange).toHaveBeenCalledWith('ab')
  })

  it('delays clearing the same way as typing', () => {
    const onDebouncedChange = vi.fn()
    const { result } = renderHook(() => useDebouncedInput('existing', onDebouncedChange))

    act(() => result.current[1](''))
    expect(result.current[0]).toBe('')
    expect(onDebouncedChange).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(onDebouncedChange).toHaveBeenCalledWith('')
  })

  it('always invokes the latest callback even if identity changes across rerenders', () => {
    const first = vi.fn()
    const second = vi.fn()
    const { result, rerender } = renderHook(
      ({ onChange }) => useDebouncedInput('', onChange),
      { initialProps: { onChange: first } },
    )

    act(() => result.current[1]('a'))
    rerender({ onChange: second })
    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    expect(first).not.toHaveBeenCalled()
    expect(second).toHaveBeenCalledWith('a')
  })

  it('resynchronizes the draft when the committed value changes externally', () => {
    const onDebouncedChange = vi.fn()
    const { result, rerender } = renderHook(
      ({ committed }) => useDebouncedInput(committed, onDebouncedChange),
      { initialProps: { committed: '' } },
    )

    act(() => result.current[1]('stale draft'))
    rerender({ committed: 'external' })

    expect(result.current[0]).toBe('external')

    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(onDebouncedChange).not.toHaveBeenCalled()
  })

  it('cancels the pending timer on unmount', () => {
    const onDebouncedChange = vi.fn()
    const { result, unmount } = renderHook(() => useDebouncedInput('', onDebouncedChange))

    act(() => result.current[1]('a'))
    unmount()
    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    expect(onDebouncedChange).not.toHaveBeenCalled()
  })
})

describe('useDebouncedFields', () => {
  it('reflects a per-key draft update immediately without committing', () => {
    const onDebouncedChange = vi.fn()
    const { result } = renderHook(() => useDebouncedFields({ a: '', b: '' }, onDebouncedChange))

    act(() => result.current[1]('a', 'x'))

    expect(result.current[0]).toEqual({ a: 'x', b: '' })
    expect(onDebouncedChange).not.toHaveBeenCalled()
  })

  it('shares one timer across fields: a keystroke in another field restarts the single pending commit', () => {
    const onDebouncedChange = vi.fn()
    const { result } = renderHook(() => useDebouncedFields({ a: '', b: '' }, onDebouncedChange))

    act(() => result.current[1]('a', 'x'))
    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50) })
    act(() => result.current[1]('b', 'y'))
    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 50) })
    expect(onDebouncedChange).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(50) })
    expect(onDebouncedChange).toHaveBeenCalledTimes(1)
    expect(onDebouncedChange).toHaveBeenCalledWith({ a: 'x', b: 'y' })
  })

  it('resynchronizes all drafts when committed values change externally', () => {
    const onDebouncedChange = vi.fn()
    const { result, rerender } = renderHook(
      ({ committed }) => useDebouncedFields(committed, onDebouncedChange),
      { initialProps: { committed: { a: '', b: '' } } },
    )

    act(() => result.current[1]('a', 'stale'))
    rerender({ committed: { a: 'external', b: 'external-b' } })

    expect(result.current[0]).toEqual({ a: 'external', b: 'external-b' })

    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })
    expect(onDebouncedChange).not.toHaveBeenCalled()
  })

  it('cancels the pending timer on unmount', () => {
    const onDebouncedChange = vi.fn()
    const { result, unmount } = renderHook(() => useDebouncedFields({ a: '', b: '' }, onDebouncedChange))

    act(() => result.current[1]('a', 'x'))
    unmount()
    act(() => { vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS) })

    expect(onDebouncedChange).not.toHaveBeenCalled()
  })
})
