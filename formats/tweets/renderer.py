"""
formats/tweets/renderer.py — Render a realistic X (Twitter) screenshot as 1080×1920 PNG.

Mimics X's "Lights Out" dark mode: black background, full-width tweet detail
view with nav bar, avatar/name row, tweet text, timestamp+views line, and
action bar with counts.

Public API:
    render_tweet(tweet, output_path) -> str
"""

import io
import logging
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# X colour palette — "Lights Out" dark mode
# ---------------------------------------------------------------------------
BG        = "#000000"
TEXT      = "#E7E9EA"
SECONDARY = "#71767B"
BORDER    = "#2F3336"
BLUE      = "#1D9BF0"

CANVAS_W, CANVAS_H = 1080, 1920

PAD_X       = 72    # horizontal content padding
AVATAR_SIZE = 108   # pixels
TOP_BAR_H   = 108

AVATAR_PALETTE = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#FF8C69",
]

_FONTS_DIR = config.ASSETS_DIR / "fonts"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_tweet(tweet: dict[str, Any], output_path: str) -> str:
    """Render a realistic X screenshot PNG.

    Args:
        tweet: dict with display_name, username, tweet_text, likes, retweets.
        output_path: Destination path for the PNG.

    Returns:
        Absolute path of the saved PNG.
    """
    fonts = _load_fonts()
    img   = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw  = ImageDraw.Draw(img)

    text_width = CANVAS_W - PAD_X * 2

    # Flat list of lines; "" = blank line between paragraphs
    raw_lines  = _split_paragraphs(tweet["tweet_text"])
    # Word-wrap each non-blank line; blank lines stay as [""]
    wrapped_lines: list[list[str]] = [
        _wrap(l, fonts["tweet_text"], text_width) if l else [""]
        for l in raw_lines
    ]

    line_h = _line_height(draw, fonts["tweet_text"])
    text_h = sum(line_h for block in wrapped_lines for _ in block)

    # Section heights
    h_topbar    = TOP_BAR_H
    h_profile   = AVATAR_SIZE + 28
    h_gap1      = 32            # gap between profile and text
    h_text      = text_h + 40
    h_timestamp = 64
    h_divider   = 1
    h_actions   = 104
    total_h = (h_topbar + h_profile + h_gap1 + h_text +
               h_timestamp + h_divider + h_actions + h_divider)

    # Start near the top (mimicking a real phone screenshot, not vertically centred)
    start_y = 80   # space for phone status bar
    y = start_y

    # -----------------------------------------------------------------------
    # 1. Top navigation bar: ← Post ... ø
    # -----------------------------------------------------------------------
    y = _draw_topbar(draw, fonts, y, h_topbar)

    # -----------------------------------------------------------------------
    # 2. Profile row: avatar | name + badge / @handle ... ø
    # -----------------------------------------------------------------------
    initial      = tweet["display_name"][0].upper() if tweet["display_name"] else "?"
    avatar_color = AVATAR_PALETTE[sum(ord(c) for c in tweet["username"]) % len(AVATAR_PALETTE)]
    verified     = tweet.get("verified", True)
    avatar_img   = _fetch_avatar(tweet.get("profile_image_url"), AVATAR_SIZE)
    y = _draw_profile_row(draw, fonts, y, tweet, initial, avatar_color, verified, avatar_img)

    # -----------------------------------------------------------------------
    # 3. Tweet text (single \n = line break, \n\n = blank line)
    # -----------------------------------------------------------------------
    y += h_gap1
    for block in wrapped_lines:
        for line in block:
            if line:
                _draw_rich_line(draw, PAD_X, y, line, fonts["tweet_text"], TEXT, BLUE)
            y += line_h
    y += 40

    # -----------------------------------------------------------------------
    # 4. Timestamp + views
    # -----------------------------------------------------------------------
    views = tweet.get("views", _derive_views(tweet.get("likes", 0)))
    # Use real timestamp if provided, otherwise generate a fake one
    if tweet.get("created_at"):
        ts_prefix = tweet["created_at"] + " · "
    else:
        ts_prefix, _ = _fake_timestamp(views)
    views_str = _fmt(views)
    draw.text((PAD_X, y), ts_prefix, font=fonts["secondary"], fill=SECONDARY)
    prefix_w = int(draw.textlength(ts_prefix, font=fonts["secondary"]))
    draw.text((PAD_X + prefix_w, y), views_str, font=fonts["secondary_bold"], fill=TEXT)
    views_str_w = int(draw.textlength(views_str, font=fonts["secondary_bold"]))
    draw.text((PAD_X + prefix_w + views_str_w, y), " Views",
              font=fonts["secondary"], fill=SECONDARY)
    y += h_timestamp

    # -----------------------------------------------------------------------
    # 5. Divider + action bar
    # -----------------------------------------------------------------------
    _hline(draw, y)
    y += h_divider

    retweets  = tweet.get("retweets", 0)
    likes     = tweet.get("likes", 0)
    replies   = max(1, likes // random.randint(15, 40))
    bookmarks = max(1, likes // random.randint(4, 10))
    _draw_action_bar(draw, fonts, y, h_actions, replies, retweets, likes, bookmarks)

    y += h_actions
    _hline(draw, y)

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out), "PNG")
    logger.info("Rendered X screenshot → %s", out)
    return str(out)


# ---------------------------------------------------------------------------
# Section drawing helpers
# ---------------------------------------------------------------------------

def _draw_topbar(draw: ImageDraw.ImageDraw, fonts: dict, y: int, h: int) -> int:
    """← Post     [ø]"""
    mid_y = y + h // 2

    # ← back arrow
    ax = PAD_X
    aw = 26
    arr_y = mid_y
    draw.line([(ax + aw, arr_y - 16), (ax, arr_y), (ax + aw, arr_y + 16)], fill=TEXT, width=4)

    # "Post" label — bold, centred
    label = "Post"
    lw    = int(draw.textlength(label, font=fonts["topbar"]))
    draw.text(((CANVAS_W - lw) // 2, mid_y - 22), label, font=fonts["topbar"], fill=TEXT)

    # ø icon (circle with diagonal line) on right
    icon_r = 20
    icon_x = CANVAS_W - PAD_X - icon_r
    icon_y = mid_y
    _draw_circle_slash(draw, icon_x, icon_y, icon_r, SECONDARY, width=3)

    return y + h


def _draw_circle_slash(draw: ImageDraw.ImageDraw,
                        cx: int, cy: int, r: int, color: str, width: int = 3) -> None:
    """Draw a ø-style circle with a diagonal line (X Spaces icon)."""
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=0, end=360, fill=color, width=width)
    angle_offset = int(r * 0.7)
    draw.line([(cx + angle_offset, cy - angle_offset),
               (cx - angle_offset, cy + angle_offset)],
              fill=color, width=width)


def _draw_profile_row(
    draw: ImageDraw.ImageDraw, fonts: dict, y: int,
    tweet: dict[str, Any], initial: str, avatar_color: str, verified: bool,
    avatar_img: "Image.Image | None" = None,
) -> int:
    """Avatar | Name + badge\n@handle       [ø ···]"""
    # Avatar circle — real image if available, coloured initial fallback
    if avatar_img:
        # Paste the pre-cropped circular avatar onto the canvas
        # Use the alpha channel as a mask for antialiased edges
        draw._image.paste(avatar_img, (PAD_X, y), avatar_img)
    else:
        draw.ellipse([PAD_X, y, PAD_X + AVATAR_SIZE, y + AVATAR_SIZE], fill=avatar_color)
        bbox = draw.textbbox((0, 0), initial, font=fonts["avatar_initial"])
        iw = bbox[2] - bbox[0]
        ih = bbox[3] - bbox[1]
        draw.text(
            (PAD_X + (AVATAR_SIZE - iw) // 2, y + (AVATAR_SIZE - ih) // 2 - 2),
            initial, font=fonts["avatar_initial"], fill="#ffffff",
        )

    # Name + verified badge
    name_x = PAD_X + AVATAR_SIZE + 24
    name_y = y + 8
    draw.text((name_x, name_y), tweet["display_name"], font=fonts["name"], fill=TEXT)
    name_w = int(draw.textlength(tweet["display_name"], font=fonts["name"]))

    if verified:
        badge_size = 34
        bx = name_x + name_w + 8
        by = name_y + 3
        _draw_verified(draw, bx, by, badge_size)

    # @handle
    handle_y = name_y + 46
    draw.text((name_x, handle_y), f"@{tweet['username']}", font=fonts["handle"], fill=SECONDARY)

    # Right side: ø icon + three dots
    right_mid_y = y + AVATAR_SIZE // 2
    icon_r = 18
    icon_cx = CANVAS_W - PAD_X - icon_r
    _draw_circle_slash(draw, icon_cx, right_mid_y, icon_r, SECONDARY, width=3)

    # three dots (···)
    dots_x = icon_cx - icon_r * 2 - 56
    for i in range(3):
        dx = dots_x + i * 16
        draw.ellipse([dx, right_mid_y - 4, dx + 8, right_mid_y + 4], fill=SECONDARY)

    return y + AVATAR_SIZE + 8


def _draw_verified(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """Blue circle with white checkmark."""
    draw.ellipse([x, y, x + size, y + size], fill=BLUE)
    cx, cy = x + size // 2, y + size // 2
    r = size * 0.28
    draw.line(
        [(int(cx - r * 1.1), int(cy + r * 0.1)), (int(cx - r * 0.1), int(cy + r * 1.0))],
        fill="white", width=max(2, size // 12),
    )
    draw.line(
        [(int(cx - r * 0.1), int(cy + r * 1.0)), (int(cx + r * 1.1), int(cy - r * 0.8))],
        fill="white", width=max(2, size // 12),
    )


def _draw_action_bar(
    draw: ImageDraw.ImageDraw, fonts: dict,
    y: int, h: int,
    replies: int, retweets: int, likes: int, bookmarks: int,
) -> None:
    """Five action items evenly spread: reply+count  repost+count  like+count  bookmark+count  share"""
    mid_y   = y + h // 2 - 8
    icon_sz = 34
    gap     = 14    # gap between icon and its count label

    items = [
        (_draw_icon_reply,    _fmt(replies)),
        (_draw_icon_repost,   _fmt(retweets)),
        (_draw_icon_like,     _fmt(likes)),
        (_draw_icon_bookmark, _fmt(bookmarks)),
        (_draw_icon_share,    None),
    ]

    # Evenly distribute across full width
    n     = len(items)
    slot  = CANVAS_W // n
    for i, (draw_fn, count) in enumerate(items):
        cx = slot * i + slot // 2
        draw_fn(draw, cx, mid_y, icon_sz)
        if count:
            count_x = cx + icon_sz // 2 + gap
            count_y = mid_y - 14
            draw.text((count_x, count_y), count, font=fonts["action_count"], fill=SECONDARY)


# ---------------------------------------------------------------------------
# Icon drawing
# ---------------------------------------------------------------------------

def _draw_icon_reply(draw: ImageDraw.ImageDraw, cx: int, cy: int, sz: int) -> None:
    r = sz // 2
    # Speech bubble arc
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=200, end=80, fill=SECONDARY, width=3)
    # Tail pointing bottom-left
    draw.line([(cx - r + 2, cy + r - 4), (cx - r - 6, cy + r + 8), (cx - r + 10, cy + r - 2)],
              fill=SECONDARY, width=3)


def _draw_icon_repost(draw: ImageDraw.ImageDraw, cx: int, cy: int, sz: int) -> None:
    r = sz // 2 - 2
    # Rounded rectangle outline
    rr = [cx - r, cy - r // 2, cx + r, cy + r // 2]
    draw.rounded_rectangle(rr, radius=6, outline=SECONDARY, width=3)
    # Top-right arrowhead
    draw.line([(cx + r - 10, cy - r // 2 - 9), (cx + r, cy - r // 2), (cx + r - 10, cy - r // 2 + 9)],
              fill=SECONDARY, width=3)
    # Bottom-left arrowhead
    draw.line([(cx - r + 10, cy + r // 2 + 9), (cx - r, cy + r // 2), (cx - r + 10, cy + r // 2 - 9)],
              fill=SECONDARY, width=3)


def _draw_icon_like(draw: ImageDraw.ImageDraw, cx: int, cy: int, sz: int) -> None:
    r = sz // 2
    offset = r // 2
    # Two arcs forming top of heart
    draw.arc([cx - r, cy - offset, cx, cy + r], start=0, end=180, fill=SECONDARY, width=3)
    draw.arc([cx, cy - offset, cx + r, cy + r], start=0, end=180, fill=SECONDARY, width=3)
    # Bottom V lines
    draw.line([(cx - r, cy + offset), (cx, cy + r + offset // 2)], fill=SECONDARY, width=3)
    draw.line([(cx + r, cy + offset), (cx, cy + r + offset // 2)], fill=SECONDARY, width=3)


def _draw_icon_bookmark(draw: ImageDraw.ImageDraw, cx: int, cy: int, sz: int) -> None:
    r = sz // 2
    pts = [
        (cx - r // 2, cy - r), (cx + r // 2, cy - r),
        (cx + r // 2, cy + r), (cx, cy + r // 3),
        (cx - r // 2, cy + r),
    ]
    draw.polygon(pts, outline=SECONDARY, width=3)


def _draw_icon_share(draw: ImageDraw.ImageDraw, cx: int, cy: int, sz: int) -> None:
    r = sz // 2
    # Upward arrow
    draw.line([(cx, cy + r - 4), (cx, cy - r + 8)], fill=SECONDARY, width=3)
    draw.line([(cx - r // 2, cy - r // 3), (cx, cy - r + 8), (cx + r // 2, cy - r // 3)],
              fill=SECONDARY, width=3)
    # Base shelf
    draw.line([(cx - r, cy + r - 4), (cx - r, cy + r // 2),
               (cx + r, cy + r // 2), (cx + r, cy + r - 4)], fill=SECONDARY, width=3)


# ---------------------------------------------------------------------------
# Avatar + rich text helpers
# ---------------------------------------------------------------------------

def _fetch_avatar(url: str | None, size: int) -> "Image.Image | None":
    """Download a profile image URL and return a circular-cropped RGBA image."""
    if not url:
        return None
    try:
        # X serves _normal (48px) — request _400x400 for higher res
        url = url.replace("_normal", "_400x400")
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)

        # Circular mask
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        img.putalpha(mask)
        return img
    except Exception as e:
        logger.warning("Failed to fetch avatar from %s: %s", url, e)
        return None


def _draw_rich_line(
    draw: ImageDraw.ImageDraw,
    x: int, y: int,
    line: str,
    font: ImageFont.FreeTypeFont,
    text_color: str,
    link_color: str,
) -> None:
    """Draw a line of text, colouring @mentions, #hashtags, and URLs in link_color."""
    # Tokenise: split into (token, is_link) pairs
    token_re = re.compile(r'(@\w+|#\w+|https?://\S+)')
    parts = token_re.split(line)
    cx = x
    for part in parts:
        if not part:
            continue
        is_link = bool(token_re.fullmatch(part))
        color = link_color if is_link else text_color
        draw.text((cx, y), part, font=font, fill=color)
        cx += int(draw.textlength(part, font=font))


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _hline(draw: ImageDraw.ImageDraw, y: int) -> None:
    draw.rectangle([0, y, CANVAS_W, y + 1], fill=BORDER)


def _split_paragraphs(text: str) -> list[str]:
    """Return a flat list of lines, with '' representing a blank line between paragraphs.

    - \\n\\n (or literal r'\\n\\n') → blank line separator (empty string in list)
    - \\n (or literal r'\\n')       → hard line break (separate entry in list)
    """
    text = text.replace("\\n", "\n")
    lines: list[str] = []
    for para in text.split("\n\n"):
        for line in para.split("\n"):
            lines.append(line.strip())
        lines.append("")   # blank line between paragraphs
    # Remove trailing blank
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    tmp   = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[str] = []
    cur   = ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if tmp.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def _line_height(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> int:
    _, _, _, h = draw.textbbox((0, 0), "Ag", font=font)
    return h + 12


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M" if v < 10 else f"{round(v)}M"
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.1f}K" if v < 10 else f"{round(v)}K"
    return str(n)


def _derive_views(likes: int) -> int:
    """Estimate a realistic view count from likes (typically 30-80x likes)."""
    multiplier = random.randint(30, 80)
    return likes * multiplier


def _fake_timestamp(views: int) -> tuple[str, str]:
    """Return (prefix_string, views_count_string) for the timestamp line."""
    now    = datetime.now(timezone.utc)
    hour   = now.hour % 12 or 12
    mins   = now.minute
    ampm   = "AM" if now.hour < 12 else "PM"
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    prefix = f"{hour}:{mins:02d} {ampm} · {months[now.month - 1]} {now.day}, {now.year} · "
    return prefix, _fmt(views)


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_fonts() -> dict[str, ImageFont.FreeTypeFont]:
    def f(name: str, size: int) -> ImageFont.FreeTypeFont:
        p = _FONTS_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
        logger.warning("Font not found: %s", p)
        return ImageFont.load_default()

    return {
        "topbar":         f("Nunito-Bold.ttf",       40),
        "name":           f("Nunito-Bold.ttf",        38),
        "handle":         f("Nunito-Regular.ttf",     32),
        "avatar_initial": f("Nunito-ExtraBold.ttf",   48),
        "tweet_text":     f("Nunito-Regular.ttf",     44),
        "secondary":      f("Nunito-Regular.ttf",     29),
        "secondary_bold": f("Nunito-Bold.ttf",        29),
        "action_count":   f("Nunito-Regular.ttf",     28),
    }
