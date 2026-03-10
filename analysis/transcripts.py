"""
analysis/transcripts.py — Fetch and store transcripts for videos in the database.

Public API:
    fetch_transcripts(channel_id) -> int   (returns count of transcripts fetched)
"""

import logging
import time
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi

from analysis.db import get_connection

logger = logging.getLogger(__name__)


def fetch_transcripts(channel_id: str) -> int:
    """Fetch transcripts for all videos in the channel that don't have one yet.

    Args:
        channel_id: The YouTube channel ID already stored in the database.

    Returns:
        Number of transcripts successfully fetched.
    """
    video_ids = _get_videos_without_transcripts(channel_id)
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

    logger.info("Done. Fetched %d/%d transcripts for channel %s", fetched, len(video_ids), channel_id)
    return fetched


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _get_videos_without_transcripts(channel_id: str) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM videos WHERE channel_id=? AND (transcript IS NULL OR transcript='')",
            (channel_id,)
        ).fetchall()
    return [r["id"] for r in rows]


_ytt_api = YouTubeTranscriptApi()


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
            if err_name in ("NoTranscriptFound", "TranscriptsDisabled", "VideoUnavailable"):
                return None   # not retryable
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
