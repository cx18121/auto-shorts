"""
analysis/visual.py — Download top-performing videos, extract frames, and
                     analyse them with Claude vision.

Public API:
    analyse_visuals(channel_id, top_n=20) -> int   (returns videos analysed)
"""

import base64
import json
import logging
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import anthropic

import config
from analysis.db import get_connection
from pipeline.claude_utils import strip_markdown_fences

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_FRAMES_PER_VIDEO = 9
_TOP_N_DEFAULT = 20


def analyse_visuals(channel_id: str, top_n: int = _TOP_N_DEFAULT) -> int:
    """Download, frame-sample, and Claude-analyse the top N performers.

    For each video:
      1. Download video via yt-dlp into a temp directory.
      2. Extract _FRAMES_PER_VIDEO evenly-spaced frames with FFmpeg.
      3. Send frames to Claude Sonnet (vision) for overlay/style analysis.
      4. Download thumbnail and send for thumbnail analysis.
      5. Save both JSON blobs to SQLite.
      6. Delete temp files.

    Args:
        channel_id: Channel already in the database.
        top_n:      Number of top performers to analyse.

    Returns:
        Number of videos successfully analysed.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    videos = _load_top_performers(channel_id, top_n)
    logger.info("Visual analysis: %d top-performer videos for channel %s", len(videos), channel_id)

    analysed = 0
    for i, video in enumerate(videos, 1):
        vid_id = video["id"]
        logger.info("[%d/%d] Analysing video %s: %s", i, len(videos), vid_id, video["title"][:60])

        tmp = Path(tempfile.mkdtemp(prefix="shorts_visual_"))
        try:
            # --- download video ---
            video_path = _download_video(vid_id, tmp)
            if video_path is None:
                logger.warning("Could not download %s, skipping", vid_id)
                continue

            # --- extract frames ---
            frames = _extract_frames(video_path, tmp, _FRAMES_PER_VIDEO)
            if not frames:
                logger.warning("No frames extracted for %s, skipping", vid_id)
                continue

            # --- visual analysis ---
            visual_json = _analyse_frames(client, frames, video["title"])
            logger.info("  Visual analysis done (%d chars)", len(json.dumps(visual_json)))

            # --- thumbnail analysis ---
            thumb_json: dict[str, Any] = {}
            if video["thumbnail_url"]:
                thumb_path = tmp / "thumbnail.jpg"
                _download_url(video["thumbnail_url"], thumb_path)
                if thumb_path.exists():
                    thumb_json = _analyse_thumbnail(client, thumb_path, video["title"])
                    logger.info("  Thumbnail analysis done")

            _save_analysis(vid_id, visual_json, thumb_json)
            analysed += 1

        except Exception as e:
            logger.error("Failed to analyse video %s: %s", vid_id, e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    logger.info("Visual analysis complete: %d/%d videos analysed", analysed, len(videos))
    return analysed


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_video(video_id: str, dest_dir: Path) -> Path | None:
    """Download a YouTube video using yt-dlp. Returns path or None."""
    url = f"https://www.youtube.com/shorts/{video_id}"
    out_template = str(dest_dir / "video.%(ext)s")

    try:
        subprocess.run(
            [
                "yt-dlp",
                "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
                "-o", out_template,
                "--no-playlist",
                "--quiet",
                url,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning("yt-dlp failed for %s: %s", video_id, e)
        return None

    # Find the downloaded file
    for p in dest_dir.iterdir():
        if p.name.startswith("video."):
            return p
    return None


def _download_url(url: str, dest: Path) -> None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dest.write_bytes(resp.read())
    except Exception as e:
        logger.warning("Could not download %s: %s", url, e)


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def _extract_frames(video_path: Path, dest_dir: Path, count: int) -> list[Path]:
    """Extract `count` evenly-spaced JPEG frames from a video using FFmpeg."""
    frames_dir = dest_dir / "frames"
    frames_dir.mkdir()

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(video_path),
                "-vf", f"select=not(mod(n\\,floor(1/({count}/duration)))),scale=640:-1",
                "-vsync", "vfr",
                "-frames:v", str(count),
                "-q:v", "3",
                str(frames_dir / "frame_%03d.jpg"),
                "-y",
            ],
            capture_output=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.warning("FFmpeg frame extraction timed out for %s", video_path)

    # Fallback: fps-based extraction if the above produces no frames
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if not frames:
        duration = _probe_duration(video_path)
        if duration > 0:
            interval = max(duration / count, 0.5)
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", str(video_path),
                    "-vf", f"fps=1/{interval:.2f},scale=640:-1",
                    "-frames:v", str(count),
                    "-q:v", "3",
                    str(frames_dir / "frame_%03d.jpg"),
                    "-y",
                ],
                capture_output=True,
                timeout=60,
            )
        frames = sorted(frames_dir.glob("frame_*.jpg"))

    return frames[:count]


def _probe_duration(video_path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-select_streams", "v:0", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        info = json.loads(result.stdout)
        return float(info["streams"][0].get("duration", 0))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Claude vision analysis
# ---------------------------------------------------------------------------

_FRAME_ANALYSIS_PROMPT = """You are analysing frames from a YouTube Shorts video to extract style information.

Video title: {title}

Analyse these {n} frames and return a JSON object with exactly this structure:
{{
  "text_overlay_style": "detailed description of text overlays: font style, size impression, color, position, any background behind text",
  "color_grading": "description of color tone, saturation, brightness, overall mood",
  "face_on_screen": "yes/no/sometimes",
  "background_type": "gameplay/stock_footage/screen_recording/real_world/animation/other",
  "editing_pace": "fast/medium/slow — describe the visual rhythm based on how different consecutive frames look",
  "framing": "description of how subjects are framed and composed",
  "recurring_elements": ["list any branding, logos, or repeated visual motifs"],
  "overall_visual_style": "1-2 sentence summary of the channel's visual identity"
}}

Return only the JSON object, no other text."""

_THUMBNAIL_ANALYSIS_PROMPT = """Analyse this YouTube Shorts thumbnail and return a JSON object with exactly this structure:
{{
  "effectiveness": "what makes this thumbnail compelling (or not)",
  "text_on_thumbnail": "any text visible and how it's styled",
  "dominant_colors": ["list 2-4 dominant colors"],
  "emotional_tone": "the emotion or feeling the thumbnail conveys",
  "composition": "how elements are arranged in the frame",
  "hooks": "specific visual elements designed to attract clicks"
}}

Return only the JSON object, no other text."""


def _encode_image(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("utf-8")


def _analyse_frames(client: anthropic.Anthropic, frames: list[Path], title: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": _FRAME_ANALYSIS_PROMPT.format(title=title, n=len(frames))}
    ]
    for frame in frames:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": _encode_image(frame),
            },
        })

    return _claude_call(client, content)


def _analyse_thumbnail(client: anthropic.Anthropic, thumb_path: Path, title: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": _THUMBNAIL_ANALYSIS_PROMPT},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": _encode_image(thumb_path),
            },
        },
    ]
    return _claude_call(client, content)


def _claude_call(client: anthropic.Anthropic, content: list[dict], max_attempts: int = 3) -> dict[str, Any]:
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=1024,
                temperature=0.3,
                messages=[{"role": "user", "content": content}],
            )
            return json.loads(strip_markdown_fences(resp.content[0].text))
        except json.JSONDecodeError as e:
            logger.warning("Claude returned invalid JSON (attempt %d): %s", attempt, e)
            if attempt == max_attempts:
                return {"error": "invalid JSON from Claude", "raw": resp.content[0].text[:200]}
        except Exception as e:
            logger.warning("Claude vision call failed (attempt %d): %s", attempt, e)
            if attempt == max_attempts:
                return {"error": str(e)}
            time.sleep(2 ** attempt)
    return {}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _load_top_performers(channel_id: str, top_n: int) -> list[Any]:
    with get_connection() as conn:
        return conn.execute(
            """SELECT id, title, thumbnail_url FROM videos
               WHERE channel_id=? AND is_top_performer=1
               ORDER BY performance_score DESC LIMIT ?""",
            (channel_id, top_n),
        ).fetchall()


def _save_analysis(video_id: str, visual: dict, thumbnail: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE videos SET visual_analysis=?, thumbnail_analysis=? WHERE id=?",
            (json.dumps(visual), json.dumps(thumbnail), video_id),
        )
