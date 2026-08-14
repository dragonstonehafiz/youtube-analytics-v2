from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from logging_config import get_logger

from .auth import get_credentials

_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)

# The maximum commentThreads.list page size. Each request costs one quota unit whatever
# the page size, so always asking for the maximum minimises quota spent per comment.
COMMENT_THREADS_PAGE_SIZE = 100

# Namespaces for comment_authors.id. Every author key carries exactly one of these, so a
# key derived from a channel ID and one derived from a comment ID can never collide. The
# unprefixed channel ID is stored separately in comment_authors.youtube_channel_id.
AUTHOR_CHANNEL_KEY_PREFIX = "channel:"
AUTHOR_COMMENT_KEY_PREFIX = "comment:"

# Per-video commentThreads failures meaning "this video has no readable comments" rather
# than "the request was wrong". Anything else — notably quotaExceeded, which also arrives
# as a 403 — must propagate and fail the stage instead of silently skipping every
# remaining video.
_RECOVERABLE_COMMENT_REASONS = frozenset({"commentsDisabled", "videoNotFound"})

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
    anomaly: str | None = None,
) -> None:
    """Log one fetched Data API page, escalating an anomalous terminal page to WARNING.

    `owner` is the id of the entity being paged through where one exists — a playlist
    for the playlist-item loops, absent for the channel-wide playlist listing.
    `owner_name` is its human-readable name, rendered last and `repr`-quoted so a title
    containing spaces or newlines cannot corrupt the fields before it.

    `anomaly` names the condition that ended pagination early (`empty_page_with_token`
    or `repeated_page_token`); both can spin pagination indefinitely and exhaust quota,
    so they are recorded as problems rather than as routine detail. The token is
    included on every record: it is an opaque result-set cursor, not a credential, and
    comparing it across consecutive pages is what distinguishes a repeating token from
    fresh tokens walking an empty region.
    """
    owner_field = f" owner={owner}" if owner else ""
    token_field = f" next_page_token={next_page_token}" if next_page_token else ""
    name_field = f" owner_name={owner_name!r}" if owner_name else ""
    if anomaly:
        _logger.warning(
            "%s page=%d items=%d %s=true%s%s%s",
            resource, page, item_count, anomaly, owner_field, token_field, name_field,
        )
        return
    _logger.debug(
        "%s page=%d items=%d%s%s%s", resource, page, item_count, owner_field, token_field, name_field
    )


def _next_page_token(
    resource: str,
    page: int,
    item_count: int,
    next_page_token: str | None,
    seen_tokens: set[str],
    owner: str | None = None,
    owner_name: str | None = None,
) -> tuple[str | None, bool]:
    """Decide whether to request another page, logging the page as a side effect.

    Returns `(token_to_follow, truncated)`. `token_to_follow` is `None` whenever
    pagination must stop. `truncated` is True only when it stopped on an anomaly, which
    means the collected rows are an incomplete view of the resource and must not be
    treated as authoritative for absence — see `sync/stages.py`, where it suppresses the
    reconciling deletes.

    Pagination stops without truncation when the response carries no token. It stops
    *with* truncation when the page is empty but still carries a token, or when the
    token has already been followed during this call — either of which would otherwise
    re-request pages until the Data API quota is gone.

    `seen_tokens` is this invocation's cursor history and is mutated here. Callers must
    create it per call so that two playlists paginated in sequence never share history.
    """
    if item_count == 0:
        anomaly = "empty_page_with_token" if next_page_token else None
        _log_page(resource, page, item_count, next_page_token, owner, owner_name, anomaly)
        return None, bool(next_page_token)

    if next_page_token and next_page_token in seen_tokens:
        _log_page(
            resource, page, item_count, next_page_token, owner, owner_name, "repeated_page_token"
        )
        return None, True

    _log_page(resource, page, item_count, next_page_token, owner, owner_name)
    if not next_page_token:
        return None, False
    seen_tokens.add(next_page_token)
    return next_page_token, False


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


def fetch_channel_identity() -> tuple[str, str]:
    """Return (channel_id, uploads_playlist_id) for the authenticated channel.

    Both come from the same `channels.list(mine=true)` response so the ownership check
    in `sync_videos()` compares against the same identity the uploads playlist belongs
    to, rather than one inferred from the playlist ID.
    """
    yt = _data_client()
    response = yt.channels().list(part="contentDetails", mine=True, maxResults=1).execute()
    items = response.get("items", [])
    if not items:
        raise RuntimeError("No channel found for the authenticated user.")
    channel = items[0]
    return channel["id"], channel["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_shorts_video_ids(uploads_playlist_id: str) -> tuple[set[str], bool]:
    """Return the set of video IDs that are Shorts via the UUSH playlist, and whether
    pagination ended early on an anomaly.

    Raises RuntimeError if the UUSH playlist is unavailable.
    """
    if not uploads_playlist_id.startswith("UU"):
        raise RuntimeError("Uploads playlist ID does not start with 'UU' — cannot derive Shorts playlist.")
    shorts_playlist_id = f"UUSH{uploads_playlist_id[2:]}"
    yt = _data_client()
    video_ids: set[str] = set()
    seen_tokens: set[str] = set()
    page_token = None
    page = 0
    truncated = False

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
        page_token, truncated = _next_page_token(
            "shorts_video_ids", page, len(items), response.get("nextPageToken"), seen_tokens,
            owner=shorts_playlist_id, owner_name="Shorts",
        )
        if not page_token:
            break

    return video_ids, truncated


def fetch_all_video_ids(uploads_playlist_id: str) -> tuple[list[str], bool]:
    """Return all video IDs from the uploads playlist, and whether pagination ended
    early on an anomaly.

    The uploads playlist is how the Data API enumerates a channel's videos, so a
    truncated result here is a partial view of the channel — never a complete one that
    happens to be short. `sync_videos()` reconciles deletions against this list and must
    skip that step when the flag is set.
    """
    yt = _data_client()
    video_ids: list[str] = []
    seen_tokens: set[str] = set()
    page_token = None
    page = 0
    truncated = False

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
        page_token, truncated = _next_page_token(
            "video_ids", page, len(items), response.get("nextPageToken"), seen_tokens,
            owner=uploads_playlist_id, owner_name="Uploads",
        )
        if not page_token:
            break

    return video_ids, truncated


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
            "channel_id": snippet.get("channelId"),
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


def fetch_playlists() -> tuple[list[dict], bool]:
    """Return all playlists for the authenticated channel, and whether pagination ended
    early on an anomaly."""
    yt = _data_client()
    playlists: list[dict] = []
    seen_tokens: set[str] = set()
    page_token = None
    page = 0
    truncated = False

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
        page_token, truncated = _next_page_token(
            "playlists", page, len(items), response.get("nextPageToken"), seen_tokens,
            owner_name="Playlists",
        )
        if not page_token:
            break

    return playlists, truncated


def fetch_playlist_items(
    playlist_id: str, playlist_title: str | None = None
) -> tuple[list[dict], bool]:
    """Return all items in a playlist, and whether pagination ended early on an anomaly.

    `playlist_title` is used only to name the playlist in this function's page log
    records; the playlistItems response carries video titles, not the owning
    playlist's, so the caller supplies it.

    The cursor history is created here, per call, so paginating one playlist can never
    make another playlist's identical token look like a repeat.
    """
    yt = _data_client()
    items: list[dict] = []
    seen_tokens: set[str] = set()
    page_token = None
    page = 0
    truncated = False

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
        page_token, truncated = _next_page_token(
            "playlist_items", page, len(page_items), response.get("nextPageToken"), seen_tokens,
            owner=playlist_id, owner_name=playlist_title,
        )
        if not page_token:
            break

    return items, truncated


def _http_error_reason(exc: HttpError) -> str | None:
    """Return the Data API's machine-readable reason for an HttpError, when it carries one.

    The HTTP status alone can't separate a video with comments turned off from an
    exhausted quota — both are 403 — so this reason string is what decides whether one
    video is skipped or the whole stage fails.
    """
    try:
        payload = json.loads(exc.content.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return None
    errors = payload.get("error", {}).get("errors") or []
    if not errors:
        return None
    reason = errors[0].get("reason")
    return str(reason) if reason else None


def _normalize_comment_thread(item: dict, video_id: str) -> dict | None:
    """Split one commentThreads item into its author and top-level comment rows.

    Returns None when the item lacks a field the schema requires, which the caller logs
    and skips. `authorChannelId` is genuinely optional — a commenter whose channel no
    longer resolves keeps a display name but loses that identifier — so those authors get
    a comment-scoped key, which keeps two such commenters apart rather than merging them
    on a shared display name.
    """
    thread_snippet = item.get("snippet") or {}
    top_level = thread_snippet.get("topLevelComment") or {}
    snippet = top_level.get("snippet") or {}

    thread_id = item.get("id")
    comment_id = top_level.get("id")
    text = snippet.get("textDisplay")
    display_name = snippet.get("authorDisplayName")
    published_at = snippet.get("publishedAt")
    if not (thread_id and comment_id and display_name and published_at) or text is None:
        return None

    channel_id = (snippet.get("authorChannelId") or {}).get("value")
    author_id = (
        f"{AUTHOR_CHANNEL_KEY_PREFIX}{channel_id}" if channel_id
        else f"{AUTHOR_COMMENT_KEY_PREFIX}{comment_id}"
    )
    return {
        "author": {
            "id": author_id,
            "youtube_channel_id": channel_id,
            "display_name": display_name,
            "profile_image_url": snippet.get("authorProfileImageUrl"),
            "channel_url": snippet.get("authorChannelUrl"),
        },
        "comment": {
            "id": comment_id,
            "thread_id": thread_id,
            "video_id": video_id,
            "author_id": author_id,
            "text": text,
            "like_count": max(int(snippet.get("likeCount") or 0), 0),
            "total_reply_count": max(int(thread_snippet.get("totalReplyCount") or 0), 0),
            "published_at": published_at,
            "youtube_updated_at": snippet.get("updatedAt") or published_at,
        },
    }


def iter_comment_threads(video_id: str, title: str | None = None) -> Iterator[dict]:
    """Yield one video's top-level comments newest first, fetching a page at a time.

    Each yielded item is `{"author": {...}, "comment": {...}}`, shaped for
    `database.upsert_comment_author()` and `database.upsert_comment()` respectively.

    One request carries at most COMMENT_THREADS_PAGE_SIZE comments and the next is only
    made once the consumer has worked through the previous ones, so a caller that stops
    early — as the incremental scan does once it reaches comments it already stores —
    spends no further quota.

    Requesting `part="snippet"` omits the optional `replies` part, so reply bodies are
    never transferred while `snippet.totalReplyCount` still is. `order="time"` is what
    makes stopping early meaningful: the newest comments arrive first.

    A video with comments disabled or one that has disappeared from YouTube yields
    nothing and is logged; every other API error propagates. The truncation signal from
    `_next_page_token()` is only logged, since nothing downstream infers a deletion from
    a comment's absence — an incomplete walk costs freshness, not correctness.
    """
    yt = _data_client()
    seen_tokens: set[str] = set()
    page_token = None
    page = 0

    while True:
        try:
            response = yt.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=COMMENT_THREADS_PAGE_SIZE,
                order="time",
                textFormat="plainText",
                pageToken=page_token,
            ).execute()
        except HttpError as exc:
            reason = _http_error_reason(exc)
            if reason in _RECOVERABLE_COMMENT_REASONS:
                _logger.warning(
                    "comment_threads skipped video=%s reason=%s title=%r", video_id, reason, title
                )
                return
            raise

        page += 1
        items = response.get("items", [])
        for item in items:
            try:
                normalized = _normalize_comment_thread(item, video_id)
            except (AttributeError, TypeError, ValueError):
                normalized = None
            if normalized is None:
                _logger.warning(
                    "comment_threads item skipped video=%s reason=malformed_item thread=%r",
                    video_id, (item or {}).get("id"),
                )
                continue
            yield normalized

        page_token, _truncated = _next_page_token(
            "comment_threads", page, len(items), response.get("nextPageToken"), seen_tokens,
            owner=video_id, owner_name=title,
        )
        if not page_token:
            break
