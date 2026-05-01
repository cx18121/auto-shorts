"""
pipeline/tts.py — ElevenLabs TTS with word-level timestamps.

Public API:
    generate_tts(text, output_dir) -> dict
"""

import base64
import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

_ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
_TTS_CACHE_DIR = config.DATA_DIR / "tts_cache"


def _cache_key(voice_id: str, text: str) -> str:
    """Return a 16-char hex cache key for a (voice_id, text) pair."""
    return hashlib.sha256(f"{voice_id}:{text}".encode()).hexdigest()[:16]


def generate_tts(text: str, output_dir: str) -> dict[str, Any]:
    """Generate TTS audio and word-level timestamps, with local cache.

    Checks data/tts_cache/ for a prior result with the same voice + text.
    On a hit, copies cached files to output_dir without calling the API.
    On a miss, calls ElevenLabs, writes output_dir, and populates the cache.

    Args:
        text: The text to convert to speech.
        output_dir: Directory where 'narration.mp3' and 'timestamps.json'
            will be saved (created if it doesn't exist).

    Returns:
        {
            "audio_path": str,
            "timestamps_path": str,
            "duration_seconds": float,
        }
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    key = _cache_key(config.ELEVENLABS_VOICE_ID, text)
    cache_dir = _TTS_CACHE_DIR / key
    cached_audio = cache_dir / "narration.mp3"
    cached_timestamps = cache_dir / "timestamps.json"

    if cached_audio.exists() and cached_timestamps.exists():
        logger.info("TTS cache hit (key=%s) — skipping ElevenLabs API call", key)
        audio_path = out / "narration.mp3"
        timestamps_path = out / "timestamps.json"
        shutil.copy2(cached_audio, audio_path)
        shutil.copy2(cached_timestamps, timestamps_path)
        word_timestamps = json.loads(timestamps_path.read_text())
        duration = word_timestamps[-1]["end_ms"] / 1000.0 if word_timestamps else 0.0
        return {
            "audio_path": str(audio_path),
            "timestamps_path": str(timestamps_path),
            "duration_seconds": duration,
        }

    logger.info("Calling ElevenLabs TTS API (voice=%s) for: %.60r…", config.ELEVENLABS_VOICE_ID, text)

    response_data = _call_with_retry(text)

    # Decode and save audio
    audio_bytes = base64.b64decode(response_data["audio_base64"])
    audio_path = out / "narration.mp3"
    audio_path.write_bytes(audio_bytes)
    logger.info("Saved audio → %s (%d bytes)", audio_path, len(audio_bytes))

    # Convert character-level alignment to word-level timestamps
    alignment = response_data.get("alignment") or response_data.get("normalized_alignment", {})
    word_timestamps = _characters_to_words(alignment)

    timestamps_path = out / "timestamps.json"
    timestamps_path.write_text(json.dumps(word_timestamps, indent=2))
    logger.info("Saved %d word timestamps → %s", len(word_timestamps), timestamps_path)

    duration = word_timestamps[-1]["end_ms"] / 1000.0 if word_timestamps else 0.0
    logger.info("Audio duration: %.2fs", duration)

    # Populate cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_path, cached_audio)
    shutil.copy2(timestamps_path, cached_timestamps)
    logger.debug("TTS cached → %s", cache_dir)

    return {
        "audio_path": str(audio_path),
        "timestamps_path": str(timestamps_path),
        "duration_seconds": duration,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_with_retry(text: str, max_attempts: int = 3) -> dict[str, Any]:
    """POST to /with-timestamps with exponential backoff."""
    url = f"{_ELEVENLABS_BASE}/text-to-speech/{config.ELEVENLABS_VOICE_ID}/with-timestamps"
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("ElevenLabs API attempt %d/%d", attempt, max_attempts)
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < max_attempts:
                wait = 2 ** attempt
                logger.info("Retrying in %ds…", wait)
                time.sleep(wait)

    raise RuntimeError(
        f"ElevenLabs API failed after {max_attempts} attempts"
    ) from last_exc


def _characters_to_words(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate character-level ElevenLabs alignment into word-level timestamps.

    ElevenLabs returns character start/end times. We group consecutive
    non-space characters into words and record the first char's start time
    and the last char's end time for each word.

    Returns:
        List of {"word": str, "start_ms": int, "end_ms": int}.
    """
    characters: list[str] = alignment.get("characters", [])
    starts: list[float] = alignment.get("character_start_times_seconds", [])
    ends: list[float] = alignment.get("character_end_times_seconds", [])

    words: list[dict[str, Any]] = []
    buf: list[str] = []
    word_start: float | None = None
    word_end: float | None = None

    for char, start, end in zip(characters, starts, ends):
        if char in (" ", "\n", "\t"):
            if buf:
                words.append({
                    "word": "".join(buf),
                    "start_ms": round(word_start * 1000),
                    "end_ms": round(word_end * 1000),
                })
                buf = []
                word_start = None
                word_end = None
        else:
            if word_start is None:
                word_start = start
            word_end = end
            buf.append(char)

    # Flush any trailing word
    if buf:
        words.append({
            "word": "".join(buf),
            "start_ms": round(word_start * 1000),
            "end_ms": round(word_end * 1000),
        })

    return words
