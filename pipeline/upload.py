"""
pipeline/upload.py — Upload module for YouTube Shorts and Instagram Reels.

Handles:
  - YouTube OAuth 2.0 setup and upload via google-api-python-client
  - Instagram Graph API Reels upload (container -> poll -> publish)
  - Instagram long-lived token refresh
  - AI-generated upload metadata (title + description + hashtags) via Claude Haiku
  - Upload record logging to SQLite (uploads table)
  - Retry logic with exponential backoff on 5xx errors

Usage:
    from pipeline.upload import (
        setup_youtube_oauth, upload_to_youtube,
        upload_to_instagram, refresh_instagram_token_if_needed,
        generate_upload_metadata,
        init_upload_table, log_upload, get_upload_history,
    )
"""
from __future__ import annotations

import json
import logging
import random
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import anthropic
import requests

from pipeline.claude_utils import strip_markdown_fences
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import (
    ANTHROPIC_API_KEY,
    CLOUDFLARE_R2_ACCOUNT_ID,
    CLOUDFLARE_R2_ACCESS_KEY,
    CLOUDFLARE_R2_SECRET_KEY,
    CLOUDFLARE_R2_BUCKET,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "22"  # People & Blogs
RETRIABLE_HTTP_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 10

INSTAGRAM_BASE_URL = "https://graph.facebook.com/v19.0"
INSTAGRAM_POLL_INTERVAL_SECONDS = 60
INSTAGRAM_POLL_MAX_ATTEMPTS = 5

METADATA_MODEL = "claude-haiku-4-5-20251001"
METADATA_MAX_TOKENS = 256
METADATA_TEMPERATURE = 0.85


# ---------------------------------------------------------------------------
# Schema / DB
# ---------------------------------------------------------------------------

def init_upload_table(conn: sqlite3.Connection) -> None:
    """Create the uploads table if it does not already exist.

    Safe to call on an existing database (CREATE TABLE IF NOT EXISTS).
    Follows the same pattern as init_backlog_tables in pipeline/backlog.py.

    Args:
        conn: Active SQLite connection.
    """
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS uploads (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        channel     TEXT NOT NULL,
        platform    TEXT NOT NULL,
        video_id    TEXT NOT NULL,
        title       TEXT NOT NULL,
        status      TEXT NOT NULL,
        error_msg   TEXT,
        uploaded_at TEXT NOT NULL
    );
    """)
    logger.debug("init_upload_table: uploads table ready")


def log_upload(
    conn: sqlite3.Connection,
    channel: str,
    platform: str,
    video_id: str,
    title: str,
    status: str,
    error_msg: Optional[str] = None,
) -> None:
    """Insert an upload record into the uploads table.

    Args:
        conn:      Active SQLite connection.
        channel:   Channel slug (e.g. 'relationships').
        platform:  'youtube' or 'instagram'.
        video_id:  Platform-assigned video/media ID.
        title:     Upload title used for the video.
        status:    'success' or 'error'.
        error_msg: Optional error message for failed uploads.
    """
    uploaded_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO uploads (channel, platform, video_id, title, status, error_msg, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (channel, platform, video_id, title, status, error_msg, uploaded_at),
    )
    conn.commit()
    logger.info(
        "log_upload: channel=%s platform=%s video_id=%s status=%s",
        channel, platform, video_id, status,
    )


def get_upload_history(
    conn: sqlite3.Connection,
    channel: str,
    limit: int = 20,
) -> list[dict]:
    """Return recent upload records for a channel, newest first.

    Args:
        conn:    Active SQLite connection with row_factory=sqlite3.Row.
        channel: Channel slug to filter by.
        limit:   Maximum number of records to return (default 20).

    Returns:
        List of dicts with keys: id, channel, platform, video_id, title,
        status, error_msg, uploaded_at.
    """
    rows = conn.execute(
        "SELECT * FROM uploads WHERE channel=? ORDER BY uploaded_at DESC LIMIT ?",
        (channel, limit),
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

def setup_youtube_oauth(channel_cfg, token_path: Path) -> None:
    """Perform OAuth 2.0 authorization flow and save credentials to token_path.

    Opens a local browser window for the user to authorize the application.
    Credentials are saved as JSON to token_path for use by upload_to_youtube().

    IMPORTANT: Videos uploaded via OAuth may appear as private until the GCP
    project completes the YouTube API compliance audit. Submit the audit request
    at https://support.google.com/youtube/contact/yt_api_form before going live.

    Args:
        channel_cfg: ChannelConfig with youtube_client_id and youtube_client_secret.
        token_path:  Path where credentials JSON will be saved.
    """
    client_config = {
        "installed": {
            "client_id": channel_cfg.youtube_client_id,
            "client_secret": channel_cfg.youtube_client_secret,
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    logger.info("setup_youtube_oauth: saved token to %s", token_path)
    logger.warning(
        "IMPORTANT: Videos may appear as private until your GCP project passes "
        "the YouTube API compliance audit. Submit at: "
        "https://support.google.com/youtube/contact/yt_api_form"
    )


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    token_path: Path,
    client_id: str,
    client_secret: str,
    publish_at: str | None = None,
    made_for_kids: bool = False,
) -> str:
    """Upload a video to YouTube Shorts and return the YouTube video ID.

    Loads OAuth credentials from token_path, refreshes if expired, then
    uploads the video using the resumable upload protocol.

    Args:
        video_path:    Path to the local MP4 file.
        title:         Video title (under 100 chars recommended).
        description:   Video description.
        tags:          List of tags (strings, no # prefix).
        token_path:    Path to saved OAuth token JSON.
        client_id:     YouTube OAuth client ID (for credential refresh).
        client_secret: YouTube OAuth client secret.
        publish_at:    Optional ISO 8601 datetime string (e.g. "2026-03-13T09:00:00Z").
                       When provided, the video is uploaded as private and scheduled
                       to go public at the specified time. When None (default), the
                       video is uploaded as public immediately.
        made_for_kids: Whether the video is made for kids (affects ad targeting
                       and YouTube's restricted mode).

    Returns:
        YouTube video ID string (e.g. 'dQw4w9WgXcQ').

    Raises:
        HttpError: On non-retriable API errors or after MAX_RETRIES exhausted.
    """
    creds = Credentials.from_authorized_user_file(str(token_path))

    if creds.expired and creds.refresh_token:
        logger.info("upload_to_youtube: refreshing expired credentials")
        creds.refresh(Request())
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)

    if publish_at:
        logger.info("upload_to_youtube: scheduling publish at %s", publish_at)
        status_block = {
            "privacyStatus": "private",
            "publishAt": publish_at,
        }
    else:
        status_block = {
            "privacyStatus": "public",
        }

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": YOUTUBE_CATEGORY_ID,
        },
        "status": {
            **status_block,
            "madeForKids": made_for_kids,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = _resumable_upload(insert_request)
    video_id = response["id"]
    logger.info("upload_to_youtube: uploaded video_id=%s title=%r", video_id, title)
    return video_id


def _resumable_upload(insert_request) -> dict:
    """Execute a resumable YouTube upload, retrying on 5xx errors.

    Args:
        insert_request: A YouTube API insert request object with next_chunk().

    Returns:
        API response dict containing at least 'id'.

    Raises:
        HttpError: On non-retriable errors or after MAX_RETRIES exhausted.
    """
    retry = 0
    while retry <= MAX_RETRIES:
        try:
            _, response = insert_request.next_chunk()
            logger.debug("_resumable_upload: upload complete response=%s", response)
            return response
        except HttpError as e:
            if e.resp.status in RETRIABLE_HTTP_STATUS:
                retry += 1
                if retry > MAX_RETRIES:
                    logger.error(
                        "_resumable_upload: max retries (%d) exceeded, last status=%d",
                        MAX_RETRIES, e.resp.status,
                    )
                    raise
                sleep_time = random.random() * (2 ** retry)
                logger.warning(
                    "_resumable_upload: HTTP %d, retry %d/%d, sleeping %.1fs",
                    e.resp.status, retry, MAX_RETRIES, sleep_time,
                )
                time.sleep(sleep_time)
            else:
                logger.error("_resumable_upload: non-retriable HTTP %d", e.resp.status)
                raise


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------

def _upload_to_r2(video_path: Path) -> str:
    """Upload a local video file to Cloudflare R2 and return its public URL.

    Args:
        video_path: Local path to the MP4 file.

    Returns:
        Public R2 URL for the uploaded file.

    Raises:
        RuntimeError: If R2 credentials are missing or upload fails.
    """
    if not all([CLOUDFLARE_R2_ACCOUNT_ID, CLOUDFLARE_R2_ACCESS_KEY,
                CLOUDFLARE_R2_SECRET_KEY, CLOUDFLARE_R2_BUCKET]):
        raise RuntimeError(
            "Missing R2 credentials. Set CLOUDFLARE_R2_ACCOUNT_ID, "
            "CLOUDFLARE_R2_ACCESS_KEY, CLOUDFLARE_R2_SECRET_KEY, and "
            "CLOUDFLARE_R2_BUCKET in .env"
        )

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=CLOUDFLARE_R2_ACCESS_KEY,
        aws_secret_access_key=CLOUDFLARE_R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    key = f"videos/{video_path.name}"
    client.upload_file(str(video_path), CLOUDFLARE_R2_BUCKET, key)

    public_url = f"https://{CLOUDFLARE_R2_BUCKET}.r2.dev/{key}"
    # Handle custom dev URL: if bucket is 'auto-shorts' but the dev URL uses the full hash ID
    if CLOUDFLARE_R2_BUCKET == "auto-shorts":
        public_url = f"https://pub-e415244b47094357ae0421689ee0435b.r2.dev/{key}"
    logger.info("_upload_to_r2: uploaded %s -> %s", video_path.name, public_url)
    return public_url


def upload_to_instagram(
    video_path: Path,
    caption: str,
    ig_user_id: str,
    access_token: str,
) -> str:
    """Upload a video as an Instagram Reel using the Graph API.

    Flow:
      1. Upload local video to R2 to get a public URL.
      2. Create an Instagram media container (video_url as R2 URL).
      3. Poll the container until status is FINISHED.
      4. Publish the container and return the media ID.

    Args:
        video_path:    Path to the local MP4 video file.
        caption:       Post caption (may include hashtags with # prefix).
        ig_user_id:    Instagram User ID (numeric string).
        access_token:  Instagram/Meta long-lived access token.

    Returns:
        Instagram media ID string.

    Raises:
        RuntimeError: If container status is ERROR or polling times out.
        requests.HTTPError: On HTTP request failures.
    """
    # Step 0: Upload to R2 to get a public URL
    video_url = _upload_to_r2(video_path)

    # Step 1: Create container with video_url as R2 URL
    create_url = f"{INSTAGRAM_BASE_URL}/{ig_user_id}/media"
    logger.info("upload_to_instagram: creating container with video_url=%s", video_url)

    create_resp = requests.post(
        create_url,
        data={
            "video_url": video_url,
            "media_type": "REELS",
            "caption": caption,
            "share_to_feed": "true",
            "access_token": access_token,
        },
    )

    if not create_resp.ok:
        logger.error("upload_to_instagram: container creation failed — HTTP %d: %s",
                     create_resp.status_code, create_resp.text)
        create_resp.raise_for_status()
    container_id = create_resp.json()["id"]
    logger.info("upload_to_instagram: container_id=%s", container_id)

    # Step 2: Poll container status
    status_url = f"{INSTAGRAM_BASE_URL}/{container_id}"
    status_params = {
        "fields": "status_code",
        "access_token": access_token,
    }

    for attempt in range(1, INSTAGRAM_POLL_MAX_ATTEMPTS + 1):
        status_resp = requests.get(status_url, params=status_params)
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code", "")
        logger.info(
            "upload_to_instagram: poll attempt %d/%d status=%s",
            attempt, INSTAGRAM_POLL_MAX_ATTEMPTS, status_code,
        )

        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(
                f"Instagram container {container_id} failed with ERROR status"
            )
        # Still processing — wait and retry
        time.sleep(INSTAGRAM_POLL_INTERVAL_SECONDS)
    else:
        raise RuntimeError(
            f"Instagram container {container_id} timed out after "
            f"{INSTAGRAM_POLL_MAX_ATTEMPTS} polling attempts (>5 minutes)"
        )

    # Step 3: Publish
    publish_url = f"{INSTAGRAM_BASE_URL}/{ig_user_id}/media_publish"
    publish_resp = requests.post(
        publish_url,
        params={"creation_id": container_id, "access_token": access_token},
    )
    publish_resp.raise_for_status()
    media_id = publish_resp.json()["id"]
    logger.info("upload_to_instagram: published media_id=%s", media_id)
    return media_id


def refresh_instagram_token_if_needed(token_path: Path) -> str:
    """Refresh the Instagram long-lived access token if it expires within 7 days.

    Reads instagram_token.json, checks expires_at timestamp. If the token
    will expire in fewer than 7 days, calls the Graph API refresh endpoint
    and saves the updated token + new expiry to the same file.

    Token file format:
        {
            "access_token": "...",
            "expires_at": "2026-06-01T00:00:00+00:00"
        }

    Args:
        token_path: Path to the instagram_token.json file.

    Returns:
        Current (or refreshed) access token string.
    """
    with open(token_path, "r", encoding="utf-8") as f:
        token_data = json.load(f)

    access_token = token_data["access_token"]
    expires_at = datetime.fromisoformat(token_data["expires_at"])
    # Ensure timezone-aware for comparison
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    days_remaining = (expires_at - now).days

    if days_remaining < 7:
        logger.info(
            "refresh_instagram_token_if_needed: token expires in %d days, refreshing",
            days_remaining,
        )
        refresh_url = "https://graph.instagram.com/refresh_access_token"
        resp = requests.get(
            refresh_url,
            params={
                "grant_type": "ig_refresh_token",
                "access_token": access_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        new_token = data["access_token"]
        expires_in_seconds = data.get("expires_in", 5184000)  # default 60 days
        new_expires_at = (now + timedelta(seconds=expires_in_seconds)).isoformat()

        updated = {
            "access_token": new_token,
            "expires_at": new_expires_at,
        }
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2)

        logger.info(
            "refresh_instagram_token_if_needed: token refreshed, new expiry=%s",
            new_expires_at,
        )
        return new_token

    logger.debug(
        "refresh_instagram_token_if_needed: token valid for %d more days, no refresh needed",
        days_remaining,
    )
    return access_token


# ---------------------------------------------------------------------------
# Metadata generation
# ---------------------------------------------------------------------------

def generate_upload_metadata(
    content_text: str,
    niche_hashtags: list[str],
    format_type: str,
) -> dict:
    """Generate a YouTube/Instagram title, description, and hashtags using Claude Haiku.

    Calls Anthropic Haiku (temperature 0.85) with the content text and
    returns a merged dict with AI-suggested title, description, and
    deduplicated hashtags (Claude's suggestions + niche_hashtags from
    channels.yaml).

    Args:
        content_text:   The story body, tweet text, or video script excerpt.
        niche_hashtags: Channel-level hashtags from channels.yaml (no # prefix).
        format_type:    'storytelling' or 'tweets' -- used in the prompt.

    Returns:
        Dict with:
            "title"       : str -- compelling title under 100 chars, no clickbait
            "description" : str -- 1-2 sentence video description
            "hashtags"    : list[str] -- deduplicated tags (no # prefix)
    """
    system_prompt = (
        "You are a social media expert specializing in YouTube Shorts and Instagram Reels. "
        "Generate upload metadata as JSON with this exact schema:\n"
        '{"title": "...", "description": "...", "hashtags": ["tag1", "tag2", "tag3"]}\n\n'
        "Rules:\n"
        "- title: ONE sentence only, ends with '?' (a compelling question), 50-80 chars, no ellipsis, no clickbait\n"
        "- description: 2-3 sentences that CONTINUE the scenario from the title (do NOT repeat the title), "
        "ends with a period (full sentence, no '...' truncation), no hashtags, 150-400 chars\n"
        "- hashtags: 2-3 content-specific tags, NO # prefix, lowercase\n"
        "- Output valid JSON only, no explanation"
    )
    user_prompt = (
        f"Format: {format_type}\n\n"
        f"Content:\n{content_text}\n\n"
        "Generate title, description, and hashtags for this content."
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=METADATA_MODEL,
            temperature=METADATA_TEMPERATURE,
            max_tokens=METADATA_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text.strip()
                break
        if not text:
            raise ValueError("No TextBlock in Claude response")
        ai_result = json.loads(strip_markdown_fences(text))
    except Exception as exc:
        logger.error("generate_upload_metadata: Claude call failed: %s", exc)
        # Fallback title: truncate at last word boundary within 80 chars
        _t = content_text.strip()
        if len(_t) > 80:
            _t = _t[:80]
            last_space = _t.rfind(" ")
            if last_space > 40:
                _t = _t[:last_space]
            _t = _t.rstrip(",-") + "..."
        # Fallback description: first 2 sentences, up to 200 chars
        _sentences = [s.strip() for s in content_text.split(". ") if s.strip()]
        _desc = ". ".join(_sentences[:2])
        if _desc and not _desc.endswith("."):
            _desc += "."
        if len(_desc) > 200:
            _desc = _desc[:200].rstrip() + "..."
        ai_result = {"title": _t, "description": _desc, "hashtags": []}

    title = ai_result.get("title", content_text[:80])
    description = ai_result.get("description", "")

    # Truncate title to YouTube's 100-char limit at word boundary (no ellipsis)
    if len(title) > 100:
        cut = title[:100]
        last_space = cut.rfind(" ")
        if last_space > 40:
            cut = cut[:last_space]
        title = cut.rstrip(",-")

    # Truncate description to 400 chars at word boundary (no ellipsis)
    if len(description) > 400:
        cut = description[:400]
        last_space = cut.rfind(" ")
        if last_space > 40:
            cut = cut[:last_space]
        description = cut.rstrip(",-")

    ai_hashtags = ai_result.get("hashtags", [])

    # Merge and deduplicate (preserve order: AI tags first, then niche)
    seen: set[str] = set()
    merged: list[str] = []
    for tag in ai_hashtags + niche_hashtags:
        normalized = tag.lstrip("#").lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)

    logger.info(
        "generate_upload_metadata: title=%r description=%r hashtags=%s",
        title, description, merged,
    )
    return {"title": title, "description": description, "hashtags": merged}


def save_metadata_file(
    video_path: str,
    metadata: dict,
) -> str:
    """Save upload metadata as a text file next to the video for manual uploads.

    Creates a .txt file with the same stem as the video containing the title,
    description, and hashtags in a copy-pasteable format.

    Args:
        video_path: Path to the generated MP4.
        metadata:   Dict from generate_upload_metadata (title, description, hashtags).

    Returns:
        Absolute path of the written metadata file.
    """
    video = Path(video_path)
    meta_path = video.with_suffix(".txt")

    hashtag_str = " ".join(f"#{t}" for t in metadata.get("hashtags", []))

    lines = [
        f"Title: {metadata.get('title', '')}",
        "",
        metadata.get("description", ""),
        "",
        hashtag_str,
    ]

    meta_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved upload metadata → %s", meta_path)
    return str(meta_path)
