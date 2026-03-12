"""
analysis/transcripts.py — Fetch and store transcripts for videos in the database.

Public API:
    fetch_transcripts(channel_id) -> int   (returns count of transcripts fetched)
"""

import http.cookiejar
import logging
import time
from pathlib import Path
from typing import Any

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

import config
from analysis.db import get_connection

logger = logging.getLogger(__name__)


_MAX_TRANSCRIPTS = 50  # Never fetch more than this many at once


def fetch_transcripts(channel_id: str, limit: int = _MAX_TRANSCRIPTS) -> int:
    """Fetch transcripts for the most recent videos in the channel without one.

    Args:
        channel_id: The YouTube channel ID already stored in the database.
        limit: Maximum number of transcripts to fetch (default: 50).

    Returns:
        Number of transcripts successfully fetched.
    """
    video_ids = _get_videos_without_transcripts(channel_id, limit=limit)
    logger.info("Fetching transcripts for %d videos (channel %s)", len(video_ids), channel_id)

    fetched = 0
    for i, video_id in enumerate(video_ids, 1):
        text = _fetch_one(video_id)
        if text:
            _save_transcript(video_id, text)
            fetched += 1
            logger.info("[%d/%d] ✓ transcript saved for %s (%d chars)",
                        i, len(video_ids), video_id, len(text))
        else:
            logger.info("[%d/%d] – no transcript for %s", i, len(video_ids), video_id)

        # Rate-limit: pause between requests to avoid IP bans / proxy throttling
        if i < len(video_ids):
            time.sleep(3.0)

    logger.info("Done. Fetched %d/%d transcripts for channel %s", fetched, len(video_ids), channel_id)
    return fetched


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _get_videos_without_transcripts(channel_id: str, limit: int = _MAX_TRANSCRIPTS) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id FROM videos
               WHERE channel_id=? AND (transcript IS NULL OR transcript='')
               ORDER BY published_at DESC
               LIMIT ?""",
            (channel_id, limit)
        ).fetchall()
    return [r["id"] for r in rows]


def _make_ytt_api() -> YouTubeTranscriptApi:
    cookie_path = config.YOUTUBE_COOKIES_PATH
    proxy_user  = config.WEBSHARE_PROXY_USERNAME
    proxy_pass  = config.WEBSHARE_PROXY_PASSWORD

    if cookie_path and Path(cookie_path).exists():
        logger.info("Using YouTube cookies from %s", cookie_path)
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(cookie_path, ignore_discard=True, ignore_expires=True)
        session = requests.Session()
        session.cookies = jar  # type: ignore[assignment]
        return YouTubeTranscriptApi(http_client=session)

    if proxy_user and proxy_pass:
        logger.info("Using Webshare proxy for transcript fetching")
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=proxy_user,
                proxy_password=proxy_pass,
            )
        )

    logger.info("Fetching transcripts directly (no cookie/proxy configured)")
    return YouTubeTranscriptApi()

_ytt_api = _make_ytt_api()


def _fetch_one(video_id: str) -> str | None:
    """Try to get a transcript for one video. Returns None on failure."""
    for attempt in range(1, 4):
        try:
            # v1.x API: instantiate the class then call .fetch()
            # Try preferred English languages via .list() first; fall back to .fetch()
            try:
                transcript_list = _ytt_api.list(video_id)
                transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
                entries = transcript.fetch()
            except Exception:
                entries = _ytt_api.fetch(video_id)
            return " ".join(s.text.strip() for s in entries if s.text)
        except Exception as e:
            err_name = type(e).__name__
            err_str = str(e)
            if err_name in ("NoTranscriptFound", "TranscriptsDisabled", "VideoUnavailable"):
                return None   # not retryable
            if "UNEXPECTED_EOF_WHILE_READING" in err_str or "SSLEOFError" in err_str:
                logger.warning("SSL connection dropped for %s, skipping", video_id)
                return None   # proxy dropped connection, skip rather than retry
            if attempt == 3:
                logger.warning("Transcript fetch failed for %s after 3 attempts: %s", video_id, e)
                return None
            time.sleep(2 ** attempt)
    return None


def _save_transcript(video_id: str, text: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE videos SET transcript=? WHERE id=?",
            (text, video_id)
        )
