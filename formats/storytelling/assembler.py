"""
formats/storytelling/assembler.py — Assemble a storytelling short via FFmpeg.

Supports two layouts:
  - Full-screen: background gameplay + burned-in ASS subtitles (original)
  - Split-screen: full gameplay background + scrolling Reddit post overlay + ASS subtitles

Public API:
    assemble_video(background_path, audio_path, subtitles_path, output_path) -> str
    assemble_split_video(background_path, audio_path, post_image_path, output_path, subtitles_path=None) -> str
"""

import json
import logging
import random
import subprocess
from pathlib import Path

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

# Absolute path to the music directory
_MUSIC_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "music"


def _pick_music_file() -> Path | None:
    """Return a random music file from assets/music/, or None if none exist."""
    candidates = (
        list(_MUSIC_DIR.glob("*.mp3"))
        + list(_MUSIC_DIR.glob("*.wav"))
        + list(_MUSIC_DIR.glob("*.m4a"))
    )
    if not candidates:
        return None
    return random.choice(candidates)


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
        duration_seconds = _probe_duration(aud)

    logger.info(
        "Assembling video | bg=%s | audio=%s | subs=%s | duration=%.2fs",
        bg.name, aud.name, subs.name, duration_seconds,
    )

    music = _pick_music_file()
    if music is None:
        logger.warning("No music files in assets/music/ — skipping background music")

    cmd = _build_ffmpeg_cmd(bg, aud, subs, out, duration_seconds, music_path=music)
    logger.info("FFmpeg command:\n  %s", " ".join(cmd))

    _run_ffmpeg(cmd)

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
    music_path: Path | None = None,
) -> list[str]:
    """Build the FFmpeg argument list.

    Video filter chain:
        crop=ih*9/16:ih   — center-crop landscape input to 9:16 aspect ratio
        scale=1080:1920   — scale to target resolution
        ass={path}        — burn in subtitles

    The background is stream-looped so shorter clips can cover any duration.
    When music_path is provided, mixes narration + music via filter_complex.
    """
    # Escape the subtitle path for use inside an FFmpeg filter string.
    # On Linux the main hazards are backslashes and colons.
    ass_escaped = _escape_filter_path(str(subs))
    fonts_escaped = _escape_filter_path(_FONTS_DIR)
    adjusted_duration = duration / AUDIO_SPEED

    if music_path is not None:
        vf_chain = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass_escaped}:fontsdir={fonts_escaped}"
        fc = (
            f"[0:v]{vf_chain}[vout];"
            f"[1:a]atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}[narr];"
            f"[2:a]volume=0.08[mus];"
            f"[narr][mus]amix=inputs=2:duration=first[aout]"
        )
        return [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1",          # loop background indefinitely
            "-i", str(bg),                 # input 0: background video
            "-i", str(audio),              # input 1: narration audio
            "-stream_loop", "-1",          # loop music indefinitely
            "-i", str(music_path),         # input 2: background music
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
    else:
        vf = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass_escaped}:fontsdir={fonts_escaped}"
        af = f"atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}"
        return [
            "ffmpeg",
            "-y",                          # overwrite output without prompting
            "-stream_loop", "-1",          # loop background indefinitely
            "-i", str(bg),                 # input 0: background video
            "-i", str(audio),              # input 1: narration audio
            "-t", str(adjusted_duration),  # trim to sped-up duration
            "-vf", vf,
            "-af", af,
            "-map", "0:v",                 # video from background
            "-map", "1:a",                 # audio from narration
            "-c:v", _VIDEO_CODEC,
            "-preset", _PRESET,
            "-crf", _CRF,
            "-c:a", _AUDIO_CODEC,
            "-b:a", _AUDIO_BR,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",     # optimize for streaming / quick preview
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
# ffprobe helper
# ---------------------------------------------------------------------------

def _probe_duration(audio_path: Path) -> float:
    """Return the duration of an audio file in seconds using ffprobe."""
    logger.info("Probing audio duration: %s", audio_path)
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "a:0",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    if not streams:
        raise RuntimeError(f"ffprobe found no audio streams in {audio_path}")

    duration = float(streams[0].get("duration", 0))
    logger.info("Probed duration: %.3fs", duration)
    return duration


# ---------------------------------------------------------------------------
# FFmpeg runner
# ---------------------------------------------------------------------------

def _run_ffmpeg(cmd: list[str]) -> None:
    """Run an FFmpeg command, streaming stderr to the logger."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found — please install FFmpeg") from None

    # FFmpeg writes progress to stderr even on success
    if proc.returncode != 0:
        # Log the tail of stderr to help debug
        stderr_tail = "\n".join(proc.stderr.splitlines()[-20:])
        logger.error("FFmpeg failed (exit %d):\n%s", proc.returncode, stderr_tail)
        raise RuntimeError(f"FFmpeg exited with code {proc.returncode}")

    logger.debug("FFmpeg stderr:\n%s", proc.stderr)


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
        duration_seconds = _probe_duration(aud)

    logger.info(
        "Assembling split video | bg=%s | audio=%s | post=%s | subs=%s | duration=%.2fs",
        bg.name, aud.name, post.name,
        subs.name if subs else "none", duration_seconds,
    )

    cmd = _build_split_ffmpeg_cmd(bg, aud, post, out, duration_seconds, subs)
    logger.info("FFmpeg command:\n  %s", " ".join(cmd))
    _run_ffmpeg(cmd)

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
    adjusted_duration = duration / AUDIO_SPEED
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

