"""
pipeline/quality_filter.py — Pure threshold-based quality filters for Reddit stories and tweets.

No Claude API calls. No hard-coded threshold numbers. All thresholds are read from the
quality_cfg dict, which is sourced from channels.yaml via ChannelConfig.quality.

Functions:
    passes_story_quality(post_dict, quality_cfg) -> tuple[bool, str]
    passes_tweet_quality(tweet_dict, quality_cfg) -> tuple[bool, str]

Return convention: (True, "") on pass; (False, "descriptive reason") on fail.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def passes_story_quality(post_dict: dict, quality_cfg: dict) -> tuple[bool, str]:
    """Check whether a Reddit story post meets the configured quality thresholds.

    Args:
        post_dict: Dict with at least 'score' (int) and 'word_count' (int).
        quality_cfg: Threshold config from channels.yaml quality: block.
                     Expected keys: min_upvotes, min_words, max_words.

    Returns:
        (True, "") if the post meets all thresholds.
        (False, reason) if any threshold is not met, where reason describes the failure.
    """
    score = post_dict["score"]
    word_count = post_dict["word_count"]

    min_upvotes = quality_cfg["min_upvotes"]
    if score < min_upvotes:
        reason = f"upvotes {score} < {min_upvotes}"
        logger.debug("Story rejected: %s", reason)
        return False, reason

    min_words = quality_cfg["min_words"]
    if word_count < min_words:
        reason = f"word_count {word_count} < {min_words}"
        logger.debug("Story rejected: %s", reason)
        return False, reason

    max_words = quality_cfg["max_words"]
    if word_count > max_words:
        reason = f"word_count {word_count} > {max_words}"
        logger.debug("Story rejected: %s", reason)
        return False, reason

    logger.debug("Story passed quality checks (score=%d, word_count=%d)", score, word_count)
    return True, ""


def passes_tweet_quality(tweet_dict: dict, quality_cfg: dict) -> tuple[bool, str]:
    """Check whether a scraped tweet meets the configured quality thresholds.

    Rejects tweets below the likes threshold, tweets containing URLs (spam/link bait),
    and tweets with excessive @-mentions (mention spam).

    Args:
        tweet_dict: Dict with at least 'likes' (int). May contain 'tweet_text' (str).
        quality_cfg: Threshold config from channels.yaml quality: block.
                     Expected keys: min_likes.

    Returns:
        (True, "") if the tweet meets all thresholds.
        (False, reason) if any threshold is not met.
    """
    likes = tweet_dict["likes"]
    min_likes = quality_cfg["min_likes"]
    if likes < min_likes:
        reason = f"likes {likes} < {min_likes}"
        logger.debug("Tweet rejected: %s", reason)
        return False, reason

    tweet_text: str = tweet_dict.get("tweet_text", "")

    if "http://" in tweet_text or "https://" in tweet_text:
        reason = "tweet contains URL"
        logger.debug("Tweet rejected: %s", reason)
        return False, reason

    mention_count = tweet_text.count("@")
    if mention_count > 2:
        reason = "tweet has too many @-mentions"
        logger.debug("Tweet rejected: %s (count=%d)", reason, mention_count)
        return False, reason

    logger.debug("Tweet passed quality checks (likes=%d)", likes)
    return True, ""
