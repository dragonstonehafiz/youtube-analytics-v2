import type { TopVideoSortBy } from '@/types'
import type { CollectionAnalytics } from '@/hooks/useCollectionAnalytics'
import VideoStatsBar from '@/components/VideoStatsBar'
import AnalyticsChart from '@/components/AnalyticsChart'
import TopVideosList from '@/components/TopVideosList'
import TopPerformersCard from '@/components/TopPerformersCard'
import VideoCarouselCard from '@/components/VideoCarouselCard'

interface AnalyticsTabProps {
  data: CollectionAnalytics
  topVideosSortBy: TopVideoSortBy
  onTopVideosSort: (sortBy: TopVideoSortBy) => void
}

/** Analytics tab of the channel and playlist pages: stats, daily chart, Top 10 table, and sidebar cards. */
export default function AnalyticsTab({ data, topVideosSortBy, onTopVideosSort }: AnalyticsTabProps) {
  const { stats, rows, publishedVideos, topVideos, topPerformingVideos, topPerformingShorts, recentVideos, recentShorts } = data
  return (
    <>
      <VideoStatsBar stats={stats.data} loading={stats.loading} error={stats.error} />
      <AnalyticsChart
        rows={rows.data}
        uploadedVideos={publishedVideos.data}
        loading={rows.loading || publishedVideos.loading}
        error={rows.error ?? publishedVideos.error}
      />
      <div className="analytics-layout">
        <div className="analytics-main">
          <TopVideosList
            videos={topVideos.data}
            sortBy={topVideosSortBy}
            onSort={onTopVideosSort}
            loading={topVideos.loading}
            error={topVideos.error}
          />
        </div>
        <div className="analytics-sidebar">
          <TopPerformersCard
            title="Top Videos (Last 7 Days)"
            videos={topPerformingVideos.data}
            loading={topPerformingVideos.loading}
            error={topPerformingVideos.error}
          />
          <TopPerformersCard
            title="Top Shorts (Last 7 Days)"
            videos={topPerformingShorts.data}
            loading={topPerformingShorts.loading}
            error={topPerformingShorts.error}
          />
          <VideoCarouselCard
            title="Latest Videos"
            videos={recentVideos.data}
            loading={recentVideos.loading}
            error={recentVideos.error}
          />
          <VideoCarouselCard
            title="Latest Shorts"
            videos={recentShorts.data}
            loading={recentShorts.loading}
            error={recentShorts.error}
          />
        </div>
      </div>
    </>
  )
}
