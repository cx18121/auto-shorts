"""
analysis/fetcher.py — Fetch all Shorts from a YouTube channel via Data API v3.

Public API:
    fetch_channel(url_or_id) -> str   (returns channel_id)
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from analysis.db import get_connection, init_db

logger = logging.getLogger(__name__)

_MAX_DURATION_SECONDS = 61   # Shorts are ≤60 s; tiny buffer for rounding
_MAX_VIDEOS = 50             # Cap playlist fetch to avoid IP bans on transcript step


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_channel(url_or_id: str, max_videos: int = _MAX_VIDEOS) -> str:
    """Fetch Shorts for a channel and persist them to SQLite.

    Args:
        url_or_id: Channel URL (any format) or raw channel ID / @handle.
        max_videos: Maximum number of videos to fetch from the playlist.

    Returns:
        The resolved channel_id string.
    """
    init_db()
    yt = build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY)

    logger.info("Resolving channel: %s", url_or_id)
    channel_id, channel_name, subscriber_count = _resolve_channel(yt, url_or_id)
    logger.info("Resolved → id=%s  name=%s  subs=%s", channel_id, channel_name, subscriber_count)

    _upsert_channel(channel_id, url_or_id, channel_name, subscriber_count)

    uploads_playlist = _get_uploads_playlist(yt, channel_id)
    logger.info("Uploads playlist: %s", uploads_playlist)

    video_ids = _paginate_playlist(yt, uploads_playlist, channel_name, max_videos=max_videos)
    logger.info("Fetched %d total video IDs from playlist", len(video_ids))

    shorts = _fetch_video_details(yt, video_ids, channel_id, channel_name)
    logger.info("Kept %d Shorts (≤%ds) out of %d total", len(shorts), _MAX_DURATION_SECONDS, len(video_ids))

    _upsert_videos(shorts)
    logger.info("Saved %d Shorts to database for channel %s", len(shorts), channel_name)
    return channel_id


# ---------------------------------------------------------------------------
# Channel resolution
# ---------------------------------------------------------------------------

def _resolve_channel(yt: Any, url_or_id: str) -> tuple[str, str, int]:
    """Return (channel_id, display_name, subscriber_count)."""
    handle = _extract_handle(url_or_id)
    channel_id_direct = _extract_channel_id(url_or_id)

    if channel_id_direct:
        return _fetch_channel_by_id(yt, channel_id_direct)
    if handle:
        return _fetch_channel_by_handle(yt, handle)
    # Fall back to search
    return _fetch_channel_by_search(yt, url_or_id)


def _extract_handle(text: str) -> str | None:
    """Extract @handle from a URL or bare @handle string."""
    m = re.search(r'@([\w.-]+)', text)
    return f"@{m.group(1)}" if m else None


def _extract_channel_id(text: str) -> str | None:
    """Extract a UC... channel ID from a URL or bare ID string."""
    m = re.search(r'(?:channel/)?(UC[\w-]{22})', text)
    return m.group(1) if m else None


def _fetch_channel_by_id(yt: Any, channel_id: str) -> tuple[str, str, int]:
    resp = _api_call(lambda: yt.channels().list(
        part="snippet,statistics",
        id=channel_id,
    ).execute())
    item = resp["items"][0]
    return (
        item["id"],
        item["snippet"]["title"],
        int(item["statistics"].get("subscriberCount", 0)),
    )


def _fetch_channel_by_handle(yt: Any, handle: str) -> tuple[str, str, int]:
    resp = _api_call(lambda: yt.channels().list(
        part="snippet,statistics",
        forHandle=handle,
    ).execute())
    if not resp.get("items"):
        raise ValueError(f"No channel found for handle: {handle}")
    item = resp["items"][0]
    return (
        item["id"],
        item["snippet"]["title"],
        int(item["statistics"].get("subscriberCount", 0)),
    )


def _fetch_channel_by_search(yt: Any, query: str) -> tuple[str, str, int]:
    resp = _api_call(lambda: yt.search().list(
        part="snippet",
        q=query,
        type="channel",
        maxResults=1,
    ).execute())
    if not resp.get("items"):
        raise ValueError(f"No channel found for query: {query}")
    channel_id = resp["items"][0]["snippet"]["channelId"]
    return _fetch_channel_by_id(yt, channel_id)


# ---------------------------------------------------------------------------
# Playlist pagination
# ---------------------------------------------------------------------------

def _get_uploads_playlist(yt: Any, channel_id: str) -> str:
    resp = _api_call(lambda: yt.channels().list(
        part="contentDetails",
        id=channel_id,
    ).execute())
    return resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _paginate_playlist(yt: Any, playlist_id: str, channel_name: str,
                       max_videos: int = _MAX_VIDEOS) -> list[str]:
    """Return video IDs from the playlist, capped at max_videos (most recent first)."""
    video_ids: list[str] = []
    page_token: str | None = None

    while True:
        kwargs: dict[str, Any] = dict(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
        )
        if page_token:
            kwargs["pageToken"] = page_token

        resp = _api_call(lambda: yt.playlistItems().list(**kwargs).execute())

        for item in resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        page_token = resp.get("nextPageToken")
        total = resp.get("pageInfo", {}).get("totalResults", "?")
        logger.info("Fetched %d/%s videos from @%s (cap: %d)...",
                    len(video_ids), total, channel_name, max_videos)

        if not page_token or len(video_ids) >= max_videos:
            break

    video_ids = video_ids[:max_videos]
    return video_ids


# ---------------------------------------------------------------------------
# Video detail fetching
# ---------------------------------------------------------------------------

def _fetch_video_details(
    yt: Any, video_ids: list[str], channel_id: str, channel_name: str
) -> list[dict[str, Any]]:
    """Batch-fetch full video metadata; return only Shorts (≤61s)."""
    shorts: list[dict[str, Any]] = []

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = _api_call(lambda: yt.videos().list(
            part="snippet,contentDetails,statistics",
            id=",".join(batch),
        ).execute())

        for item in resp.get("items", []):
            duration = _parse_duration(item["contentDetails"]["duration"])
            if duration > _MAX_DURATION_SECONDS:
                continue

            snippet = item["snippet"]
            stats   = item.get("statistics", {})

            # Caption type: closedCaption vs none (manual vs auto is not exposed via basic API)
            caption_type = "closedCaption" if item["contentDetails"].get("caption") == "true" else "none"

            shorts.append({
                "id":                     item["id"],
                "channel_id":             channel_id,
                "title":                  snippet.get("title", ""),
                "description":            snippet.get("description", ""),
                "view_count":             int(stats.get("viewCount", 0)),
                "like_count":             int(stats.get("likeCount", 0)),
                "comment_count":          int(stats.get("commentCount", 0)),
                "duration_seconds":       duration,
                "published_at":           snippet.get("publishedAt", ""),
                "tags":                   json.dumps(snippet.get("tags", [])),
                "thumbnail_url":          (snippet.get("thumbnails", {}).get("maxres")
                                           or snippet.get("thumbnails", {}).get("high", {})).get("url", ""),
                "category_id":            snippet.get("categoryId", ""),
                "default_audio_language": snippet.get("defaultAudioLanguage", ""),
                "caption_type":           caption_type,
            })

    return shorts


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _upsert_channel(channel_id: str, url: str, name: str, subscriber_count: int) -> None:
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO channels (id, url, name, subscriber_count, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                subscriber_count=excluded.subscriber_count,
                fetched_at=excluded.fetched_at
        """, (channel_id, url, name, subscriber_count,
              datetime.now(timezone.utc).isoformat()))


def _upsert_videos(videos: list[dict[str, Any]]) -> None:
    if not videos:
        return
    with get_connection() as conn:
        conn.executemany("""
            INSERT INTO videos (
                id, channel_id, title, description, view_count, like_count,
                comment_count, duration_seconds, published_at, tags,
                thumbnail_url, category_id, default_audio_language, caption_type
            ) VALUES (
                :id, :channel_id, :title, :description, :view_count, :like_count,
                :comment_count, :duration_seconds, :published_at, :tags,
                :thumbnail_url, :category_id, :default_audio_language, :caption_type
            )
            ON CONFLICT(id) DO UPDATE SET
                view_count=excluded.view_count,
                like_count=excluded.like_count,
                comment_count=excluded.comment_count
        """, videos)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_duration(iso: str) -> int:
    """Parse ISO 8601 duration string (e.g. PT1M30S) → total seconds."""
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not m:
        return 0
    h, mins, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mins * 60 + s


def _api_call(fn: Any, max_attempts: int = 3) -> Any:
    """Call a YouTube API lambda with exponential backoff."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except HttpError as e:
            if e.resp.status in (403, 429):
                wait = 2 ** attempt
                logger.warning("YouTube API rate limit (attempt %d), retrying in %ds", attempt, wait)
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            if attempt == max_attempts:
                raise
            wait = 2 ** attempt
            logger.warning("API call failed (attempt %d): %s, retrying in %ds", attempt, e, wait)
            time.sleep(wait)
    raise RuntimeError("YouTube API call failed after retries")
