"""
formats/tweets/assembler.py — Assemble a tweet screenshot Short via FFmpeg.

Takes a static tweet PNG + narration audio and produces a 1080×1920 MP4
with a slow zoom animation.

Public API:
    assemble_tweet_video(image_path, audio_path, output_path, duration_seconds) -> str
"""

import logging
import random
from pathlib import Path

from pipeline.ffmpeg_utils import probe_audio_duration, run_ffmpeg as _run_ffmpeg_shared

logger = logging.getLogger(__name__)

_VIDEO_CODEC = "libx264"
_PRESET      = "medium"
_CRF         = "18"
_AUDIO_CODEC = "aac"
_AUDIO_BR    = "192k"
_FPS         = 30
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


def assemble_tweet_video(
    image_path: str,
    audio_path: str,
    output_path: str,
    duration_seconds: float | None = None,
) -> str:
    """Assemble a tweet Short: static image + audio + slow zoom → MP4.

    Args:
        image_path:       Path to the rendered tweet PNG (1080×1920).
        audio_path:       Path to the narration MP3.
        output_path:      Destination path for the final MP4.
        duration_seconds: Length to trim to. If None, probed from audio.

    Returns:
        Absolute path of the written MP4.
    """
    img = Path(image_path).resolve()
    aud = Path(audio_path).resolve()
    out = Path(output_path).resolve()

    for label, p in [("image", img), ("audio", aud)]:
        if not p.exists():
            raise FileNotFoundError(f"{label} file not found: {p}")

    out.parent.mkdir(parents=True, exist_ok=True)

    if duration_seconds is None:
        duration_seconds = probe_audio_duration(aud)

    adjusted_duration = duration_seconds / AUDIO_SPEED + 0.5
    total_frames = int(adjusted_duration * _FPS)
    logger.info("Assembling tweet video | img=%s | audio=%.2fs | adjusted=%.2fs | frames=%d",
                img.name, duration_seconds, adjusted_duration, total_frames)

    music = _pick_music_file()
    if music is None:
        logger.warning("No music files in assets/music/ — skipping background music")

    cmd = _build_cmd(img, aud, out, adjusted_duration, total_frames, music_path=music)
    logger.info("FFmpeg: %s", " ".join(cmd))
    _run_ffmpeg_shared(cmd)

    size_mb = out.stat().st_size / 1_048_576
    logger.info("Tweet video saved → %s (%.1f MB)", out, size_mb)
    return str(out)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _build_cmd(
    img: Path,
    audio: Path,
    output: Path,
    duration: float,
    total_frames: int,
    music_path: Path | None = None,
) -> list[str]:
    # zoompan: slow zoom in from 1.0x to ~1.05x over the full video duration
    # d= must equal total_frames so the filter covers the whole clip
    zoom_expr = "z='1+0.0005*on'"
    zoom_x    = "x='iw/2-(iw/zoom/2)'"
    zoom_y    = "y='ih/2-(ih/zoom/2)'"
    zoompan   = f"zoompan={zoom_expr}:d={total_frames}:{zoom_x}:{zoom_y}:s=1080x1920:fps={_FPS}"

    if music_path is not None:
        fc = (
            f"[0:v]{zoompan}[vout];"
            f"[1:a]atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}[narr];"
            f"[2:a]volume=0.08[mus];"
            f"[narr][mus]amix=inputs=2:duration=first[aout]"
        )
        return [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(img),                # input 0: static image
            "-i", str(audio),              # input 1: narration audio
            "-stream_loop", "-1",          # loop music indefinitely
            "-i", str(music_path),         # input 2: background music
            "-t", str(duration),
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
        af = f"atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}"
        return [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(img),
            "-i", str(audio),
            "-t", str(duration),
            "-vf", zoompan,
            "-af", af,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", _VIDEO_CODEC,
            "-preset", _PRESET,
            "-crf", _CRF,
            "-c:a", _AUDIO_CODEC,
            "-b:a", _AUDIO_BR,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ]


