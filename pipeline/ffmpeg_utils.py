"""
pipeline/ffmpeg_utils.py — Shared FFmpeg helpers used by both assemblers.

Public API:
    run_ffmpeg(cmd)                     -> None
    probe_audio_duration(audio_path)    -> float
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Prefer ffmpeg-full (includes libass for subtitle rendering) over the standard bottle
_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFPROBE_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffprobe")

FFMPEG_BIN = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else (shutil.which("ffmpeg") or "ffmpeg")
FFPROBE_BIN = str(_FFPROBE_FULL) if _FFPROBE_FULL.exists() else (shutil.which("ffprobe") or "ffprobe")


def probe_audio_duration(audio_path: Path) -> float:
    """Return the duration of an audio file in seconds using ffprobe."""
    logger.info("Probing audio duration: %s", audio_path)
    result = subprocess.run(
        [
            FFPROBE_BIN,
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
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise RuntimeError(f"ffprobe found no audio streams in {audio_path}")
    duration = float(streams[0].get("duration", 0))
    logger.info("Probed duration: %.3fs", duration)
    return duration


def run_ffmpeg(cmd: list[str]) -> None:
    """Run an FFmpeg command, streaming stderr to the logger on failure."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found — please install FFmpeg") from None

    if proc.returncode != 0:
        stderr_tail = "\n".join(proc.stderr.splitlines()[-20:])
        logger.error("FFmpeg failed (exit %d):\n%s", proc.returncode, stderr_tail)
        raise RuntimeError(f"FFmpeg exited with code {proc.returncode}")

    logger.debug("FFmpeg stderr:\n%s", proc.stderr)
