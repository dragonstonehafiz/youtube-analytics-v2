// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import AsyncCard from '@/components/AsyncCard'

const shell = (container: HTMLElement) => container.querySelector('.async-card')
const body = (container: HTMLElement) => container.querySelector('.async-card-body')

afterEach(() => {
  cleanup()
})

describe('card shell and state region', () => {
  it('renders the shell and the state region as different elements', () => {
    const { container } = render(
      <AsyncCard loading={false}><p>Resolved</p></AsyncCard>,
    )

    expect(shell(container)).not.toBeNull()
    expect(body(container)).not.toBeNull()
    expect(body(container)).not.toBe(shell(container))
    expect(body(container)?.parentElement).toBe(shell(container))
  })

  it('keeps the shell mounted while the request is in flight', () => {
    const { container } = render(
      <AsyncCard loading><p>Resolved</p></AsyncCard>,
    )

    expect(shell(container)?.className).toContain('card')
    expect(screen.queryByText('Resolved')).toBeNull()
  })

  it('keeps a caller heading visible in the shell while loading', () => {
    render(
      <AsyncCard loading heading={<div className="section-header">Top Videos</div>}>
        <p>Resolved</p>
      </AsyncCard>,
    )

    expect(screen.getByText('Top Videos')).toBeDefined()
  })

  it('gives the plain variant a stable shell that carries the surface on its own states', () => {
    const { container, rerender } = render(
      <AsyncCard variant="plain" loading><div className="card">A resolved card</div></AsyncCard>,
    )
    const shellBefore = shell(container)

    // The shell adds no box of its own, because the content is already a stack of cards…
    expect(shellBefore?.className).toContain('async-card--plain')
    expect(shellBefore?.className).not.toContain(' card')
    // …so each of its own states supplies one instead.
    expect(screen.getByRole('status').className).toContain('card')

    rerender(<AsyncCard variant="plain" loading={false} empty emptyMessage="Nothing here"><div /></AsyncCard>)
    expect(shell(container)).toBe(shellBefore)
    expect(screen.getByText('Nothing here').className).toContain('card')

    rerender(<AsyncCard variant="plain" loading={false} error="Request failed"><div /></AsyncCard>)
    expect(shell(container)).toBe(shellBefore)
    const alert = screen.getByRole('alert')
    expect(alert.className).toContain('card')
    expect(alert.className).toContain('async-card-error')
  })

  it('gives the table variant a shell separate from the table it holds', () => {
    const { container } = render(
      <AsyncCard variant="table" loading={false}>
        <div className="table-overflow-wrap"><table><tbody><tr><td>Cell</td></tr></tbody></table></div>
      </AsyncCard>,
    )

    const table = screen.getByRole('table')
    expect(shell(container)?.className).toContain('async-card--table')
    expect(table.closest('.async-card')).toBe(shell(container))
    expect(table).not.toBe(shell(container))
  })
})

describe('the loading indicator', () => {
  it('announces itself and hides the decorative circle', () => {
    const { container } = render(<AsyncCard loading><p>Resolved</p></AsyncCard>)

    const status = screen.getByRole('status')
    expect(status.textContent).toBe('Loading...')
    const spinner = container.querySelector('.async-card-spinner')
    expect(spinner).not.toBeNull()
    expect(spinner?.getAttribute('aria-hidden')).toBe('true')
  })

  it('uses a caller-supplied label', () => {
    render(<AsyncCard loading loadingLabel="Loading comments..."><p>Resolved</p></AsyncCard>)

    expect(screen.getByRole('status').textContent).toBe('Loading comments...')
  })

  it('renders inside the state region, not in place of the shell', () => {
    const { container } = render(<AsyncCard loading><p>Resolved</p></AsyncCard>)

    expect(screen.getByRole('status').parentElement).toBe(body(container))
  })
})

describe('state precedence', () => {
  it('shows the indicator instead of an empty message while a request is pending', () => {
    render(
      <AsyncCard loading empty emptyMessage="No videos found"><p>Resolved</p></AsyncCard>,
    )

    expect(screen.getByRole('status')).toBeDefined()
    expect(screen.queryByText('No videos found')).toBeNull()
  })

  it('shows the indicator instead of a stale error while a refetch is pending', () => {
    render(
      <AsyncCard loading error="Request failed"><p>Resolved</p></AsyncCard>,
    )

    expect(screen.getByRole('status')).toBeDefined()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows the error rather than the empty message once the request has finished', () => {
    render(
      <AsyncCard loading={false} error="Request failed" empty emptyMessage="No videos found">
        <p>Resolved</p>
      </AsyncCard>,
    )

    expect(screen.getByRole('alert').textContent).toBe('Request failed')
    expect(screen.queryByText('No videos found')).toBeNull()
    expect(screen.queryByText('Resolved')).toBeNull()
  })

  it('shows the empty message only after a request resolved with no results', () => {
    render(
      <AsyncCard loading={false} empty emptyMessage="No videos found"><p>Resolved</p></AsyncCard>,
    )

    expect(screen.getByText('No videos found')).toBeDefined()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByText('Resolved')).toBeNull()
  })
})

describe('resolving a request', () => {
  it('replaces the indicator with the content without replacing the shell', () => {
    const { container, rerender } = render(
      <AsyncCard loading><p>Resolved</p></AsyncCard>,
    )
    const shellBefore = shell(container)
    expect(screen.getByRole('status')).toBeDefined()

    rerender(<AsyncCard loading={false}><p>Resolved</p></AsyncCard>)

    expect(shell(container)).toBe(shellBefore)
    expect(screen.getByText('Resolved')).toBeDefined()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('returns to the indicator on a refetch without unmounting the shell', () => {
    const { container, rerender } = render(
      <AsyncCard loading={false}><p>Resolved</p></AsyncCard>,
    )
    const shellBefore = shell(container)

    rerender(<AsyncCard loading><p>Resolved</p></AsyncCard>)

    expect(shell(container)).toBe(shellBefore)
    expect(screen.getByRole('status')).toBeDefined()
    expect(screen.queryByText('Resolved')).toBeNull()
  })
})
