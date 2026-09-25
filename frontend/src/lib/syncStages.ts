const STAGE_LABELS: Readonly<Record<string, string>> = {
  search_related_insights: 'Search Insights',
  playlists: 'Playlists',
  videos: 'Videos',
  pruning: 'Pruning',
  fx_rates: 'FX Rates',
  comments: 'Comments',
  video_analytics: 'Video Analytics',
  video_traffic_sources: 'Traffic Sources',
  search_insights: 'Search Insights',
  related_video_insights: 'Related Video Insights',
}

/** Human stage name, falling back to the stored value for an unknown stage. */
export function stageLabel(syncType: string): string {
  return STAGE_LABELS[syncType] ?? syncType
}
