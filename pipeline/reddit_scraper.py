"""
pipeline/reddit_scraper.py — Reddit scraper using PRAW.

Fetches top posts from configured subreddits, filters invalid content,
and provides results for downstream quality filtering and backlog insertion.

Public API:
    scrape_subreddit_top(reddit, subreddit_name, time_filter, limit) -> list[dict]
    scrape_channel_subreddits(channel_cfg, reddit, time_filter, limit) -> list[dict]
    scrape_and_store_reddit(channel_cfg, window, limit) -> dict

Note: config, praw, analysis.db are imported lazily inside scrape_and_store_reddit
to avoid triggering channels.yaml loading at import time (for testability).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INVALID_SELFTEXT: frozenset[str] = frozenset({"", "[removed]", "[deleted]"})

WINDOW_MAP: dict[str, str] = {
    "24h": "day",
    "month": "month",
}


# ---------------------------------------------------------------------------
# Core scraping functions
# ---------------------------------------------------------------------------

def scrape_subreddit_top(
    reddit: Any,
    subreddit_name: str,
    time_filter: str = "day",
    limit: int = 100,
) -> list[dict]:
    """Fetch top posts from a single subreddit and return as list of dicts.

    Filters out link posts (is_self=False) and posts with invalid selftext
    (empty, [removed], or [deleted]).

    Args:
        reddit:         PRAW Reddit instance (read-only).
        subreddit_name: Subreddit name without the r/ prefix.
        time_filter:    PRAW time_filter — "day", "week", "month", "year", "all".
        limit:          Maximum number of posts to fetch from Reddit API.

    Returns:
        List of post dicts with keys: id, title, body, score, word_count,
        subreddit, url. Returns [] on any exception.
    """
    try:
        submissions = reddit.subreddit(subreddit_name).top(
            time_filter=time_filter,
            limit=limit,
        )
        results: list[dict] = []
        for post in submissions:
            # Skip link posts — they have no meaningful body text
            if not post.is_self:
                continue
            # Skip posts with invalid selftext
            if post.selftext in INVALID_SELFTEXT:
                continue
            results.append({
                "id": post.id,
                "title": post.title,
                "body": post.selftext,
                "score": post.score,
                "word_count": len(post.selftext.split()),
                "subreddit": subreddit_name,
                "url": f"https://reddit.com{post.permalink}",
            })
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
    reddit: Any,
    time_filter: str = "day",
    limit: int = 100,
) -> list[dict]:
    """Scrape all subreddits configured for a channel and return merged post list.

    Per-subreddit failures are caught and logged — other subreddits still run.
    Deduplicates by post id (handles cross-posted content).

    Args:
        channel_cfg: Channel configuration from channels.yaml.
        reddit:      PRAW Reddit instance (read-only).
        time_filter: PRAW time_filter string.
        limit:       Maximum posts per subreddit.

    Returns:
        Deduplicated list of post dicts across all configured subreddits.
    """
    seen_ids: set[str] = set()
    all_posts: list[dict] = []

    for subreddit_name in channel_cfg.subreddits:
        try:
            posts = scrape_subreddit_top(reddit, subreddit_name, time_filter, limit)
            for post in posts:
                if post["id"] not in seen_ids:
                    seen_ids.add(post["id"])
                    all_posts.append(post)
        except Exception:
            logger.warning(
                "scrape_channel_subreddits: error processing r/%s — skipping",
                subreddit_name,
                exc_info=True,
            )

    return all_posts


def scrape_and_store_reddit(
    channel_cfg: Any,
    window: str = "24h",
    limit: int = 100,
) -> dict:
    """Scrape Reddit posts for a channel, quality-filter, and insert passing posts into backlog.

    Creates a PRAW read-only Reddit instance using credentials from config.py.
    Maps the window string to a PRAW time_filter via WINDOW_MAP.

    Args:
        channel_cfg: Channel configuration from channels.yaml (ChannelConfig dataclass).
        window:      Time window string — "24h" or "month". Defaults to "24h".
        limit:       Maximum posts to fetch per subreddit.

    Returns:
        Summary dict: {"scraped": int, "passed": int, "inserted": int, "duplicates": int}
    """
    # Lazy imports to avoid triggering channels.yaml loading at import time
    import praw as _praw
    import config as _config
    from analysis.db import get_connection
    from pipeline.backlog import insert_story
    from pipeline.quality_filter import passes_story_quality

    reddit = _praw.Reddit(
        client_id=_config.REDDIT_CLIENT_ID,
        client_secret=_config.REDDIT_CLIENT_SECRET,
        user_agent=_config.REDDIT_USER_AGENT,
    )
    reddit.read_only = True

    time_filter = WINDOW_MAP.get(window, "day")

    posts = scrape_channel_subreddits(channel_cfg, reddit, time_filter, limit)

    scraped = len(posts)
    passed = 0
    inserted = 0
    duplicates = 0

    conn = get_connection()
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
