import { useLocation, useNavigate } from 'react-router-dom'
import SyncStatus from '@/components/SyncStatus'
import './TopNav.css'

const links = [
  { to: '/videos', label: 'Videos', exact: false },
  { to: '/playlists', label: 'Playlists', exact: false },
  { to: '/analytics', label: 'Analytics', exact: false },
]

export default function TopNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const isDetailPage = /^\/analytics\/(videos|playlists)\//.test(location.pathname)
  const showBack = isDetailPage

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
            const isActive = link.exact
              ? location.pathname === link.to
              : location.pathname.startsWith(link.to)
            return (
              <button
                key={link.to}
                type="button"
                className={`topnav-link${isActive ? ' active' : ''}`}
                onClick={() => {
                  if (location.pathname === link.to) return
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
