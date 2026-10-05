// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'

afterEach(() => {
  cleanup()
})

/** Renders the hook inside a data router so tests can read the history stack and current URL. */
function renderSetParams(initial: string) {
  let router: ReturnType<typeof createMemoryRouter> | undefined
  const { result } = renderHook(() => useReplaceSearchParams(), {
    wrapper: ({ children }: { children: ReactNode }) => {
      router ??= createMemoryRouter([{ path: '*', element: children }], { initialEntries: ['/other', initial], initialIndex: 1 })
      return <RouterProvider router={router} />
    },
  })
  return {
    setParams: (updates: Parameters<typeof result.current[1]>[0]) => act(() => result.current[1](updates)),
    search: () => router!.state.location.search,
    router: () => router!,
  }
}

describe('useReplaceSearchParams setParams', () => {
  it('sets, keeps empty strings, deletes null keys, and leaves other params alone', async () => {
    const { setParams, search } = renderSetParams('/page?keep=1&title=old&start_date=2024-01-01')
    await setParams({ title: 'new', start_date: '', extra: null })
    const params = new URLSearchParams(search())
    expect(params.get('keep')).toBe('1')
    expect(params.get('title')).toBe('new')
    expect(params.get('start_date')).toBe('')
    expect(params.has('extra')).toBe(false)

    await setParams({ title: null })
    expect(new URLSearchParams(search()).has('title')).toBe(false)
  })

  it('replaces the current history entry instead of pushing a new one', async () => {
    const { setParams, router } = renderSetParams('/page')
    await setParams({ tab: 'comments' })
    await setParams({ tab: 'analytics' })
    await act(() => router().navigate(-1))
    expect(router().state.location.pathname).toBe('/other')
  })
})
