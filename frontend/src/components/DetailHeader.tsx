import { Fragment } from 'react'
import type { ReactNode } from 'react'
import AsyncCard from '@/components/AsyncCard'
import '@/components/VideoMetaCard.css'

export interface DetailStat {
  label: string
  value: string
}

export interface DetailHeaderContent {
  thumbnailUrl: string | null
  title: string
  stats: DetailStat[]
}

interface DetailHeaderProps {
  loading: boolean
  error: string | null
  emptyMessage: string
  /** `null` once loaded means the item does not exist. */
  content: DetailHeaderContent | null
  /** Rendered beside the title. */
  badge?: ReactNode
  /** Rendered below the stats row. */
  children?: ReactNode
}

/** Header card of a video or playlist page: thumbnail, title, and a divided stats row. */
export default function DetailHeader({ loading, error, emptyMessage, content, badge, children }: DetailHeaderProps) {
  return (
    <AsyncCard
      loading={loading}
      error={error}
      empty={!content}
      emptyMessage={emptyMessage}
      className="video-meta-card"
      bodyClassName="video-meta-card-body"
    >
      {content && (
        <>
          <div className="video-meta-thumb-wrap">
            {content.thumbnailUrl
              ? <img src={content.thumbnailUrl} alt="" className="video-meta-thumb" />
              : <div className="video-meta-thumb video-meta-thumb-placeholder" />}
          </div>
          <div className="video-meta-info">
            <div className="video-meta-title-row">
              <h1 className="video-meta-title">{content.title}</h1>
              {badge}
            </div>
            <div className="video-meta-stats">
              {content.stats.map((stat, i) => (
                <Fragment key={stat.label}>
                  {i > 0 && <div className="video-meta-stat-divider" />}
                  <div className="video-meta-stat">
                    <span className="video-meta-stat-value">{stat.value}</span>
                    <span className="video-meta-stat-label">{stat.label}</span>
                  </div>
                </Fragment>
              ))}
            </div>
            {children}
          </div>
        </>
      )}
    </AsyncCard>
  )
}
