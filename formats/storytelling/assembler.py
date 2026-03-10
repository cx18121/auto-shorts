"""
formats/storytelling/assembler.py — Assemble a storytelling short via FFmpeg.

Takes a background video, narration audio, and an ASS subtitle file and
produces a 1080×1920 (9:16) MP4 with burned-in subtitles.

Public API:
    assemble_video(background_path, audio_path, subtitles_path, output_path) -> str
"""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# FFmpeg encode settings
_VIDEO_CODEC = "libx264"
_PRESET      = "fast"
_CRF         = "23"          # quality (lower = better; 23 is a good default)
_AUDIO_CODEC = "aac"
_AUDIO_BR    = "192k"


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

    cmd = _build_ffmpeg_cmd(bg, aud, subs, out, duration_seconds)
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
) -> list[str]:
    """Build the FFmpeg argument list.

    Video filter chain:
        crop=ih*9/16:ih   — center-crop landscape input to 9:16 aspect ratio
        scale=1080:1920   — scale to target resolution
        ass={path}        — burn in subtitles

    The background is stream-looped so shorter clips can cover any duration.
    """
    # Escape the subtitle path for use inside an FFmpeg filter string.
    # On Linux the main hazards are backslashes and colons.
    ass_escaped = _escape_filter_path(str(subs))
    vf = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass_escaped}"

    return [
        "ffmpeg",
        "-y",                          # overwrite output without prompting
        "-stream_loop", "-1",          # loop background indefinitely
        "-i", str(bg),                 # input 0: background video
        "-i", str(audio),              # input 1: narration audio
        "-t", str(duration),           # trim output to narration length
        "-vf", vf,
        "-map", "0:v",                 # video from background
        "-map", "1:a",                 # audio from narration
        "-c:v", _VIDEO_CODEC,
        "-preset", _PRESET,
        "-crf", _CRF,
        "-c:a", _AUDIO_CODEC,
        "-b:a", _AUDIO_BR,
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
