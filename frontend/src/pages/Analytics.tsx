import { useEffect } from 'react'
import type { TopVideoSortBy } from '@/types'
import Tabs from '@/components/Tabs'
import type { TabOption } from '@/components/Tabs'
import FilterBar from '@/components/FilterBar'
import AnalyticsTab from '@/components/AnalyticsTab'
import TrafficSourcesTab from '@/components/TrafficSourcesTab'
import CommentsTab from '@/components/CommentsTab'
import { TRAFFIC_SOURCES_SUB_TABS, toTrafficSourcesSubTab } from '@/lib/trafficSources'
import { lastNDates } from '@/lib/dates'
import { useCollectionAnalytics } from '@/hooks/useCollectionAnalytics'
import { useReplaceSearchParams } from '@/hooks/useReplaceSearchParams'
import { useDebouncedInput } from '@/hooks/useDebouncedInput'
import './Analytics.css'

type Tab = 'analytics' | 'traffic-sources' | 'comments'

const TABS: readonly TabOption<Tab>[] = [
  { value: 'analytics', label: 'Analytics' },
  { value: 'traffic-sources', label: 'Traffic Sources' },
  { value: 'comments', label: 'Comments' },
]

export default function Analytics() {
  const [searchParams, setParams] = useReplaceSearchParams()
  const tab = (searchParams.get('tab') as Tab) ?? 'analytics'
  const startDate = searchParams.has('start_date') ? searchParams.get('start_date')! : lastNDates(28)[0]
  const endDate = searchParams.has('end_date') ? searchParams.get('end_date')! : lastNDates(28)[1]
  const title = searchParams.get('title') ?? ''
  const contentType = searchParams.get('content_type') ?? ''
  const privacyStatus = searchParams.get('privacy_status') ?? ''
  const rawTopVideosSortBy = searchParams.get('top_videos_sort_by')
  const topVideosSortBy: TopVideoSortBy = rawTopVideosSortBy === 'views' ? 'views' : 'watch_time'
  const tsTab = toTrafficSourcesSubTab(searchParams.get('ts_tab'), TRAFFIC_SOURCES_SUB_TABS)

  const data = useCollectionAnalytics(
    { kind: 'channel' },
    { startDate, endDate, title, contentType, privacyStatus },
    topVideosSortBy,
    tab === 'traffic-sources' && tsTab === 'related',
  )

  // A bare route has no explicit tab; write the derived default back so the URL matches what renders.
  useEffect(() => {
    if (searchParams.has('tab')) return
    setParams({ tab: 'analytics' })
  }, [searchParams, setParams])

  const handleTopVideosSort = (sortBy: TopVideoSortBy) => {
    if (sortBy !== topVideosSortBy) setParams({ top_videos_sort_by: sortBy })
  }

  const [titleDraft, setTitleDraft] = useDebouncedInput(title, t => setParams({ title: t || null }))

  return (
    <div className="page analytics-page">
      <div className="page-header">
        <h1>Analytics</h1>
      </div>

      <Tabs options={TABS} value={tab} onChange={t => setParams({ tab: t })} />

      {/* Comments filter on their own publication dates and carry their own filter bar,
          so the shared analytics date range does not apply to that tab. */}
      {tab !== 'comments' && (
      <FilterBar
        dates={{
          startDate: { value: startDate, onChange: v => setParams({ start_date: v }) },
          endDate: { value: endDate, onChange: v => setParams({ end_date: v }) },
          onPeriodChange: (sd, ed) => setParams({ start_date: sd, end_date: ed }),
        }}
        title={{ value: titleDraft, onChange: setTitleDraft }}
        contentType={{ value: contentType, onChange: v => setParams({ content_type: v || null }) }}
        privacyStatus={{ value: privacyStatus, onChange: v => setParams({ privacy_status: v || null }) }}
      />
      )}

      {tab === 'comments' ? (
        <CommentsTab scope={{ kind: 'channel' }} />
      ) : tab === 'analytics' ? (
        <AnalyticsTab data={data} topVideosSortBy={topVideosSortBy} onTopVideosSort={handleTopVideosSort} />
      ) : (
        <TrafficSourcesTab data={data} subTab={tsTab} onSubTabChange={t => setParams({ ts_tab: t })} />
      )}
    </div>
  )
}
