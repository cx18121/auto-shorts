"""
formats/tweets/scraper.py — Fetch real viral tweets via twscrape.

Scrapes recent tweets from a curated list of popular accounts, ranks them
by engagement (likes + retweets), and returns the top ones ready for
screenshotting.

Public API:
    setup_account(username, password, email)  -> None  (one-time setup)
    scrape_top_tweets(n, min_likes) -> list[dict]
"""

import asyncio
import logging
from pathlib import Path

import twscrape

logger = logging.getLogger(__name__)

# Twscrape stores its account DB here
_ACCOUNTS_DB = Path("data/twscrape_accounts.db")

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

# How many recent tweets to fetch per account
_TWEETS_PER_ACCOUNT = 20


async def _setup_account_async(username: str, password: str, email: str,
                                email_password: str | None = None) -> None:
    api = twscrape.API(str(_ACCOUNTS_DB))
    await api.pool.add_account(
        username=username,
        password=password,
        email=email,
        email_password=email_password or password,
    )
    await api.pool.login_all()
    logger.info("Account %s added and logged in.", username)


def setup_account(username: str, password: str, email: str,
                   email_password: str | None = None) -> None:
    """One-time setup: add a Twitter/X account for scraping.

    Args:
        username:       Twitter @handle (without @).
        password:       Account password.
        email:          Account email address.
        email_password: Email password (if different from Twitter password).
    """
    _ACCOUNTS_DB.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_setup_account_async(username, password, email, email_password))


async def _scrape_async(accounts: list[str], tweets_per_account: int,
                         min_likes: int) -> list[dict]:
    api = twscrape.API(str(_ACCOUNTS_DB))
    results: list[dict] = []

    for handle in accounts:
        try:
            logger.info("Scraping @%s …", handle)
            user = await api.user_by_login(handle)
            if not user:
                logger.warning("User not found: @%s", handle)
                continue

            count = 0
            async for tweet in api.user_tweets(user.id, limit=tweets_per_account):
                if tweet.likeCount < min_likes:
                    continue
                # Skip replies and retweets
                if tweet.inReplyToTweetId or tweet.retweetedTweet:
                    continue
                # Skip tweets with media (images/videos) — text-only looks best
                if tweet.media and (tweet.media.photos or tweet.media.videos):
                    continue

                user = tweet.user
                results.append({
                    "url":               f"https://x.com/{handle}/status/{tweet.id}",
                    "tweet_id":          str(tweet.id),
                    "username":          handle,
                    "display_name":      user.displayname if user else handle,
                    "tweet_text":        tweet.rawContent,
                    "text":              tweet.rawContent,
                    "likes":             tweet.likeCount,
                    "retweets":          tweet.retweetedCount,
                    "views":             tweet.viewCount or 0,
                    "score":             tweet.likeCount + tweet.retweetedCount * 3,
                    "profile_image_url": user.profileImageUrl if user else None,
                    "verified":          bool((user.blue or user.verified) if user else False),
                    "created_at":        tweet.date.strftime("%-I:%M %p · %b %-d, %Y") if tweet.date else None,
                })
                count += 1

            logger.info("  → %d qualifying tweets from @%s", count, handle)

        except Exception as e:
            logger.warning("Failed to scrape @%s: %s", handle, e)

    # Sort by engagement score descending
    results.sort(key=lambda t: t["score"], reverse=True)
    return results


def scrape_top_tweets(
    n: int = 10,
    min_likes: int = 500,
    accounts: list[str] | None = None,
) -> list[dict]:
    """Fetch top viral tweets from curated accounts.

    Args:
        n:         Maximum number of tweets to return.
        min_likes: Minimum like count to include a tweet.
        accounts:  Override the default account list.

    Returns:
        List of tweet dicts sorted by engagement, each containing:
        url, tweet_id, username, display_name, text, likes, retweets, views, score.
    """
    _ACCOUNTS_DB.parent.mkdir(parents=True, exist_ok=True)
    target = accounts or VIRAL_ACCOUNTS
    logger.info("Scraping %d accounts for top tweets (min_likes=%d) …",
                len(target), min_likes)
    tweets = asyncio.run(_scrape_async(target, _TWEETS_PER_ACCOUNT, min_likes))
    logger.info("Found %d qualifying tweets total, returning top %d", len(tweets), n)
    return tweets[:n]
