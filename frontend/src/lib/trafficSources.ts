import type { TrafficSourceRow } from '@/types'

const TRAFFIC_SOURCE_LABELS: Record<string, string> = {
  YT_SEARCH: 'YouTube Search',
  YT_CHANNEL: 'Channel Page',
  YT_OTHER_PAGE: 'Other YouTube Page',
  EXT_URL: 'External',
  NO_LINK_OTHER: 'Direct or Unknown',
  NO_LINK_EMBEDDED: 'Embedded Player',
  RELATED_VIDEO: 'Suggested Videos',
  SUBSCRIBER: 'Subscriber Feed',
  PLAYLIST: 'Playlist',
  NOTIFICATION: 'Notification',
  PROMOTED: 'Promoted',
  END_SCREEN: 'End Screen',
  ANNOTATION: 'Annotation',
  CAMPAIGN_CARD: 'Campaign Card',
  ADVERTISING: 'Advertising',
  SHORTS: 'Shorts Feed',
}

export function formatTrafficSource(type: string): string {
  return TRAFFIC_SOURCE_LABELS[type] ?? type.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())
}

// Fixed categorical order (never cycled) — every traffic source type keeps the
// same color everywhere it's rendered (table bars, chart lines), regardless of
// its rank in any particular filtered view.
export const TRAFFIC_SOURCE_OTHER_COLOR = '#898781'

// All 16 slots validated together via the dataviz skill's validate_palette.js
// (lightness band, chroma floor, and CVD separation all PASS at --mode light).
const TRAFFIC_SOURCE_COLORS: Record<string, string> = {
  YT_SEARCH: '#2a78d6',
  SUBSCRIBER: '#1baf7a',
  RELATED_VIDEO: '#eda100',
  YT_CHANNEL: '#008300',
  PLAYLIST: '#4a3aa7',
  EXT_URL: '#e34948',
  NOTIFICATION: '#e87ba4',
  NO_LINK_OTHER: '#eb6834',
  SHORTS: '#0d5c8c',
  PROMOTED: '#a0522d',
  END_SCREEN: '#5c6bc0',
  ANNOTATION: '#8bc34a',
  CAMPAIGN_CARD: '#ad1457',
  ADVERTISING: '#1a7fac',
  YT_OTHER_PAGE: '#c2a000',
  NO_LINK_EMBEDDED: '#c06638',
}

export function getTrafficSourceColor(type: string): string {
  return TRAFFIC_SOURCE_COLORS[type] ?? TRAFFIC_SOURCE_OTHER_COLOR
}

export interface TrafficSourceTotals {
  traffic_source_type: string
  views: number
  watch_time_minutes: number
}

/** Sum views/watch time per traffic source type across all weeks, sorted by views descending. */
export function aggregateTrafficSourceTotals(rows: TrafficSourceRow[]): TrafficSourceTotals[] {
  const byType = new Map<string, TrafficSourceTotals>()
  for (const r of rows) {
    const existing = byType.get(r.traffic_source_type)
    if (existing) {
      existing.views += r.views
      existing.watch_time_minutes += r.watch_time_minutes
    } else {
      byType.set(r.traffic_source_type, { traffic_source_type: r.traffic_source_type, views: r.views, watch_time_minutes: r.watch_time_minutes })
    }
  }
  return [...byType.values()].sort((a, b) => b.views - a.views)
}
