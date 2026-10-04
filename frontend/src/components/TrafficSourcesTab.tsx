import type { CollectionScope, CollectionFilters } from '@/hooks/useCollectionAnalytics'
import {
  useCollectionOverview, useTrafficSources, useTopVideosBySource, useSearchInsights, useRelatedVideos,
} from '@/hooks/useCollectionAnalytics'
import type { RequestState } from '@/lib/requestState'
import type { TrafficSourceRow } from '@/types'
import type { TrafficSourcesSubTab } from '@/lib/trafficSources'
import { TRAFFIC_SOURCES_SUB_TABS } from '@/lib/trafficSources'
import Tabs from '@/components/Tabs'
import VideoStatsBar from '@/components/VideoStatsBar'
import TrafficSourceChart from '@/components/TrafficSourceChart'
import TrafficSourcesTable from '@/components/TrafficSourcesTable'
import TrafficSourceTopVideosPanel from '@/components/TrafficSourceTopVideosPanel'
import SearchTermsDonutCard from '@/components/SearchTermsDonutCard'
import SearchTermVideosDonutCard from '@/components/SearchTermVideosDonutCard'
import RelatedReferrerBreakdownCard from '@/components/RelatedReferrerBreakdownCard'
import RelatedDestinationsByReferrerCard from '@/components/RelatedDestinationsByReferrerCard'

interface TrafficSourcesTabProps {
  scope: CollectionScope
  filters: CollectionFilters
  subTab: TrafficSourcesSubTab
  onSubTabChange: (subTab: TrafficSourcesSubTab) => void
}

interface SubTabProps {
  scope: CollectionScope
  filters: CollectionFilters
}

/** Traffic Sources tab of the channel and playlist pages: stats, chart, and the four sub-tabs. */
export default function TrafficSourcesTab({ scope, filters, subTab, onSubTabChange }: TrafficSourcesTabProps) {
  const { stats, publishedVideos } = useCollectionOverview(scope, filters)
  const trafficSources = useTrafficSources(scope, filters)
  return (
    <>
      <VideoStatsBar stats={stats.data} loading={stats.loading} error={stats.error} />
      <TrafficSourceChart
        rows={trafficSources.data}
        uploadedVideos={publishedVideos.data}
        loading={trafficSources.loading || publishedVideos.loading}
        error={trafficSources.error ?? publishedVideos.error}
      />
      <Tabs options={TRAFFIC_SOURCES_SUB_TABS} value={subTab} onChange={onSubTabChange} className="ts-subtabs" />
      {subTab === 'sources' ? (
        <TrafficSourcesTable
          rows={trafficSources.data}
          loading={trafficSources.loading}
          error={trafficSources.error}
        />
      ) : subTab === 'top-videos' ? (
        <TopVideosBySourceSubTab scope={scope} filters={filters} trafficSources={trafficSources} />
      ) : subTab === 'search' ? (
        <SearchInsightsSubTab scope={scope} filters={filters} />
      ) : (
        <RelatedVideosSubTab scope={scope} filters={filters} />
      )}
    </>
  )
}

function TopVideosBySourceSubTab({ scope, filters, trafficSources }: SubTabProps & { trafficSources: RequestState<TrafficSourceRow[]> }) {
  const topVideosBySource = useTopVideosBySource(scope, filters)
  return (
    <TrafficSourceTopVideosPanel
      rows={trafficSources.data}
      bySource={topVideosBySource.data}
      loading={trafficSources.loading || topVideosBySource.loading}
      error={trafficSources.error ?? topVideosBySource.error}
    />
  )
}

function SearchInsightsSubTab({ scope, filters }: SubTabProps) {
  const data = useSearchInsights(scope, filters)
  return (
    <>
      <div className="search-insights-columns">
        <SearchTermsDonutCard
          title="Top Search Terms"
          rows={data.searchTerms.data}
          loading={data.searchTerms.loading}
          error={data.searchTerms.error}
        />
        <SearchTermsDonutCard
          title="Top Search Terms — Videos"
          rows={data.searchTermsByVideo.data}
          loading={data.searchTermsByVideo.loading}
          error={data.searchTermsByVideo.error}
        />
        <SearchTermsDonutCard
          title="Top Search Terms — Shorts"
          rows={data.searchTermsByShort.data}
          loading={data.searchTermsByShort.loading}
          error={data.searchTermsByShort.error}
        />
      </div>
      <div className="search-insights-videos">
        <SearchTermVideosDonutCard
          title="Top Videos by Search Term"
          terms={data.searchTermsByVideo.data}
          termsLoading={data.searchTermsByVideo.loading}
          selectedTerm={data.videoTerm}
          onSelectTerm={data.setVideoTerm}
          videos={data.videosForVideoTerm.data}
          loading={data.videosForVideoTerm.loading}
          error={data.videosForVideoTerm.error}
        />
        <SearchTermVideosDonutCard
          title="Top Shorts by Search Term"
          terms={data.searchTermsByShort.data}
          termsLoading={data.searchTermsByShort.loading}
          selectedTerm={data.shortTerm}
          onSelectTerm={data.setShortTerm}
          videos={data.videosForShortTerm.data}
          loading={data.videosForShortTerm.loading}
          error={data.videosForShortTerm.error}
        />
      </div>
    </>
  )
}

function RelatedVideosSubTab({ scope, filters }: SubTabProps) {
  const data = useRelatedVideos(scope, filters)
  return (
    <>
      <div className="related-videos-columns">
        <RelatedReferrerBreakdownCard
          title="Related Traffic from My Channel"
          referrers={data.relatedReferrersMine.data.items}
          loading={data.relatedReferrersMine.loading}
          error={data.relatedReferrersMine.error}
        />
        <RelatedReferrerBreakdownCard
          title="Related Traffic from Other Channels"
          referrers={data.relatedReferrersOther.data.items}
          loading={data.relatedReferrersOther.loading}
          error={data.relatedReferrersOther.error}
        />
      </div>
      <div className="related-videos-columns">
        <RelatedDestinationsByReferrerCard
          title="Top Destinations — My Channel"
          referrerOptions={data.relatedReferrersMine.data.items}
          referrerOptionsLoading={data.relatedReferrersMine.loading}
          selectedReferrerId={data.mineReferrerId}
          onSelectReferrer={data.setMineReferrer}
          destinations={data.relatedDestinationsMine.data}
          loading={data.relatedDestinationsMine.loading}
          error={data.relatedDestinationsMine.error}
        />
        <RelatedDestinationsByReferrerCard
          title="Top Destinations — Other Channels"
          referrerOptions={data.relatedReferrersOther.data.items}
          referrerOptionsLoading={data.relatedReferrersOther.loading}
          selectedReferrerId={data.otherReferrerId}
          onSelectReferrer={data.setOtherReferrer}
          destinations={data.relatedDestinationsOther.data}
          loading={data.relatedDestinationsOther.loading}
          error={data.relatedDestinationsOther.error}
        />
      </div>
    </>
  )
}
