CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    published_at TEXT,
    duration_seconds INTEGER,
    thumbnail_url TEXT,
    content_type TEXT,
    privacy_status TEXT,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_analytics (
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    views INTEGER,
    watch_time_minutes REAL,
    estimated_revenue REAL,
    average_view_duration_seconds REAL,
    average_view_percentage REAL,
    likes INTEGER,
    subscribers_gained INTEGER,
    subscribers_lost INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (video_id, date)
);

CREATE INDEX IF NOT EXISTS idx_video_analytics_date ON video_analytics(date);
CREATE INDEX IF NOT EXISTS idx_video_analytics_video ON video_analytics(video_id);

CREATE TABLE IF NOT EXISTS video_traffic_sources (
    video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    traffic_source_type TEXT NOT NULL,
    views INTEGER,
    watch_time_minutes REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (video_id, date, traffic_source_type)
);

CREATE INDEX IF NOT EXISTS idx_video_traffic_sources_date ON video_traffic_sources(date);
CREATE INDEX IF NOT EXISTS idx_video_traffic_sources_video ON video_traffic_sources(video_id);

CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    published_at TEXT,
    thumbnail_url TEXT,
    item_count INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playlist_items (
    id TEXT PRIMARY KEY,
    playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    video_id TEXT,
    position INTEGER,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist ON playlist_items(playlist_id);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS fx_rates (
    date TEXT PRIMARY KEY,
    usd_to_sgd REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    sync_type TEXT NOT NULL,
    scope TEXT,
    year INTEGER,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    rows_fetched INTEGER NOT NULL DEFAULT 0,
    rows_written INTEGER NOT NULL DEFAULT 0,
    rows_deleted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_started_at ON sync_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_sync_runs_type_started ON sync_runs(sync_type, started_at);
