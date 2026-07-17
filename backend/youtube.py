from __future__ import annotations

import calendar
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_SECRETS_DIR = Path(__file__).parent / "secrets"
_TOKEN_PATH = _SECRETS_DIR / "token.json"
_CLIENT_SECRET_PATH = _SECRETS_DIR / "client_secret.json"

_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]

_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)

_VIDEO_DAILY_METRICS = [
    "views",
    "estimatedMinutesWatched",
    "estimatedRevenue",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "subscribersGained",
    "subscribersLost",
]

_TRAFFIC_SOURCE_METRICS = [
    "views",
    "estimatedMinutesWatched",
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_credentials() -> Credentials:
    """Return OAuth credentials, refreshing or running the auth flow as needed."""
    creds: Credentials | None = None
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

    if not creds or not creds.valid or not creds.has_scopes(_SCOPES):
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                _TOKEN_PATH.unlink(missing_ok=True)
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(_CLIENT_SECRET_PATH), _SCOPES)
            creds = flow.run_local_server(port=0, access_type="offline", include_granted_scopes="true", prompt="consent")

        _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------

def _data_client():
    """Return an authenticated YouTube Data API v3 client."""
    return build("youtube", "v3", credentials=get_credentials())


def _analytics_client():
    """Return an authenticated YouTube Analytics API v2 client."""
    return build("youtubeAnalytics", "v2", credentials=get_credentials())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_duration(value: str | None) -> int | None:
    """Convert ISO 8601 duration string to total seconds."""
    if not value:
        return None
    match = _DURATION_RE.match(value)
    if not match:
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return hours * 3600 + minutes * 60 + seconds


def _analytics_query(service, params: dict, max_attempts: int = 5) -> dict:
    """Execute a YouTube Analytics reports.query with exponential-backoff retry."""
    for attempt in range(1, max_attempts + 1):
        try:
            return service.reports().query(**params).execute()
        except HttpError as exc:
            status_code = int(exc.resp.status)
            error_text = exc.content.decode("utf-8") if exc.content else str(exc)
            is_quota = any(t in error_text for t in ("rateLimitExceeded", "quotaExceeded"))
            should_retry = status_code >= 500 or (status_code in {403, 429} and is_quota)
            if should_retry and attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 30))
                continue
            raise RuntimeError(f"YouTube Analytics API error: {exc}") from exc
    return {}


def _chunk_date_range(start: str, end: str, months: int = 4) -> list[tuple[str, str]]:
    """Split a date range into chunks of N months."""
    chunks: list[tuple[str, str]] = []
    current = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    while current <= end_date:
        month = current.month - 1 + months
        year = current.year + month // 12
        month = month % 12 + 1
        last_day = calendar.monthrange(year, month)[1]
        chunk_end = min(date(year, month, last_day) - timedelta(days=1), end_date)
        chunks.append((current.isoformat(), chunk_end.isoformat()))
        current = chunk_end + timedelta(days=1)
    return chunks


def _fetch_analytics_rows(service, params: dict) -> list[dict[str, Any]]:
    """Fetch all paginated rows from an Analytics reports.query call."""
    results: list[dict[str, Any]] = []
    headers: list[str] | None = None
    max_results = params.get("maxResults", 200)

    while True:
        response = _analytics_query(service, params)
        rows = response.get("rows") or []
        if headers is None:
            headers = [h["name"] for h in response.get("columnHeaders", [])]
        for row in rows:
            results.append({headers[i]: row[i] for i in range(len(headers))})
        if not rows:
            break
        params = {**params, "startIndex": params.get("startIndex", 1) + max_results}
        time.sleep(0.2)

    return results


# ---------------------------------------------------------------------------
# Data API fetches
# ---------------------------------------------------------------------------

def fetch_uploads_playlist_id() -> str:
    """Return the uploads playlist ID for the authenticated channel."""
    yt = _data_client()
    response = yt.channels().list(part="contentDetails", mine=True, maxResults=1).execute()
    items = response.get("items", [])
    if not items:
        raise RuntimeError("No channel found for the authenticated user.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_shorts_video_ids(uploads_playlist_id: str) -> set[str]:
    """Return the set of video IDs that are Shorts via the UUSH playlist.

    Raises RuntimeError if the UUSH playlist is unavailable.
    """
    if not uploads_playlist_id.startswith("UU"):
        raise RuntimeError("Uploads playlist ID does not start with 'UU' — cannot derive Shorts playlist.")
    shorts_playlist_id = f"UUSH{uploads_playlist_id[2:]}"
    yt = _data_client()
    video_ids: set[str] = set()
    page_token = None

    while True:
        try:
            response = yt.playlistItems().list(
                part="contentDetails",
                playlistId=shorts_playlist_id,
                maxResults=50,
                pageToken=page_token,
            ).execute()
        except HttpError as exc:
            if int(exc.resp.status) == 404:
                raise RuntimeError(f"Shorts playlist {shorts_playlist_id} not found.") from exc
            raise
        for item in response.get("items", []):
            vid = item["contentDetails"].get("videoId")
            if vid:
                video_ids.add(vid)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def fetch_all_video_ids(uploads_playlist_id: str) -> list[str]:
    """Return all video IDs from the uploads playlist."""
    yt = _data_client()
    video_ids: list[str] = []
    page_token = None

    while True:
        response = yt.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            vid = item["contentDetails"].get("videoId")
            if vid:
                video_ids.append(vid)
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def fetch_videos(video_ids: list[str]) -> list[dict]:
    """Fetch video details for up to 50 IDs and return normalized dicts."""
    if not video_ids:
        return []
    yt = _data_client()
    response = yt.videos().list(
        part="snippet,contentDetails,statistics,status",
        id=",".join(video_ids),
        maxResults=50,
    ).execute()

    results: list[dict] = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            thumbnails.get("maxres") or
            thumbnails.get("high") or
            thumbnails.get("medium") or
            thumbnails.get("default") or {}
        ).get("url")

        results.append({
            "id": item["id"],
            "title": snippet.get("title", ""),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "duration_seconds": _parse_duration(item.get("contentDetails", {}).get("duration")),
            "thumbnail_url": thumbnail_url,
            "content_type": None,  # set by caller after Shorts detection
            "privacy_status": item.get("status", {}).get("privacyStatus"),
            "view_count": int(stats.get("viewCount") or 0),
            "like_count": int(stats.get("likeCount") or 0),
            "comment_count": int(stats.get("commentCount") or 0),
        })

    return results


def fetch_playlists() -> list[dict]:
    """Return all playlists for the authenticated channel."""
    yt = _data_client()
    playlists: list[dict] = []
    page_token = None

    while True:
        response = yt.playlists().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("maxres") or
                thumbnails.get("high") or
                thumbnails.get("medium") or
                thumbnails.get("default") or {}
            ).get("url")
            playlists.append({
                "id": item["id"],
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail_url": thumbnail_url,
                "item_count": item.get("contentDetails", {}).get("itemCount"),
            })
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return playlists


def fetch_playlist_items(playlist_id: str) -> list[dict]:
    """Return all items in a playlist."""
    yt = _data_client()
    items: list[dict] = []
    page_token = None

    while True:
        response = yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            items.append({
                "id": item["id"],
                "playlist_id": playlist_id,
                "video_id": snippet.get("resourceId", {}).get("videoId"),
                "position": snippet.get("position"),
            })
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return items


# ---------------------------------------------------------------------------
# Analytics API fetches
# ---------------------------------------------------------------------------

def iter_video_analytics(
    video_id: str,
    start_date: str,
    end_date: str,
    publish_date: str | None = None,
):
    """Yield daily analytics rows for a single video, one year-chunk at a time.

    Clamps start_date to publish_date if provided, skips entirely if the video
    hasn't been published yet within the requested range. maxResults is set high
    enough that a full year (365 rows) always fits in a single page - the API has
    no documented upper bound on maxResults, so this avoids pagination entirely
    in the common case (confirmed by a live full-year test returning all 365 days
    in one call with no gaps).
    """
    effective_start = start_date
    if publish_date:
        if publish_date > end_date:
            return
        if publish_date > start_date:
            effective_start = publish_date

    service = _analytics_client()

    for chunk_start, chunk_end in _chunk_date_range(effective_start, end_date, months=12):
        params = {
            "ids": "channel==MINE",
            "startDate": chunk_start,
            "endDate": chunk_end,
            "metrics": ",".join(_VIDEO_DAILY_METRICS),
            "dimensions": "day",
            "filters": f"video=={video_id}",
            "sort": "day",
            "maxResults": 2000,
            "startIndex": 1,
        }
        for row in _fetch_analytics_rows(service, params):
            yield {
                "video_id": video_id,
                "date": row.get("day"),
                "views": row.get("views"),
                "watch_time_minutes": row.get("estimatedMinutesWatched"),
                "estimated_revenue": row.get("estimatedRevenue"),
                "average_view_duration_seconds": row.get("averageViewDuration"),
                "average_view_percentage": row.get("averageViewPercentage"),
                "likes": row.get("likes"),
                "subscribers_gained": row.get("subscribersGained"),
                "subscribers_lost": row.get("subscribersLost"),
            }


def iter_video_traffic_sources(
    video_id: str,
    start_date: str,
    end_date: str,
    publish_date: str | None = None,
):
    """Yield daily traffic-source breakdown rows for a single video, one year-chunk at a time.

    Queries dimensions=day,insightTrafficSourceType per 1-year window so each API
    call returns one row per (day, traffic source type) pair. Clamps start_date to
    publish_date if provided. maxResults is set well above the theoretical ceiling
    of 365 days x 21 traffic source types (7665 rows) so a full year always fits in
    a single page - confirmed by a live full-year test (2883 rows, 365/365 days
    covered, no gaps) returned in one call with no pagination needed.
    """
    effective_start = start_date
    if publish_date:
        if publish_date > end_date:
            return
        if publish_date > start_date:
            effective_start = publish_date

    service = _analytics_client()

    for chunk_start, chunk_end in _chunk_date_range(effective_start, end_date, months=12):
        params = {
            "ids": "channel==MINE",
            "startDate": chunk_start,
            "endDate": chunk_end,
            "metrics": ",".join(_TRAFFIC_SOURCE_METRICS),
            "dimensions": "day,insightTrafficSourceType",
            "filters": f"video=={video_id}",
            "sort": "day,insightTrafficSourceType",
            "maxResults": 10000,
            "startIndex": 1,
        }
        for row in _fetch_analytics_rows(service, params):
            yield {
                "video_id": video_id,
                "date": row.get("day"),
                "traffic_source_type": row.get("insightTrafficSourceType"),
                "views": row.get("views"),
                "watch_time_minutes": row.get("estimatedMinutesWatched"),
            }
