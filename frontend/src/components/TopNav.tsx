import { useLocation, useNavigate } from 'react-router-dom'
import SyncStatus from '@/components/SyncStatus'
import './TopNav.css'

/** Comments is a tab on the Analytics pages rather than a route of its own. */
const COMMENTS_TO = '/analytics?tab=comments'

const links = [
  { to: '/videos', label: 'Videos', exact: false },
  { to: '/playlists', label: 'Playlists', exact: false },
  { to: '/analytics', label: 'Analytics', exact: false },
  { to: COMMENTS_TO, label: 'Comments', exact: false },
  { to: '/sync', label: 'Sync', exact: false },
]

export default function TopNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const isDetailPage = /^\/analytics\/(videos|playlists)\//.test(location.pathname)
  const showBack = isDetailPage

  /**
   * Analytics and Comments share the /analytics pathname, so which of the two is active
   * comes from the tab parameter; matching on the path alone would light up both.
   */
  const onAnalyticsPath = location.pathname.startsWith('/analytics')
  const onCommentsTab = new URLSearchParams(location.search).get('tab') === 'comments'

  const isLinkActive = (to: string, exact: boolean): boolean => {
    if (to === COMMENTS_TO) return onAnalyticsPath && onCommentsTab
    if (to === '/analytics') return onAnalyticsPath && !onCommentsTab
    return exact ? location.pathname === to : location.pathname.startsWith(to)
  }

  return (
    <nav className="topnav">
      <div className="topnav-inner">
        {showBack && (
          <button type="button" className="topnav-back" onClick={() => navigate(-1)} aria-label="Go back">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 5l-7 7 7 7"/>
            </svg>
          </button>
        )}
        <button
          type="button"
          className="topnav-brand"
          onClick={() => {
            if (location.pathname === '/') return
            navigate('/')
          }}
        >
          YouTube Analytics
        </button>
        <div className="topnav-links">
          {links.map(link => {
            const isActive = isLinkActive(link.to, link.exact)
            return (
              <button
                key={link.to}
                type="button"
                className={`topnav-link${isActive ? ' active' : ''}`}
                onClick={() => {
                  if (isActive) return
                  navigate(link.to)
                }}
              >
                {link.label}
              </button>
            )
          })}
        </div>
        <div className="topnav-sync">
          <SyncStatus />
        </div>
      </div>
    </nav>
  )
}
