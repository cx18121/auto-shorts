"""
formats/tweets/screenshotter.py — Screenshot a real X post via Playwright.

Opens the tweet URL in a headless Chromium browser at iPhone 13 viewport,
waits for the tweet article to render, and saves a cropped 1080×1920 PNG
(the tweet card centred on a black background, matching Shorts aspect ratio).

Public API:
    screenshot_tweet(url, output_path) -> str
"""

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Target canvas size for the final Short
CANVAS_W, CANVAS_H = 1080, 1920

# Viewport that matches an iPhone 13 (375×812 logical px, device pixel ratio 3)
_VIEWPORT_W   = 390
_VIEWPORT_H   = 844
_DEVICE_SCALE = 3       # results in 1170×2532 physical pixels


def screenshot_tweet(url: str, output_path: str) -> str:
    """Screenshot a real X post and return a 1080×1920 PNG ready for video assembly.

    The tweet article is screenshotted at mobile viewport, then placed centred
    on a pure-black 1080×1920 canvas.

    Args:
        url:         Full X/Twitter URL, e.g. https://x.com/user/status/123
        output_path: Destination path for the PNG.

    Returns:
        Absolute path of the saved PNG.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Screenshotting tweet: %s", url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": _VIEWPORT_W, "height": _VIEWPORT_H},
            device_scale_factor=_DEVICE_SCALE,
            color_scheme="dark",
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )
        page = ctx.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Wait for the tweet article to appear
            page.wait_for_selector('article[data-testid="tweet"]', timeout=20_000)
            # Extra settle time for fonts / images
            page.wait_for_timeout(1500)
        except PWTimeout:
            logger.warning("Timed out waiting for tweet element at %s", url)
        except Exception as e:
            logger.warning("Navigation error for %s: %s", url, e)

        # Screenshot just the tweet article element
        tweet_el = page.query_selector('article[data-testid="tweet"]')
        if tweet_el:
            raw_png = out.with_name("_raw_tweet.png")
            tweet_el.screenshot(path=str(raw_png))
            logger.info("Tweet element captured → %s", raw_png)
        else:
            # Fallback: full page screenshot
            logger.warning("Tweet element not found — falling back to full-page screenshot")
            raw_png = out.with_name("_raw_tweet.png")
            page.screenshot(path=str(raw_png), full_page=False)

        browser.close()

    # Compose onto a 1080×1920 black canvas
    _compose_on_canvas(raw_png, out)
    raw_png.unlink(missing_ok=True)

    logger.info("Screenshot saved → %s", out)
    return str(out)


def _compose_on_canvas(src: Path, dst: Path) -> None:
    """Place the tweet screenshot centred-top on a 1080×1920 black canvas."""
    tweet_img = Image.open(src).convert("RGB")
    tw, th    = tweet_img.size

    # Scale to fit canvas width if wider
    if tw > CANVAS_W:
        scale     = CANVAS_W / tw
        tw        = CANVAS_W
        th        = int(th * scale)
        tweet_img = tweet_img.resize((tw, th), Image.LANCZOS)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), "#000000")

    # Paste at top-centre (leave ~120px from top for status bar feel)
    paste_x = (CANVAS_W - tw) // 2
    paste_y = 120
    canvas.paste(tweet_img, (paste_x, paste_y))
    canvas.save(str(dst), "PNG")
