import { BrowserRouter, Routes, Route } from 'react-router-dom'
import TopNav from '@/components/TopNav'
import Home from '@/pages/Home'
import Videos from '@/pages/Videos'
import Playlists from '@/pages/Playlists'
import Analytics from '@/pages/Analytics'
import VideoAnalytics from '@/pages/VideoAnalytics'
import PlaylistAnalytics from '@/pages/PlaylistAnalytics'

export default function App() {
  return (
    <BrowserRouter>
      <TopNav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/videos" element={<Videos />} />
        <Route path="/playlists" element={<Playlists />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/analytics/videos/:id" element={<VideoAnalytics />} />
        <Route path="/analytics/playlists/:id" element={<PlaylistAnalytics />} />
      </Routes>
    </BrowserRouter>
  )
}
