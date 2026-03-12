"""
formats/tweets/renderer.py — Render a realistic X (Twitter) screenshot as 1080×1920 PNG.

Uses an HTML template rendered via Playwright for pixel-perfect output matching
X's actual dark mode UI — proper fonts, SVG icons, and CSS spacing.

Public API:
    render_tweet(tweet, output_path) -> str
"""

import html
import io
import logging
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image

import config

logger = logging.getLogger(__name__)

CANVAS_W, CANVAS_H = 1080, 1920

_TEMPLATE_PATH = Path(__file__).parent / "tweet_template.html"

AVATAR_PALETTE = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#FF8C69",
]

_VERIFIED_SVG = '<svg class="verified-badge" viewBox="0 0 22 22" width="18" height="18"><path d="M20.396 11c-.018-.646-.215-1.275-.57-1.816-.354-.54-.852-.972-1.438-1.246.223-.607.27-1.264.14-1.897-.131-.634-.437-1.218-.882-1.687-.47-.445-1.053-.75-1.687-.882-.633-.13-1.29-.083-1.897.14-.273-.587-.704-1.086-1.245-1.44S11.647 1.62 11 1.604c-.646.017-1.273.213-1.813.568s-.969.855-1.24 1.44c-.608-.223-1.267-.272-1.902-.14-.635.13-1.22.436-1.69.882-.445.47-.749 1.055-.878 1.69-.13.633-.08 1.29.144 1.896-.587.274-1.087.705-1.443 1.245-.356.54-.555 1.17-.574 1.817.02.647.218 1.276.574 1.817.356.54.856.972 1.443 1.245-.224.607-.274 1.264-.144 1.897.13.634.433 1.218.877 1.688.47.443 1.054.747 1.687.878.633.132 1.29.084 1.897-.136.274.586.705 1.084 1.246 1.439.54.354 1.17.551 1.816.569.647-.016 1.276-.213 1.817-.567s.972-.854 1.245-1.44c.604.239 1.266.296 1.903.164.636-.132 1.22-.447 1.68-.907.46-.46.776-1.044.908-1.681.132-.637.075-1.299-.164-1.903.584-.274 1.083-.704 1.439-1.246.354-.54.551-1.17.569-1.816zM9.662 14.85l-3.429-3.428 1.293-1.302 2.072 2.072 4.4-4.794 1.347 1.246z" fill="#1d9bf0"/></svg>'

_NO_VERIFIED = ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_tweet(tweet: dict[str, Any], output_path: str) -> str:
    """Render a realistic X screenshot PNG using HTML + Playwright.

    Args:
        tweet: dict with display_name, username, tweet_text, likes, retweets.
        output_path: Destination path for the PNG.

    Returns:
        Absolute path of the saved PNG.
    """
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    template = _TEMPLATE_PATH.read_text()
    filled   = _fill_template(template, tweet)

    # Render HTML to PNG via Playwright
    raw_png = _render_html(filled)

    # Compose onto 1080x1920 black canvas
    _compose_on_canvas(raw_png, out)
    raw_png.unlink(missing_ok=True)

    logger.info("Rendered X screenshot → %s", out)
    return str(out)


# ---------------------------------------------------------------------------
# Template filling
# ---------------------------------------------------------------------------

def _fill_template(template: str, tweet: dict[str, Any]) -> str:
    """Replace placeholders in the HTML template with tweet data."""

    display_name = html.escape(tweet["display_name"])
    username     = html.escape(tweet["username"])

    # Tweet text: escape HTML, then colorize @mentions, #hashtags, URLs
    raw_text  = tweet.get("tweet_text", tweet.get("text", ""))
    text_html = _format_tweet_text(raw_text)

    # Verified badge
    verified = tweet.get("verified", True)
    badge    = _VERIFIED_SVG if verified else _NO_VERIFIED

    # Avatar
    avatar_url = tweet.get("profile_image_url")
    if avatar_url:
        avatar_url = avatar_url.replace("_normal", "_400x400")
        avatar_html = f'<img class="avatar" src="{html.escape(avatar_url)}" alt="">'
    else:
        color   = AVATAR_PALETTE[sum(ord(c) for c in username) % len(AVATAR_PALETTE)]
        initial = display_name[0].upper() if display_name else "?"
        avatar_html = f'<div class="avatar-placeholder" style="background:{color}">{initial}</div>'

    # Timestamp
    if tweet.get("created_at"):
        timestamp = tweet["created_at"]
    else:
        timestamp = _fake_timestamp()

    # Stats
    likes     = tweet.get("likes", 0)
    retweets  = tweet.get("retweets", 0)
    views     = tweet.get("views", _derive_views(likes))
    replies   = max(1, likes // random.randint(15, 40))
    bookmarks = max(1, likes // random.randint(4, 10))

    replacements = {
        "{{AVATAR}}":        avatar_html,
        "{{DISPLAY_NAME}}":  display_name,
        "{{VERIFIED_BADGE}}": badge,
        "{{USERNAME}}":      username,
        "{{TWEET_TEXT}}":    text_html,
        "{{TIMESTAMP}}":     timestamp,
        "{{VIEWS}}":         _fmt(views),
        "{{REPLIES}}":       _fmt(replies),
        "{{RETWEETS}}":      _fmt(retweets),
        "{{LIKES}}":         _fmt(likes),
        "{{BOOKMARKS}}":     _fmt(bookmarks),
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value))
    return result


def _format_tweet_text(text: str) -> str:
    """Escape HTML, convert newlines, and colorize mentions/hashtags/URLs."""
    text = html.escape(text, quote=False)
    # Colorize @mentions
    text = re.sub(r'(@\w+)', r'<span class="mention">\1</span>', text)
    # Colorize #hashtags
    text = re.sub(r'(#\w+)', r'<span class="hashtag">\1</span>', text)
    # Colorize URLs
    text = re.sub(r'(https?://\S+)', r'<span class="link">\1</span>', text)
    # Newlines to <br> (preserve \n)
    text = text.replace("\n", "\n")  # pre-wrap handles this
    return text


# ---------------------------------------------------------------------------
# Playwright rendering
# ---------------------------------------------------------------------------

def _render_html(html_content: str) -> Path:
    """Render HTML string to a temporary PNG file via Playwright."""
    from playwright.sync_api import sync_playwright

    tmp_html = Path(config.OUTPUT_DIR / "_tmp_tweet.html")
    tmp_html.parent.mkdir(parents=True, exist_ok=True)
    tmp_html.write_text(html_content, encoding="utf-8")
    tmp_png = tmp_html.with_suffix(".png")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 600, "height": 900},
            device_scale_factor=3,
            color_scheme="dark",
        )
        page.goto(f"file://{tmp_html.resolve()}", wait_until="networkidle")
        page.wait_for_timeout(500)

        # Screenshot just the tweet container
        container = page.query_selector(".tweet-container")
        if container:
            container.screenshot(path=str(tmp_png))
        else:
            page.screenshot(path=str(tmp_png), full_page=True)

        browser.close()

    tmp_html.unlink(missing_ok=True)
    return tmp_png


def _compose_on_canvas(src: Path, dst: Path) -> None:
    """Place the tweet screenshot centred-top on a 1080×1920 black canvas."""
    tweet_img = Image.open(src).convert("RGB")
    tw, th    = tweet_img.size

    # Scale to fit canvas width
    if tw != CANVAS_W:
        scale     = CANVAS_W / tw
        tw        = CANVAS_W
        th        = int(th * scale)
        tweet_img = tweet_img.resize((tw, th), Image.LANCZOS)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), "#000000")
    paste_x = (CANVAS_W - tw) // 2
    paste_y = 80  # slight top offset for status bar feel
    canvas.paste(tweet_img, (paste_x, paste_y))
    canvas.save(str(dst), "PNG")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _fmt(n: int) -> str:
    if n >= 1_000_000:
        v = n / 1_000_000
        return f"{v:.1f}M" if v < 10 else f"{round(v)}M"
    if n >= 1_000:
        v = n / 1_000
        return f"{v:.1f}K"
    return str(n)


def _derive_views(likes: int) -> int:
    return likes * random.randint(30, 80)


def _fake_timestamp() -> str:
    now  = datetime.now(timezone.utc)
    hour = now.hour % 12 or 12
    ampm = "AM" if now.hour < 12 else "PM"
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{hour}:{now.minute:02d} {ampm} · {months[now.month - 1]} {now.day}, {now.year}"
