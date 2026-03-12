"""
formats/storytelling/reddit_renderer.py — Render story text as a Reddit post screenshot.

Renders the story as a Reddit dark-mode post using HTML + Playwright,
producing a tall PNG that can be scrolled over the duration of the video.

Public API:
    render_reddit_post(story_text, title, subreddit, score, output_path) -> str
"""

import html
import logging
import random
from pathlib import Path

from PIL import Image

import config

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).parent / "reddit_template.html"

# Target width matching assembler _POST_W (narrower than canvas for gameplay border)
RENDER_WIDTH = 940


def render_reddit_post(
    story_text: str,
    title: str,
    subreddit: str = "stories",
    score: int = 0,
    output_path: str = "",
) -> str:
    """Render story text as a Reddit-style post screenshot.

    Args:
        story_text: The narration text (will be used as the post body).
        title:      Post title.
        subreddit:  Subreddit name (without r/).
        score:      Upvote score to display.
        output_path: Destination PNG path.

    Returns:
        Absolute path of the saved PNG.
    """
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    filled = _fill_template(template, story_text, title, subreddit, score)

    # Render HTML to PNG via Playwright
    raw_png = _render_html(filled, out.parent)

    # Scale to target width — no padding, let gameplay show around short posts
    img = Image.open(raw_png).convert("RGBA")
    w, h = img.size
    if w != RENDER_WIDTH:
        scale = RENDER_WIDTH / w
        img = img.resize((RENDER_WIDTH, int(h * scale)), Image.LANCZOS)

    img.save(str(out), "PNG")
    raw_png.unlink(missing_ok=True)

    logger.info("Rendered Reddit post → %s (%dx%d)", out, img.width, img.height)
    return str(out)


def _fill_template(
    template: str,
    story_text: str,
    title: str,
    subreddit: str,
    score: int,
) -> str:
    """Replace placeholders in the HTML template."""
    body_html = html.escape(story_text, quote=False)
    # Preserve paragraph breaks
    body_html = body_html.replace("\n\n", "\n\n")

    # Format score like Reddit (e.g. 1.2k)
    if score >= 1000:
        score_str = f"{score / 1000:.1f}k"
    else:
        score_str = str(score)

    # Fake metadata
    username = _random_username()
    time_ago = random.choice(["3h", "5h", "8h", "12h", "14h", "1d"])
    comments = random.randint(50, 800)

    replacements = {
        "{{SCORE}}": score_str,
        "{{SUBREDDIT}}": html.escape(subreddit),
        "{{USERNAME}}": username,
        "{{TIME_AGO}}": time_ago,
        "{{TITLE}}": html.escape(title),
        "{{BODY}}": body_html,
        "{{COMMENTS}}": str(comments),
    }

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result


def _random_username() -> str:
    """Generate a Reddit-like throwaway username."""
    prefixes = [
        "ThrowRA", "throwaway", "anonymous", "confused",
        "worried", "stressed", "just_a", "regular",
    ]
    suffixes = [str(random.randint(100, 9999)) for _ in range(1)]
    return random.choice(prefixes) + suffixes[0]


def _render_html(html_content: str, workdir: Path) -> Path:
    """Render HTML string to a temporary PNG file via Playwright."""
    from playwright.sync_api import sync_playwright

    tmp_html = workdir / "_tmp_reddit.html"
    tmp_html.write_text(html_content, encoding="utf-8")
    tmp_png = tmp_html.with_suffix(".png")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 600, "height": 800},
            device_scale_factor=3,
            color_scheme="dark",
        )
        page.goto(f"file://{tmp_html.resolve()}", wait_until="networkidle")
        page.wait_for_timeout(500)

        container = page.query_selector(".post-container")
        if container:
            container.screenshot(path=str(tmp_png))
        else:
            page.screenshot(path=str(tmp_png), full_page=True)

        browser.close()

    tmp_html.unlink(missing_ok=True)
    return tmp_png
