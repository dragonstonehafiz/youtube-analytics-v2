from __future__ import annotations

import re
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from logging_config import get_logger

from .auth import get_credentials

_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)

_logger = get_logger("sync")


def _data_client() -> Any:
    """Return an authenticated YouTube Data API v3 client."""
    return build("youtube", "v3", credentials=get_credentials())


def _log_page(
    resource: str,
    page: int,
    item_count: int,
    next_page_token: str | None,
    owner: str | None = None,
    owner_name: str | None = None,
) -> None:
    """Log one fetched Data API page, escalating an empty-but-tokened page to WARNING.

    `owner` is the id of the entity being paged through where one exists — a playlist
    for the playlist-item loops, absent for the channel-wide playlist listing.
    `owner_name` is its human-readable name, rendered last and `repr`-quoted so a title
    containing spaces or newlines cannot corrupt the fields before it.

    A page that returns no items while still supplying a `nextPageToken` can spin
    pagination indefinitely and exhaust quota, so it is recorded as a problem rather
    than as routine detail. The token is included on every record: it is an opaque
    result-set cursor, not a credential, and comparing it across consecutive pages is
    what distinguishes a repeating token from fresh tokens walking an empty region.
    """
    owner_field = f" owner={owner}" if owner else ""
    token_field = f" next_page_token={next_page_token}" if next_page_token else ""
    name_field = f" owner_name={owner_name!r}" if owner_name else ""
    if item_count == 0 and next_page_token:
        _logger.warning(
            "%s page=%d items=0 empty_page_with_token=true%s%s%s",
            resource, page, owner_field, token_field, name_field,
        )
        return
    _logger.debug(
        "%s page=%d items=%d%s%s%s", resource, page, item_count, owner_field, token_field, name_field
    )


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
    page = 0

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
        page += 1
        items = response.get("items", [])
        for item in items:
            vid = item["contentDetails"].get("videoId")
            if vid:
                video_ids.add(vid)
        page_token = response.get("nextPageToken")
        _log_page(
            "shorts_video_ids", page, len(items), page_token,
            owner=shorts_playlist_id, owner_name="Shorts",
        )
        if not page_token:
            break

    return video_ids


def fetch_all_video_ids(uploads_playlist_id: str) -> list[str]:
    """Return all video IDs from the uploads playlist."""
    yt = _data_client()
    video_ids: list[str] = []
    page_token = None
    page = 0

    while True:
        response = yt.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        page += 1
        items = response.get("items", [])
        for item in items:
            vid = item["contentDetails"].get("videoId")
            if vid:
                video_ids.append(vid)
        page_token = response.get("nextPageToken")
        _log_page(
            "video_ids", page, len(items), page_token,
            owner=uploads_playlist_id, owner_name="Uploads",
        )
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
    page = 0

    while True:
        response = yt.playlists().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        page += 1
        items = response.get("items", [])
        for item in items:
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
        _log_page("playlists", page, len(items), page_token, owner_name="Playlists")
        if not page_token:
            break

    return playlists


def fetch_playlist_items(playlist_id: str, playlist_title: str | None = None) -> list[dict]:
    """Return all items in a playlist.

    `playlist_title` is used only to name the playlist in this function's page log
    records; the playlistItems response carries video titles, not the owning
    playlist's, so the caller supplies it.
    """
    yt = _data_client()
    items: list[dict] = []
    page_token = None
    page = 0

    while True:
        response = yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        page += 1
        page_items = response.get("items", [])
        for item in page_items:
            snippet = item.get("snippet", {})
            items.append({
                "id": item["id"],
                "playlist_id": playlist_id,
                "video_id": snippet.get("resourceId", {}).get("videoId"),
                "position": snippet.get("position"),
            })
        page_token = response.get("nextPageToken")
        _log_page(
            "playlist_items", page, len(page_items), page_token,
            owner=playlist_id, owner_name=playlist_title,
        )
        if not page_token:
            break

    return items
