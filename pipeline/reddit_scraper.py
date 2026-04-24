"""
pipeline/reddit_scraper.py — Reddit scraper using public JSON endpoints.

Fetches top posts from configured subreddits via reddit.com/.json,
filters invalid content, and provides results for downstream quality
filtering and backlog insertion. No API credentials required.

Public API:
    scrape_subreddit_top(subreddit_name, time_filter, limit) -> list[dict]
    scrape_channel_subreddits(channel_cfg, time_filter, limit) -> list[dict]
    scrape_and_store_reddit(channel_cfg, window, limit) -> dict
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INVALID_SELFTEXT: frozenset[str] = frozenset({"", "[removed]", "[deleted]"})

WINDOW_MAP: dict[str, str] = {
    "24h": "day",
    "month": "month",
    "year": "year",
}

_USER_AGENT = "auto-shorts/1.0 (reddit public JSON scraper)"
_REQUEST_DELAY = 2.0  # seconds between requests to avoid rate limiting


# ---------------------------------------------------------------------------
# Core scraping functions
# ---------------------------------------------------------------------------

def scrape_subreddit_top(
    subreddit_name: str,
    time_filter: str = "day",
    limit: int = 100,
) -> list[dict]:
    """Fetch top posts from a single subreddit via public JSON and return as list of dicts.

    Filters out link posts (is_self=False) and posts with invalid selftext
    (empty, [removed], or [deleted]).

    Args:
        subreddit_name: Subreddit name without the r/ prefix.
        time_filter:    Time filter — "day", "week", "month", "year", "all".
        limit:          Maximum number of posts to fetch.

    Returns:
        List of post dicts with keys: id, title, body, score, word_count,
        subreddit, url. Returns [] on any exception.
    """
    try:
        results: list[dict] = []
        after: str | None = None
        fetched = 0

        while fetched < limit:
            batch_size = min(100, limit - fetched)
            url = f"https://www.reddit.com/r/{subreddit_name}/top.json"
            params: dict[str, Any] = {
                "t": time_filter,
                "limit": batch_size,
            }
            if after:
                params["after"] = after

            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            children = data.get("data", {}).get("children", [])
            if not children:
                break

            for child in children:
                post = child.get("data", {})
                if not post.get("is_self", False):
                    continue
                selftext = post.get("selftext", "")
                if selftext in INVALID_SELFTEXT:
                    continue
                results.append({
                    "id": post["id"],
                    "title": post.get("title", ""),
                    "body": selftext,
                    "score": post.get("score", 0),
                    "word_count": len(selftext.split()),
                    "subreddit": subreddit_name,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                })

            after = data.get("data", {}).get("after")
            fetched += len(children)

            if not after:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info("Scraped %d posts from r/%s", len(results), subreddit_name)
        return results
    except Exception:
        logger.warning(
            "scrape_subreddit_top: failed to fetch r/%s — skipping",
            subreddit_name,
            exc_info=True,
        )
        return []


def scrape_channel_subreddits(
    channel_cfg: Any,
    time_filter: str = "day",
    limit: int = 100,
) -> list[dict]:
    """Scrape all subreddits configured for a channel and return merged post list.

    Per-subreddit failures are caught and logged — other subreddits still run.
    Deduplicates by post id (handles cross-posted content).

    Args:
        channel_cfg: Channel configuration from channels.yaml.
        time_filter: Time filter string.
        limit:       Maximum posts per subreddit.

    Returns:
        Deduplicated list of post dicts across all configured subreddits.
    """
    seen_ids: set[str] = set()
    all_posts: list[dict] = []

    def fetch_subreddit(name: str) -> list[dict]:
        try:
            return scrape_subreddit_top(name, time_filter, limit)
        except Exception:
            logger.warning(
                "scrape_channel_subreddits: error processing r/%s — skipping",
                name,
                exc_info=True,
            )
            return []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_subreddit, name): name for name in channel_cfg.subreddits}
        for future in as_completed(futures):
            for post in future.result():
                if post["id"] not in seen_ids:
                    seen_ids.add(post["id"])
                    all_posts.append(post)

    return all_posts


def scrape_and_store_reddit(
    channel_cfg: Any,
    window: str = "24h",
    limit: int = 100,
) -> dict:
    """Scrape Reddit posts for a channel, quality-filter, and insert passing posts into backlog.

    Uses Reddit's public JSON endpoints — no API credentials needed.
    Maps the window string to a time_filter via WINDOW_MAP.

    Args:
        channel_cfg: Channel configuration from channels.yaml (ChannelConfig dataclass).
        window:      Time window string — "24h", "month", or "year". Defaults to "24h".
        limit:       Maximum posts to fetch per subreddit.

    Returns:
        Summary dict: {"scraped": int, "passed": int, "inserted": int, "duplicates": int}
    """
    from pipeline.db import get_connection
    from pipeline.backlog import insert_story, init_backlog_tables
    from pipeline.quality_filter import passes_story_quality

    time_filter = WINDOW_MAP.get(window, "day")

    posts = scrape_channel_subreddits(channel_cfg, time_filter, limit)

    scraped = len(posts)
    passed = 0
    inserted = 0
    duplicates = 0

    conn = get_connection()
    init_backlog_tables(conn)
    try:
        for post in posts:
            ok, reason = passes_story_quality(post, channel_cfg.quality)
            if not ok:
                logger.info(
                    "Rejected r/%s post '%s...': %s",
                    post["subreddit"],
                    post["title"][:40],
                    reason,
                )
                continue
            passed += 1
            was_inserted = insert_story(conn, {**post, "channel": channel_cfg.slug})
            if was_inserted:
                inserted += 1
                logger.info("Stored: %s", post["id"])
            else:
                duplicates += 1
                logger.debug("Duplicate: %s", post["id"])
    finally:
        conn.close()

    return {
        "scraped": scraped,
        "passed": passed,
        "inserted": inserted,
        "duplicates": duplicates,
    }


__all__ = [
    "scrape_subreddit_top",
    "scrape_channel_subreddits",
    "scrape_and_store_reddit",
]
