"""
pipeline/overlay.py — Convert word-level timestamps into an ASS subtitle file.

Each caption block shows BLOCK_SIZE words across two lines (LINE_SIZE words per
line).  One Dialogue event is emitted per word; the active word is highlighted
yellow while the rest of the block stays white.

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
# Block / caption parameters
# ---------------------------------------------------------------------------

BLOCK_SIZE = 4   # total words per caption block  (2 lines × 2)
LINE_SIZE  = 2   # words per line within the block

# Sentence-ending punctuation → always flush early
_HARD_BREAK = frozenset(".!?")
# Clause-ending punctuation → flush only when block is at least half full
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

    Each caption block spans up to BLOCK_SIZE words displayed on two lines.
    The currently spoken word is highlighted yellow; the rest are white.

    Args:
        timestamps_path: Path to timestamps JSON (list of
            {"word", "start_ms", "end_ms"} objects).
        output_path: Destination path for the .ass file.
        speed_factor: Audio playback speed multiplier (e.g. 1.3 for 30% faster).
            Subtitle timestamps are scaled to stay in sync with sped-up audio.

    Returns:
        Absolute path of the written .ass file.
    """
    words: list[dict[str, Any]] = json.loads(Path(timestamps_path).read_text())
    logger.info("Loaded %d words from %s", len(words), timestamps_path)

    if speed_factor != 1.0:
        for w in words:
            w["start_ms"] = round(w["start_ms"] / speed_factor)
            w["end_ms"]   = round(w["end_ms"]   / speed_factor)

    blocks = _group_into_blocks(words)
    logger.info(
        "Grouped into %d blocks (avg %.1f words each)",
        len(blocks),
        sum(len(b) for b in blocks) / max(len(blocks), 1),
    )

    ass_text = _build_ass(blocks)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ass_text, encoding="utf-8")
    logger.info("Saved ASS subtitle file → %s", out)

    return str(out)


# ---------------------------------------------------------------------------
# Grouping logic
# ---------------------------------------------------------------------------

def _group_into_blocks(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Segment words into caption blocks of up to BLOCK_SIZE words.

    Blocks flush early on sentence-ending punctuation (.!?) so captions
    never straddle sentence boundaries.  Clause punctuation flushes when
    the block is at least half full.
    """
    blocks: list[list[dict[str, Any]]] = []
    buf: list[dict[str, Any]] = []

    for word in words:
        buf.append(word)

        clean = word["word"].rstrip("\"')")
        tail  = clean[-1] if clean else ""

        is_hard = tail in _HARD_BREAK
        is_soft = tail in _SOFT_BREAK and len(buf) >= BLOCK_SIZE // 2
        is_full = len(buf) >= BLOCK_SIZE

        if is_hard or is_soft or is_full:
            blocks.append(buf)
            buf = []

    if buf:
        blocks.append(buf)

    return blocks


def _clean_word(raw: str) -> str:
    """Uppercase and strip punctuation for clean subtitle display."""
    cleaned = re.sub(r"[\u2013\u2014\-]+", " ", raw)
    return re.sub(r"[?.!\-\u2013\u2014:]", "", cleaned).upper().strip()


# ---------------------------------------------------------------------------
# ASS file construction
# ---------------------------------------------------------------------------

# ASS colour format: &HAABBGGRR&  (AA=alpha 00=opaque, then BGR)
_COLOUR_WHITE  = "&H00FFFFFF&"  # white  — inactive words
_COLOUR_YELLOW = "&H0000FFFF&"  # yellow — active (highlighted) word
_COLOUR_BLACK  = "&H00000000&"  # black  — outline
_COLOUR_SHADOW = "&H00003399&"  # warm orange-red shadow

_ASS_SCRIPT_INFO = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1
ScaledBorderAndShadow: yes

"""

# Fontsize reduced from 150→110 to fit 3 words per line comfortably.
# Outline reduced from 18→12 to match the smaller font.
_ASS_STYLES = (
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    f"Style: Default,Komika Axis,110,"
    f"{_COLOUR_WHITE},{_COLOUR_BLACK},{_COLOUR_BLACK},{_COLOUR_SHADOW},"
    f"-1,0,0,0,"
    f"100,100,1,0,"
    f"1,12,2,"
    f"2,40,40,768,1\n"
    "\n"
)

_ASS_EVENTS_HEADER = (
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


def _build_ass(blocks: list[list[dict[str, Any]]]) -> str:
    lines = [_ASS_SCRIPT_INFO, _ASS_STYLES, _ASS_EVENTS_HEADER]

    for block in blocks:
        display = [_clean_word(w["word"]) for w in block]

        for i, word in enumerate(block):
            start_ms = word["start_ms"]
            # Hold until the next word in the block begins; last word uses its own end
            end_ms = block[i + 1]["start_ms"] if i + 1 < len(block) else word["end_ms"]

            # Guard against zero-length or inverted events
            if end_ms <= start_ms:
                end_ms = start_ms + 50

            text  = _format_block(display, highlight_idx=i)
            start = _ms_to_ass(start_ms)
            end   = _ms_to_ass(end_ms)
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")

    return "".join(lines)


def _format_block(words: list[str], highlight_idx: int) -> str:
    """Render a block as two subtitle lines with the active word coloured yellow.

    Line 1: words[0 : LINE_SIZE]
    Line 2: words[LINE_SIZE : BLOCK_SIZE]  (empty if block has ≤ LINE_SIZE words)
    """
    parts = []
    for i, word in enumerate(words):
        if i == highlight_idx:
            parts.append(f"{{\\c{_COLOUR_YELLOW}}}{word}{{\\c{_COLOUR_WHITE}}}")
        else:
            parts.append(word)

    line1 = " ".join(parts[:LINE_SIZE])
    line2 = " ".join(parts[LINE_SIZE:])

    return f"{line1}\\N{line2}" if line2 else line1


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _ms_to_ass(ms: int) -> str:
    """Convert milliseconds to ASS timestamp H:MM:SS.cc."""
    total_cs = ms // 10
    cs       = total_cs % 100
    total_s  = total_cs // 100
    s        = total_s  % 60
    total_m  = total_s  // 60
    m        = total_m  % 60
    h        = total_m  // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
