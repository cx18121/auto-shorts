"""
formats/storytelling/assembler.py — Assemble a storytelling short via FFmpeg.

Supports two layouts:
  - Full-screen: background gameplay + burned-in ASS subtitles (original)
  - Split-screen: full gameplay background + scrolling Reddit post overlay + ASS subtitles

Public API:
    assemble_video(background_path, audio_path, subtitles_path, output_path) -> str
    assemble_split_video(background_path, audio_path, post_image_path, output_path, subtitles_path=None) -> str
"""

import logging
import random
import subprocess
from pathlib import Path

from pipeline.ffmpeg_utils import probe_audio_duration, run_ffmpeg as _run_ffmpeg_shared

logger = logging.getLogger(__name__)

# Absolute path to the fonts directory — passed to FFmpeg's ass filter via fontsdir
_FONTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "assets" / "fonts")

# FFmpeg encode settings
_VIDEO_CODEC = "libx264"
_PRESET      = "medium"
_CRF         = "18"          # quality (lower = better; 18 = visually lossless)
_AUDIO_CODEC = "aac"
_AUDIO_BR    = "192k"

# Audio processing: speed up narration slightly and boost volume
AUDIO_SPEED  = 1.3           # 30% faster playback
_AUDIO_VOLUME = "1.5"        # 50% volume boost


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assemble_video(
    background_path: str,
    audio_path: str,
    subtitles_path: str,
    output_path: str,
    duration_seconds: float | None = None,
) -> str:
    """Assemble a 9:16 storytelling short video.

    Steps performed by FFmpeg:
      1. Loop the background clip so it always covers the full audio duration.
      2. Center-crop to 9:16 and scale to 1080×1920.
      3. Burn in the ASS subtitles.
      4. Replace background audio with the narration track.
      5. Trim output to the narration duration.

    Args:
        background_path: Path to a background gameplay video (any resolution).
        audio_path: Path to the narration MP3/WAV.
        subtitles_path: Path to the .ass subtitle file.
        output_path: Destination path for the final MP4.
        duration_seconds: Length to trim to. If None, probed from audio_path.

    Returns:
        Absolute path of the written MP4.
    """
    bg   = Path(background_path).resolve()
    aud  = Path(audio_path).resolve()
    subs = Path(subtitles_path).resolve()
    out  = Path(output_path).resolve()

    for label, p in [("background", bg), ("audio", aud), ("subtitles", subs)]:
        if not p.exists():
            raise FileNotFoundError(f"{label} file not found: {p}")

    out.parent.mkdir(parents=True, exist_ok=True)

    if duration_seconds is None:
        duration_seconds = probe_audio_duration(aud)

    logger.info(
        "Assembling video | bg=%s | audio=%s | subs=%s | duration=%.2fs",
        bg.name, aud.name, subs.name, duration_seconds,
    )

    adjusted_duration = duration_seconds / AUDIO_SPEED + 0.5
    bg_start = _random_bg_start(bg, adjusted_duration)

    cmd = _build_ffmpeg_cmd(bg, aud, subs, out, duration_seconds, bg_start=bg_start)
    logger.info("FFmpeg command:\n  %s", " ".join(cmd))

    _run_ffmpeg_shared(cmd)

    size_mb = out.stat().st_size / 1_048_576
    logger.info("Output saved → %s (%.1f MB)", out, size_mb)
    return str(out)


# ---------------------------------------------------------------------------
# FFmpeg command builder
# ---------------------------------------------------------------------------

def _build_ffmpeg_cmd(
    bg: Path,
    audio: Path,
    subs: Path,
    output: Path,
    duration: float,
    bg_start: float = 0.0,
) -> list[str]:
    """Build the FFmpeg argument list.

    Video filter chain:
        crop=ih*9/16:ih   — center-crop landscape input to 9:16 aspect ratio
        scale=1080:1920   — scale to target resolution
        ass={path}        — burn in subtitles

    Audio: narration (sped up + boosted) mixed with gameplay audio (quiet).
    The background is stream-looped so shorter clips can cover any duration.
    """
    ass_escaped = _escape_filter_path(str(subs))
    fonts_escaped = _escape_filter_path(_FONTS_DIR)
    adjusted_duration = duration / AUDIO_SPEED + 0.5

    vf_chain = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass_escaped}:fontsdir={fonts_escaped}"
    fc = (
        f"[0:v]{vf_chain}[vout];"
        f"[1:a]atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}[narr];"
        f"[0:a]volume=0.15[game];"
        f"[narr][game]amix=inputs=2:duration=first[aout]"
    )
    return [
        "ffmpeg",
        "-y",
        "-ss", str(bg_start),          # random start point in background
        "-stream_loop", "-1",          # loop background indefinitely
        "-i", str(bg),                 # input 0: background video + gameplay audio
        "-i", str(audio),              # input 1: narration audio
        "-t", str(adjusted_duration),  # trim to sped-up duration
        "-filter_complex", fc,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", _VIDEO_CODEC,
        "-preset", _PRESET,
        "-crf", _CRF,
        "-c:a", _AUDIO_CODEC,
        "-b:a", _AUDIO_BR,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]


def _escape_filter_path(path: str) -> str:
    """Escape a file path for use in an FFmpeg -vf filter string.

    FFmpeg filter values treat backslash, colon, comma, and single-quote
    as special.  On Linux paths only colons are realistically an issue
    (Windows drive letters don't appear), but we escape defensively.
    """
    path = path.replace("\\", "/")     # normalise separators
    path = path.replace("'",  "\\'")   # escape single quotes
    path = path.replace(":",  "\\:")   # escape colons (filter delimiter)
    return f"'{path}'"


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def _probe_video_duration(video_path: Path) -> float:
    """Return the duration of a video file in seconds using ffprobe.

    Reads from format-level duration (reliable for webm/mkv/mp4) rather than
    stream-level, which is often absent in container formats like webm.
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    duration = info.get("format", {}).get("duration")
    if not duration:
        raise RuntimeError(f"ffprobe could not determine duration for {video_path}")
    return float(duration)


def _random_bg_start(bg_path: Path, required_duration: float) -> float:
    """Return a random start time within the background video.

    Since the background is stream-looped, any start point is safe — the video
    wraps around. We still pick within the actual clip duration so the seek is
    meaningful (avoids seeking past EOF on the first iteration).
    """
    try:
        bg_duration = _probe_video_duration(bg_path)
    except Exception as exc:
        logger.warning("Could not probe background duration (%s) — starting at 0", exc)
        return 0.0

    if bg_duration <= required_duration:
        # Clip is shorter than the video we need — loop covers it, start at 0
        return 0.0

    max_start = bg_duration - required_duration
    start = random.uniform(0, max_start)
    logger.info("Random background start: %.2fs (clip=%.2fs)", start, bg_duration)
    return start


# ---------------------------------------------------------------------------
# Split-screen assembly (gameplay background + Reddit post overlay + subtitles)
# ---------------------------------------------------------------------------

_POST_W = 940    # Reddit post width (narrower than canvas — gameplay border visible)
_POST_H = 960    # Reddit post overlay height (upper portion of 1920 canvas)
_POST_X = 70     # Horizontal offset to center post: (1080 - 940) / 2
_POST_Y = 232    # Top padding for post overlay (~12% from top, avoids mobile camera cutoff)
_CANVAS_W = 1080
_CANVAS_H = 1920

def assemble_split_video(
    background_path: str,
    audio_path: str,
    post_image_path: str,
    output_path: str,
    subtitles_path: str | None = None,
    duration_seconds: float | None = None,
) -> str:
    """Assemble a 9:16 video: full gameplay background + Reddit post overlay + subtitles.

    The gameplay fills the entire 1080x1920 canvas. The Reddit post image is
    overlaid on the upper portion and scrolls vertically as the narration plays.
    ASS subtitles are burned in when provided.

    Args:
        background_path:  Path to a background gameplay video.
        audio_path:       Path to the narration audio.
        post_image_path:  Path to the tall Reddit post PNG.
        output_path:      Destination path for the final MP4.
        subtitles_path:   Path to .ass subtitle file (optional).
        duration_seconds: Length to trim to. If None, probed from audio_path.

    Returns:
        Absolute path of the written MP4.
    """
    bg   = Path(background_path).resolve()
    aud  = Path(audio_path).resolve()
    post = Path(post_image_path).resolve()
    out  = Path(output_path).resolve()
    subs = Path(subtitles_path).resolve() if subtitles_path else None

    checks = [("background", bg), ("audio", aud), ("post_image", post)]
    if subs:
        checks.append(("subtitles", subs))
    for label, p in checks:
        if not p.exists():
            raise FileNotFoundError(f"{label} file not found: {p}")

    out.parent.mkdir(parents=True, exist_ok=True)

    if duration_seconds is None:
        duration_seconds = probe_audio_duration(aud)

    logger.info(
        "Assembling split video | bg=%s | audio=%s | post=%s | subs=%s | duration=%.2fs",
        bg.name, aud.name, post.name,
        subs.name if subs else "none", duration_seconds,
    )

    cmd = _build_split_ffmpeg_cmd(bg, aud, post, out, duration_seconds, subs)
    logger.info("FFmpeg command:\n  %s", " ".join(cmd))
    _run_ffmpeg_shared(cmd)

    size_mb = out.stat().st_size / 1_048_576
    logger.info("Output saved → %s (%.1f MB)", out, size_mb)
    return str(out)


def _build_split_ffmpeg_cmd(
    bg: Path,
    audio: Path,
    post_img: Path,
    output: Path,
    duration: float,
    subs: Path | None = None,
) -> list[str]:
    """Build FFmpeg command for overlay layout.

    Filter graph:
      [0:v] — background gameplay, looped → scaled/cropped to fill 1080x1920
      [1:v] — tall Reddit post PNG → scaled, scrolled, overlaid on upper portion
      Optional: ASS subtitles burned on top of the composite

    Gameplay fills the entire canvas; the Reddit post floats over the top ~960px.
    """
    adjusted_duration = duration / AUDIO_SPEED + 0.5
    # Scroll from top to bottom; if image is shorter than _POST_H, no scroll needed
    scroll_y = f"max(0,(in_h-min(in_h\\,{_POST_H})))*t/{adjusted_duration}"

    # Build filter_complex chain
    # Use min(in_h, _POST_H) for crop height so short images don't cause errors
    crop_h = f"min(in_h\\,{_POST_H})"
    fc_parts = [
        # Gameplay: fit within canvas (zoom out — no aggressive crop)
        f"[0:v]scale={_CANVAS_W}:{_CANVAS_H}:force_original_aspect_ratio=decrease,"
        f"pad={_CANVAS_W}:{_CANVAS_H}:(ow-iw)/2:(oh-ih)/2[bg]",
        # Post image: scale to narrower width, crop a scrolling window
        f"[1:v]scale={_POST_W}:-1,"
        f"crop={_POST_W}:{crop_h}:0:'{scroll_y}'[post]",
        # Overlay post centered with gameplay border visible around it
        f"[bg][post]overlay={_POST_X}:{_POST_Y}[comp]",
    ]

    # Burn subtitles if provided
    if subs:
        ass_escaped = _escape_filter_path(str(subs))
        fonts_escaped = _escape_filter_path(_FONTS_DIR)
        fc_parts.append(f"[comp]ass={ass_escaped}:fontsdir={fonts_escaped}[out]")
        out_label = "[out]"
    else:
        out_label = "[comp]"

    fc = ";".join(fc_parts)
    af = f"atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}"

    return [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", str(bg),                     # input 0: gameplay
        "-i", str(post_img),               # input 1: Reddit post PNG
        "-i", str(audio),                  # input 2: narration audio
        "-t", str(adjusted_duration),
        "-filter_complex", fc,
        "-af", af,
        "-map", out_label,                 # video from filter
        "-map", "2:a",                     # audio from narration
        "-c:v", _VIDEO_CODEC,
        "-preset", _PRESET,
        "-crf", _CRF,
        "-c:a", _AUDIO_CODEC,
        "-b:a", _AUDIO_BR,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]

