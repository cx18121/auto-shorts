"""
formats/tweets/scraper.py — Fetch real viral tweets via Playwright.

Scrapes tweets from two sources and merges them:
  1. Curated account profiles (predictable high-engagement sources)
  2. The authenticated home feed (algorithmically diverse posts)

Public API:
    setup_account(username, password, email)  -> None  (kept for backwards compat)
    scrape_top_tweets(n, min_likes) -> list[dict]
"""

import asyncio
import logging
import re
from http.cookiejar import MozillaCookieJar
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to Netscape-format X.com cookies (exported from browser)
_COOKIES_PATH = Path("data/x.com_cookies.txt")

# Curated list of accounts known for high-engagement viral tweets
VIRAL_ACCOUNTS = [
    # Business / entrepreneurship
    "naval", "paulg", "Jason", "sama", "levelsio",
    # Science / education
    "waitbutwhy", "neiltyson",
    # Productivity / mindset
    "JamesClear", "ShaneAParrish", "morganhousel",
    # Tech / culture
    "paulgraham", "benedictevans",
    # Humor / observations
    "dril", "KaleFrancis",
]

# Tweets to collect per account profile
_TWEETS_PER_ACCOUNT = 20

# Tweets to collect from the home feed
_HOME_FEED_TARGET = 40


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_playwright_cookies(cookies_path: Path) -> list[dict]:
    """Parse a Netscape cookie file into Playwright cookie dicts.

    Args:
        cookies_path: Path to a Netscape-format cookies.txt file.

    Returns:
        List of cookie dicts accepted by ``BrowserContext.add_cookies()``.
    """
    if not cookies_path.exists():
        raise FileNotFoundError(
            f"Cookie file not found: {cookies_path}. "
            "Export your X.com cookies using the 'Get cookies.txt LOCALLY' "
            "Chrome extension and save to data/x.com_cookies.txt"
        )

    jar = MozillaCookieJar(str(cookies_path))
    jar.load(ignore_discard=True, ignore_expires=True)

    pw_cookies: list[dict] = []
    for cookie in jar:
        pw_cookie: dict = {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
            "secure": bool(cookie.secure),
            "httpOnly": bool(getattr(cookie, "_rest", {}).get("HttpOnly", False)),
        }
        if cookie.expires:
            pw_cookie["expires"] = float(cookie.expires)
        pw_cookies.append(pw_cookie)

    logger.info("Loaded %d cookies from %s", len(pw_cookies), cookies_path)
    return pw_cookies


def _parse_count(text: str) -> int:
    """Convert an X.com engagement label to an integer.

    Handles formats like "1,234", "1.2K", "45.6K", "1.1M".

    Args:
        text: Raw string from an aria-label or span.

    Returns:
        Integer count, or 0 if the string cannot be parsed.
    """
    match = re.search(r"[\d,]+\.?\d*[KkMm]?", text.replace(",", ""))
    if not match:
        return 0
    s = match.group(0).strip()
    try:
        if s.lower().endswith("k"):
            return int(float(s[:-1]) * 1_000)
        if s.lower().endswith("m"):
            return int(float(s[:-1]) * 1_000_000)
        return int(s)
    except (ValueError, OverflowError):
        return 0


async def _extract_tweet_from_card(card, fallback_handle: str = "") -> dict | None:
    """Extract a tweet dict from a Playwright element handle.

    Returns None if the tweet should be skipped (reply, retweet, media, no text).

    Args:
        card:             Playwright ElementHandle for a ``[data-testid="tweet"]``.
        fallback_handle:  @handle to use if the DOM doesn't yield a username.

    Returns:
        Tweet dict or None.
    """
    # ---- Filter: skip retweets ------------------------------------------
    social_ctx = await card.query_selector('[data-testid="socialContext"]')
    if social_ctx:
        ctx_text = (await social_ctx.inner_text()).lower()
        if "retweeted" in ctx_text:
            return None

    # ---- Filter: skip replies -------------------------------------------
    card_text = await card.inner_text()
    if "Replying to" in card_text:
        return None

    # ---- Filter: skip media tweets --------------------------------------
    if await card.query_selector('[data-testid="tweetPhoto"]'):
        return None
    if await card.query_selector('[data-testid="videoPlayer"]'):
        return None

    # ---- Tweet ID from timestamp link -----------------------------------
    time_el = await card.query_selector("time")
    if not time_el:
        return None
    datetime_str = await time_el.get_attribute("datetime")

    time_link = await card.query_selector("a:has(time)")
    if not time_link:
        return None
    href = await time_link.get_attribute("href") or ""
    parts = href.rstrip("/").split("/")
    tweet_id = parts[-1] if parts else ""
    if not tweet_id or not tweet_id.isdigit():
        return None

    # ---- Tweet text -----------------------------------------------------
    text_el = await card.query_selector('[data-testid="tweetText"]')
    if not text_el:
        return None
    tweet_text = (await text_el.inner_text()).strip()
    if not tweet_text:
        return None

    # ---- Like count -----------------------------------------------------
    like_el = await card.query_selector('[data-testid="like"]')
    likes = 0
    if like_el:
        aria = await like_el.get_attribute("aria-label") or ""
        likes = _parse_count(aria)
        if not aria:
            span = await like_el.query_selector(
                "span[data-testid='app-text-transition-container']"
            )
            if span:
                likes = _parse_count(await span.inner_text())

    # ---- Retweet count --------------------------------------------------
    rt_el = await card.query_selector('[data-testid="retweet"]')
    retweets = 0
    if rt_el:
        aria = await rt_el.get_attribute("aria-label") or ""
        retweets = _parse_count(aria)

    # ---- Display name + username ----------------------------------------
    user_name_el = await card.query_selector('[data-testid="User-Name"]')
    display_name = fallback_handle
    scraped_username = fallback_handle
    if user_name_el:
        spans = await user_name_el.query_selector_all("span")
        texts = [
            (await sp.inner_text()).strip()
            for sp in spans
        ]
        texts = [t for t in texts if t and not t.startswith("·")]
        if texts:
            display_name = texts[0]
        for t in texts:
            if t.startswith("@"):
                scraped_username = t.lstrip("@")
                break

    # ---- Profile image --------------------------------------------------
    avatar_el = await card.query_selector(
        f'[data-testid="UserAvatar-Container-{scraped_username}"] img,'
        f'[data-testid="UserAvatar-Container-{fallback_handle}"] img'
    )
    profile_image_url: str | None = None
    if avatar_el:
        profile_image_url = await avatar_el.get_attribute("src")

    # ---- Verified badge -------------------------------------------------
    verified = bool(await card.query_selector('[data-testid="icon-verified"]'))

    # ---- created_at formatting ------------------------------------------
    created_at: str | None = None
    if datetime_str:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            dt = dt.astimezone()
            created_at = dt.strftime("%-I:%M %p · %b %-d, %Y")
        except Exception:
            created_at = datetime_str

    return {
        "url":               f"https://x.com/{scraped_username}/status/{tweet_id}",
        "tweet_id":          tweet_id,
        "username":          scraped_username,
        "display_name":      display_name,
        "tweet_text":        tweet_text,
        "text":              tweet_text,
        "likes":             likes,
        "retweets":          retweets,
        "views":             0,
        "score":             likes + retweets * 3,
        "profile_image_url": profile_image_url,
        "verified":          verified,
        "created_at":        created_at,
    }


async def _scrape_page_playwright(
    page,
    url: str,
    target: int,
    min_likes: int,
    max_scrolls: int = 20,
    label: str = "",
) -> list[dict]:
    """Navigate to a URL, scroll, and collect qualifying tweet dicts.

    Generic engine used by both profile and home-feed scrapers.

    Args:
        page:        Playwright Page (already authenticated).
        url:         X.com URL to navigate to.
        target:      Stop collecting after this many qualifying tweets.
        min_likes:   Minimum like count.
        max_scrolls: Hard cap on scroll iterations.
        label:       Human-readable label for log messages.

    Returns:
        List of tweet dicts.
    """
    logger.info("Navigating to %s", url)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_selector('[data-testid="tweet"]', timeout=20_000)
    except Exception as e:
        logger.warning("Failed to load %s: %s", label or url, e)
        return []

    results: list[dict] = []
    seen_ids: set[str] = set()
    no_new_count = 0

    for _ in range(max_scrolls):
        if len(results) >= target:
            break

        cards = await page.query_selector_all('[data-testid="tweet"]')
        prev_seen = len(seen_ids)

        for card in cards:
            if len(results) >= target:
                break
            tweet = await _extract_tweet_from_card(card)
            if tweet is None:
                continue
            if tweet["tweet_id"] in seen_ids:
                continue
            if tweet["likes"] < min_likes:
                seen_ids.add(tweet["tweet_id"])  # mark seen so we don't re-check
                continue
            seen_ids.add(tweet["tweet_id"])
            results.append(tweet)

        await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
        await page.wait_for_timeout(1_500)

        if len(seen_ids) == prev_seen:
            no_new_count += 1
            if no_new_count >= 3:
                logger.debug("No new cards after 3 scrolls for %s, stopping", label or url)
                break
        else:
            no_new_count = 0

    logger.info("  → %d qualifying tweets from %s", len(results), label or url)
    return results


# ---------------------------------------------------------------------------
# Source-specific scrapers
# ---------------------------------------------------------------------------

async def _scrape_account_playwright(
    page,
    handle: str,
    tweets_per_account: int,
    min_likes: int,
) -> list[dict]:
    """Scrape one account's profile page."""
    return await _scrape_page_playwright(
        page,
        url=f"https://x.com/{handle}",
        target=tweets_per_account,
        min_likes=min_likes,
        label=f"@{handle}",
    )


async def _scrape_home_playwright(
    page,
    target: int,
    min_likes: int,
) -> list[dict]:
    """Scrape the authenticated home feed for diverse posts."""
    return await _scrape_page_playwright(
        page,
        url="https://x.com/home",
        target=target,
        min_likes=min_likes,
        max_scrolls=30,
        label="home feed",
    )


# ---------------------------------------------------------------------------
# Main async scraper
# ---------------------------------------------------------------------------

async def _scrape_async(
    accounts: list[str],
    tweets_per_account: int,
    min_likes: int,
    include_home: bool = True,
) -> list[dict]:
    """Scrape account profiles + home feed, merge, and rank by score."""
    from playwright.async_api import async_playwright

    cookies = _load_playwright_cookies(_COOKIES_PATH)
    results: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            await ctx.add_cookies(cookies)
            page = await ctx.new_page()

            # --- Home feed ---------------------------------------------------
            if include_home:
                try:
                    home_tweets = await _scrape_home_playwright(
                        page, target=_HOME_FEED_TARGET, min_likes=min_likes
                    )
                    results.extend(home_tweets)
                    logger.info("Home feed: %d qualifying tweets", len(home_tweets))
                except Exception as e:
                    logger.warning("Home feed scrape failed: %s", e)
                await asyncio.sleep(2.0)

            # --- Curated account profiles ------------------------------------
            for i, handle in enumerate(accounts):
                try:
                    account_tweets = await _scrape_account_playwright(
                        page, handle, tweets_per_account, min_likes
                    )
                    results.extend(account_tweets)
                except Exception as e:
                    logger.warning("Failed to scrape @%s: %s", handle, e)
                if i < len(accounts) - 1:
                    await asyncio.sleep(2.5)
        finally:
            await browser.close()

    # Deduplicate by tweet_id (home feed and profile may overlap)
    seen: set[str] = set()
    deduped: list[dict] = []
    for t in results:
        if t["tweet_id"] not in seen:
            seen.add(t["tweet_id"])
            deduped.append(t)

    deduped.sort(key=lambda t: t["score"], reverse=True)
    return deduped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_account(username: str, password: str, email: str,
                   email_password: str | None = None,
                   cookies: str | None = None) -> None:
    """Kept for backwards compatibility — no longer needed for Playwright scraping.

    Playwright reads cookies directly from ``data/x.com_cookies.txt``.
    Export that file from your browser using the 'Get cookies.txt LOCALLY'
    Chrome extension while logged in to X.com.
    """
    logger.info(
        "setup_account() is a no-op with the Playwright scraper. "
        "Export your X.com cookies to data/x.com_cookies.txt instead."
    )


def scrape_top_tweets(
    n: int = 10,
    min_likes: int = 500,
    accounts: list[str] | None = None,
    include_home: bool = True,
) -> list[dict]:
    """Fetch top viral tweets from curated accounts and the home feed.

    Combines two sources:
      - Curated account profiles (``accounts`` or ``VIRAL_ACCOUNTS``)
      - Authenticated home feed (algorithmically diverse posts)

    Results are deduplicated, sorted by engagement score, and capped at ``n``.

    Args:
        n:            Maximum number of tweets to return.
        min_likes:    Minimum like count to include a tweet.
        accounts:     Override the default curated account list.
        include_home: Whether to also scrape the home feed (default True).

    Returns:
        List of tweet dicts sorted by engagement score (desc), each containing:
        url, tweet_id, username, display_name, text, likes, retweets, views,
        score, profile_image_url, verified, created_at.
    """
    target = accounts or VIRAL_ACCOUNTS
    logger.info(
        "Scraping %d accounts + %s for top tweets (min_likes=%d) via Playwright …",
        len(target),
        "home feed" if include_home else "no home feed",
        min_likes,
    )
    tweets = asyncio.run(
        _scrape_async(target, _TWEETS_PER_ACCOUNT, min_likes, include_home=include_home)
    )
    logger.info("Found %d unique qualifying tweets total, returning top %d", len(tweets), n)
    return tweets[:n]
