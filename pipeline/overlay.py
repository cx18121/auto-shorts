"""
pipeline/overlay.py — Convert word-level timestamps into an ASS subtitle file.

Public API:
    generate_ass(timestamps_path, output_path) -> str
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phrase grouping parameters
# ---------------------------------------------------------------------------

PHRASE_MIN_WORDS = 1          # don't break on soft punctuation below this
PHRASE_MAX_WORDS = 2          # hard cap; flush regardless
PHRASE_MAX_DURATION_MS = 1500 # also flush if a phrase would span > 1.5 s

# Sentence-ending punctuation → always flush (even with fewer than MIN words)
_HARD_BREAK = frozenset(".!?")
# Clause-ending punctuation → flush only when we have enough words
_SOFT_BREAK = frozenset(",;:")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_ass(
    timestamps_path: str,
    output_path: str,
    speed_factor: float = 1.0,
) -> str:
    """Build an ASS subtitle file from word-level timestamps.

    Reads the timestamps JSON produced by pipeline.tts, groups the words
    into subtitle phrases, and writes a styled .ass file ready for FFmpeg.

    Args:
        timestamps_path: Path to timestamps JSON (list of
            {"word", "start_ms", "end_ms"} objects).
        output_path: Destination path for the .ass file.
        speed_factor: Audio playback speed multiplier (e.g. 1.15 for 15% faster).
            Subtitle timestamps are scaled to stay in sync with sped-up audio.

    Returns:
        Absolute path of the written .ass file.
    """
    words: list[dict[str, Any]] = json.loads(Path(timestamps_path).read_text())
    logger.info("Loaded %d words from %s", len(words), timestamps_path)

    # Scale timestamps if audio is sped up
    if speed_factor != 1.0:
        for w in words:
            w["start_ms"] = round(w["start_ms"] / speed_factor)
            w["end_ms"] = round(w["end_ms"] / speed_factor)

    phrases = _group_into_phrases(words)
    logger.info(
        "Grouped into %d phrases (avg %.1f words each)",
        len(phrases),
        sum(p["word_count"] for p in phrases) / max(len(phrases), 1),
    )

    ass_text = _build_ass(phrases)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ass_text, encoding="utf-8")
    logger.info("Saved ASS subtitle file → %s", out)

    return str(out)


# ---------------------------------------------------------------------------
# Grouping logic
# ---------------------------------------------------------------------------

def _group_into_phrases(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Segment words into subtitle phrases with natural break points.

    Priority order for flushing a phrase:
      1. Hard punctuation (. ! ?) — always flush, even if short
      2. Soft punctuation (, ; :) — flush when >= PHRASE_MIN_WORDS
      3. Reached PHRASE_MAX_WORDS — forced flush
      4. Phrase duration >= PHRASE_MAX_DURATION_MS — forced flush
    """
    phrases: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []

    for word in words:
        buf.append(word)

        # Strip trailing quotes/parens before checking punctuation
        clean_word = word["word"].rstrip("\"')")
        tail = clean_word[-1] if clean_word else ""

        duration_ms = buf[-1]["end_ms"] - buf[0]["start_ms"]

        is_hard = tail in _HARD_BREAK
        is_soft = tail in _SOFT_BREAK and len(buf) >= PHRASE_MIN_WORDS
        is_forced = len(buf) >= PHRASE_MAX_WORDS or duration_ms >= PHRASE_MAX_DURATION_MS

        if is_hard or is_soft or is_forced:
            phrases.append(_make_phrase(buf))
            buf = []

    if buf:
        phrases.append(_make_phrase(buf))

    return phrases


def _make_phrase(words: list[dict[str, Any]]) -> dict[str, Any]:
    raw = " ".join(w["word"] for w in words)
    # All caps, strip punctuation for clean subtitle display
    display = re.sub(r"[^\w\s]", "", raw).upper().strip()
    return {
        "text": display,
        "start_ms": words[0]["start_ms"],
        "end_ms": words[-1]["end_ms"],
        "word_count": len(words),
    }


# ---------------------------------------------------------------------------
# ASS file construction
# ---------------------------------------------------------------------------

# ASS colour format: &HAABBGGRR&
#   AA = alpha  (0x00 = fully opaque, 0xFF = fully transparent)
#   BB GG RR = blue, green, red
_COLOUR_WHITE  = "&H00FFFFFF&"  # opaque white text
_COLOUR_BLACK  = "&H00000000&"  # opaque black outline
_COLOUR_SHADOW = "&H00003399&"  # deep orange-red shadow (gives warm bubbly pop)

_ASS_SCRIPT_INFO = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1
ScaledBorderAndShadow: yes

"""

# Style field order:
#   Name, Fontname, Fontsize,
#   PrimaryColour, SecondaryColour, OutlineColour, BackColour,
#   Bold, Italic, Underline, StrikeOut,
#   ScaleX, ScaleY, Spacing, Angle,
#   BorderStyle, Outline, Shadow,
#   Alignment, MarginL, MarginR, MarginV, Encoding
#
# BorderStyle 1 = outline + shadow.
# Komika Axis is a bold comic-style font — punchy subtitle look.
# Outline=6 gives a fat black border that puffs the letters out.
# Shadow=2 with a coloured BackColour adds a warm offset shadow for depth.
# Alignment 2 = numpad bottom-centre — places subtitles in the lower portion of the 1080×1920 canvas.
_ASS_STYLES = (
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    f"Style: Default,Komika Axis,120,"
    f"{_COLOUR_WHITE},{_COLOUR_BLACK},{_COLOUR_BLACK},{_COLOUR_SHADOW},"
    f"-1,0,0,0,"        # Bold=-1 (on), no italic/underline/strikeout
    f"100,100,1,0,"     # ScaleX, ScaleY, Spacing=1 (slight letter spacing), Angle
    f"1,6,2,"           # BorderStyle=1, Outline=6px (thick border), Shadow=2px
    f"2,40,40,768,1\n"  # Alignment=2 (bottom-centre), MarginL/R=40, MarginV=768 (~40% from bottom), Encoding=1
    "\n"
)

_ASS_EVENTS_HEADER = (
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


def _build_ass(phrases: list[dict[str, Any]]) -> str:
    lines = [_ASS_SCRIPT_INFO, _ASS_STYLES, _ASS_EVENTS_HEADER]
    for phrase in phrases:
        start = _ms_to_ass(phrase["start_ms"])
        end   = _ms_to_ass(phrase["end_ms"])
        text  = phrase["text"]
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")
    return "".join(lines)


def _ms_to_ass(ms: int) -> str:
    """Convert milliseconds to ASS timestamp H:MM:SS.cc."""
    total_cs, rem = divmod(ms, 10)   # centiseconds
    cs            = total_cs % 100
    total_s       = total_cs // 100
    s             = total_s  % 60
    total_m       = total_s  // 60
    m             = total_m  % 60
    h             = total_m  // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
