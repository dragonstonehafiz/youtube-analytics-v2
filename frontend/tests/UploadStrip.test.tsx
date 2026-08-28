// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { PublishedVideo } from '@/types'
import {
  BADGE_DIAMETER,
  BUCKET_WIDTH,
  CHART_RIGHT,
  UploadStrip,
  YAXIS_WIDTH,
  computeUploadBuckets,
  type UploadBucket,
} from '@/components/UploadStrip'

afterEach(() => {
  cleanup()
})

function pv(overrides: Partial<PublishedVideo> = {}): PublishedVideo {
  return {
    id: 'video-1',
    title: 'A video',
    published_at: '2024-01-01T00:00:00+00:00',
    thumbnail_url: null,
    content_type: 'video',
    ...overrides,
  }
}

function row(date: string): { date: string } {
  return { date }
}

/** 30 daily rows from 2024-01-01 through 2024-01-30. */
function monthOfRows(): { date: string }[] {
  const rows: { date: string }[] = []
  for (let d = 1; d <= 30; d++) rows.push(row(`2024-01-${String(d).padStart(2, '0')}`))
  return rows
}

describe('computeUploadBuckets', () => {
  it('returns no buckets when there are no uploads, no rows, or no usable width', () => {
    const rows = monthOfRows()
    expect(computeUploadBuckets([], [pv()], 800)).toEqual([])
    expect(computeUploadBuckets(rows, undefined, 800)).toEqual([])
    expect(computeUploadBuckets(rows, [], 800)).toEqual([])
    expect(computeUploadBuckets(rows, [pv()], 0)).toEqual([])
  })

  it('groups same-bucket uploads by content type and counts them', () => {
    const rows = monthOfRows()
    const uploads = [
      pv({ id: 'v1', published_at: '2024-01-15T00:00:00+00:00', content_type: 'video' }),
      pv({ id: 'v2', published_at: '2024-01-15T00:00:00+00:00', content_type: 'video' }),
      pv({ id: 's1', published_at: '2024-01-15T00:00:00+00:00', content_type: 'short' }),
    ]
    const buckets = computeUploadBuckets(rows, uploads, 800)
    const middle = buckets.find(b => b.videos.length > 0 && b.shorts.length > 0)
    expect(middle).toBeDefined()
    expect(middle!.videos).toHaveLength(2)
    expect(middle!.shorts).toHaveLength(1)
  })

  it('inclusively keeps uploads on the first/last row dates and drops uploads outside that range', () => {
    const rows = monthOfRows()
    const uploads = [
      pv({ id: 'on-first', published_at: '2024-01-01T00:00:00+00:00' }),
      pv({ id: 'on-last', published_at: '2024-01-30T00:00:00+00:00' }),
      pv({ id: 'before-first', published_at: '2023-12-31T00:00:00+00:00' }),
      pv({ id: 'after-last', published_at: '2024-01-31T00:00:00+00:00' }),
    ]
    const buckets = computeUploadBuckets(rows, uploads, 800)
    const includedIds = buckets.flatMap(b => b.videos.map(v => v.id))
    expect(includedIds).toContain('on-first')
    expect(includedIds).toContain('on-last')
    expect(includedIds).not.toContain('before-first')
    expect(includedIds).not.toContain('after-last')
  })

  it('keeps a badge-radius margin from both plotting edges at a representative width', () => {
    const rows = monthOfRows()
    const uploads = [
      pv({ id: 'first', published_at: '2024-01-01T00:00:00+00:00' }),
      pv({ id: 'last', published_at: '2024-01-30T00:00:00+00:00' }),
    ]
    const cardWidth = 800
    const chartAreaWidth = cardWidth - YAXIS_WIDTH - CHART_RIGHT
    const radiusPct = (BADGE_DIAMETER / 2) / chartAreaWidth

    const buckets = computeUploadBuckets(rows, uploads, cardWidth)
    const leftmost = buckets[0]
    const rightmost = buckets[buckets.length - 1]

    expect(leftmost.leftPct).toBeGreaterThanOrEqual(radiusPct - 1e-9)
    expect(rightmost.leftPct).toBeLessThanOrEqual(1 - radiusPct + 1e-9)
  })

  it('leaves a middle bucket effectively unclamped at a wide width', () => {
    const rows = monthOfRows()
    const uploads = [pv({ id: 'mid', published_at: '2024-01-15T00:00:00+00:00' })]
    const buckets = computeUploadBuckets(rows, uploads, 800)
    expect(buckets[0].leftPct).toBeGreaterThan(0.4)
    expect(buckets[0].leftPct).toBeLessThan(0.6)
  })

  it('uses the 30px BUCKET_WIDTH to permit finer temporal buckets than a coarser allocation would', () => {
    expect(BUCKET_WIDTH).toBe(BADGE_DIAMETER + 8)

    const rows = monthOfRows()
    const cardWidth = 400
    const chartAreaWidth = cardWidth - YAXIS_WIDTH - CHART_RIGHT
    const totalDays = 29
    const bucketDays = Math.max(1, Math.ceil(totalDays / Math.floor(chartAreaWidth / BUCKET_WIDTH)))
    // Two uploads this many days apart share one bucket under the finer allocation...
    expect(bucketDays).toBeLessThan(5)

    const uploads = [
      pv({ id: 'day1', published_at: '2024-01-01T00:00:00+00:00' }),
      pv({ id: 'day5', published_at: '2024-01-05T00:00:00+00:00' }),
    ]
    const buckets = computeUploadBuckets(rows, uploads, cardWidth)
    // ...4 days apart, they land in separate buckets rather than being aggregated together.
    expect(buckets).toHaveLength(2)
    expect(buckets[0].videos).toHaveLength(1)
    expect(buckets[1].videos).toHaveLength(1)
  })

  it('places bucket centers proportionally to their real calendar gap, not their occupied-bucket ordinal', () => {
    const rows = monthOfRows()
    const uploads = [
      pv({ id: 'early', published_at: '2024-01-01T00:00:00+00:00' }),
      pv({ id: 'mid', published_at: '2024-01-05T00:00:00+00:00' }),
      pv({ id: 'late', published_at: '2024-01-29T00:00:00+00:00' }),
    ]
    const buckets = computeUploadBuckets(rows, uploads, 800)
    expect(buckets).toHaveLength(3)

    const gapEarlyToMid = buckets[1].leftPct - buckets[0].leftPct
    const gapMidToLate = buckets[2].leftPct - buckets[1].leftPct
    // mid is 4 days after early; late is 24 days after mid — a calendar-proportional
    // layout must make the second gap much larger, not equal (which ordinal spacing would).
    expect(gapMidToLate).toBeGreaterThan(gapEarlyToMid * 3)
  })

  it('merges a boundary-clamped last bucket into its neighbor when their badges overlap, combining both content types', () => {
    // 7 daily rows (Jan 1-7, totalDays=6) at cardWidth=192 (chartAreaWidth=120) give
    // maxBuckets=4, bucketDays=2. The Jan 7 upload's bucket then computes a raw center
    // past the chart's right edge; clamping it inward lands it within BADGE_DIAMETER
    // (22px) of the Jan 5 bucket, so the two are expected to merge into one column.
    const rows: { date: string }[] = []
    for (let d = 1; d <= 7; d++) rows.push(row(`2024-01-0${d}`))
    const uploads = [
      pv({ id: 'jan1', published_at: '2024-01-01T00:00:00+00:00', content_type: 'video' }),
      pv({ id: 'jan3', published_at: '2024-01-03T00:00:00+00:00', content_type: 'short' }),
      pv({ id: 'jan5', published_at: '2024-01-05T00:00:00+00:00', content_type: 'video' }),
      pv({ id: 'jan7', published_at: '2024-01-07T00:00:00+00:00', content_type: 'short' }),
    ]
    const buckets = computeUploadBuckets(rows, uploads, 192)

    expect(buckets).toHaveLength(3)
    const merged = buckets[buckets.length - 1]
    // The merge is triggered purely by column proximity, regardless of which row
    // (video/short) each side occupies — the combined column carries both.
    expect(merged.videos.map(v => v.id)).toEqual(['jan5'])
    expect(merged.shorts.map(v => v.id)).toEqual(['jan7'])
  })
})

function renderStrip(buckets: UploadBucket[]) {
  return render(
    <MemoryRouter>
      <UploadStrip buckets={buckets} />
    </MemoryRouter>,
  )
}

describe('UploadStrip', () => {
  it('renders nothing for an empty bucket list', () => {
    const { container } = renderStrip([])
    expect(container.querySelector('.upload-strip')).toBeNull()
  })

  it('renders the video row before the shorts row', () => {
    const buckets: UploadBucket[] = [
      { bucketStart: '2024-01-05', videos: [pv({ id: 'v1' })], shorts: [], leftPct: 0.3 },
      { bucketStart: '2024-01-20', videos: [], shorts: [pv({ id: 's1', content_type: 'short' })], leftPct: 0.7 },
    ]
    const { container } = renderStrip(buckets)
    const rows = container.querySelectorAll('.upload-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].classList.contains('upload-row--video')).toBe(true)
    expect(rows[1].classList.contains('upload-row--short')).toBe(true)
  })

  it('places a mixed bucket in both rows at the same horizontal position, and single-type buckets only in their own row', () => {
    const buckets: UploadBucket[] = [
      {
        bucketStart: '2024-01-15',
        videos: [pv({ id: 'v1' })],
        shorts: [pv({ id: 's1', content_type: 'short' })],
        leftPct: 0.5,
      },
      { bucketStart: '2024-01-25', videos: [pv({ id: 'v2' })], shorts: [], leftPct: 0.9 },
    ]
    const { container } = renderStrip(buckets)
    const videoRow = container.querySelector('.upload-row--video')!
    const shortRow = container.querySelector('.upload-row--short')!

    expect(videoRow.querySelectorAll('.upload-badge-slot')).toHaveLength(2)
    expect(shortRow.querySelectorAll('.upload-badge-slot')).toHaveLength(1)

    const mixedVideoSlot = videoRow.querySelector('.upload-badge-slot') as HTMLElement
    const mixedShortSlot = shortRow.querySelector('.upload-badge-slot') as HTMLElement
    expect(mixedVideoSlot.style.left).toBe(mixedShortSlot.style.left)
  })

  it('retains counts and links to the video detail page', () => {
    const buckets: UploadBucket[] = [
      {
        bucketStart: '2024-01-15',
        videos: [pv({ id: 'v1' }), pv({ id: 'v2' })],
        shorts: [],
        leftPct: 0.5,
      },
    ]
    const { getByText, container } = renderStrip(buckets)
    expect(getByText('2')).toBeTruthy()
    const link = container.querySelector('a[href="/analytics/videos/v1"]')
    expect(link).toBeTruthy()
  })
})
