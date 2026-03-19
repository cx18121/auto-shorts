"""
formats/tweets/generator.py — Generate tweet screenshots via Claude Haiku.

Public API:
    generate_tweet(profile)                      -> dict
    generate_batch(count, profile_path)          -> list[dict]
    generate_thread(count, profile_path)         -> list[list[dict]]
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Any

import anthropic

import config
from pipeline.claude_utils import parse_json as _parse_json_shared

logger = logging.getLogger(__name__)

_MODEL       = "claude-haiku-4-5-20251001"
_TEMPERATURE = 0.85
_MAX_TOKENS  = 512
_MAX_RETRIES = 2

_REQUIRED_KEYS = {"display_name", "username", "tweet_text", "likes", "retweets", "hook_type"}

_SYSTEM_PROMPT = """\
You are a viral social media content creator. You generate realistic-looking tweets \
optimised for YouTube Shorts screenshot videos. You always output valid JSON and nothing else."""

_USER_PROMPT = """\
Generate a viral tweet screenshot for a YouTube Short.

CHANNEL STYLE GUIDANCE:
{guidance}

EMOTIONAL TRIGGERS TO USE: {emotional_triggers}
HOOK TYPES THAT WORK: {hook_patterns}
{feedback_block}
Rules:
- The tweet must be a standalone, punchy statement that works as a video hook
- Display name and username must sound like a real person (not obviously fake)
- Engagement numbers should be plausible for a viral tweet (likes: 5k–500k, retweets: 500–50k)
- Hook type must be one of: hot_take, relatable, controversial, funny, observation

Return exactly this JSON:
{{
  "display_name": "FirstName LastName or single name",
  "username": "handle_without_at_sign",
  "tweet_text": "the tweet content — punchy, under 240 chars, no hashtags",
  "likes": integer,
  "retweets": integer,
  "category": "topic category of this tweet",
  "hook_type": "hot_take|relatable|controversial|funny|observation"
}}"""

_THREAD_PROMPT = """\
Generate {n} thematically connected tweets for a YouTube Shorts thread video.

CHANNEL STYLE GUIDANCE:
{guidance}

The tweets should tell a progression or explore one theme from multiple angles.
Each tweet should work standalone but feel connected.

Return a JSON array of {n} tweet objects, each with:
{{
  "display_name": "string",
  "username": "string",
  "tweet_text": "string under 240 chars",
  "likes": integer,
  "retweets": integer,
  "category": "string",
  "hook_type": "hot_take|relatable|controversial|funny|observation"
}}"""


def generate_tweet(profile: dict[str, Any], feedback: str = "") -> dict[str, Any]:
    """Generate a single tweet from a style profile.

    Args:
        profile:  Style profile dict.
        feedback: Optional rejection reason from a previous attempt to guide regeneration.

    Returns:
        Tweet dict with keys: display_name, username, tweet_text, likes,
        retweets, category, hook_type.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = _build_prompt(profile, feedback=feedback)

    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            tweet = _parse_json_shared(text)
            _validate(tweet)
            # Normalise engagement numbers
            tweet["likes"]    = int(tweet["likes"])
            tweet["retweets"] = int(tweet["retweets"])
            logger.info("Generated tweet: %r (type=%s)", tweet["tweet_text"][:60], tweet["hook_type"])
            return tweet
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Tweet generation attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise RuntimeError(f"Tweet generation failed after {_MAX_RETRIES + 1} attempts") from e
            time.sleep(1)
        except Exception as e:
            logger.warning("Claude call attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError("Tweet generation failed")


def generate_batch(count: int, profile_path: str) -> list[dict[str, Any]]:
    """Generate multiple individual tweets.

    Args:
        count:        Number of tweets to generate.
        profile_path: Path to style profile JSON.

    Returns:
        List of tweet dicts.
    """
    profile = json.loads(Path(profile_path).read_text())
    tweets: list[dict[str, Any]] = []
    for i in range(count):
        try:
            tweets.append(generate_tweet(profile))
            logger.info("Batch: %d/%d tweets", len(tweets), count)
        except Exception as e:
            logger.error("Failed to generate tweet %d/%d: %s", i + 1, count, e)
    return tweets


def generate_thread(count: int, profile_path: str) -> list[list[dict[str, Any]]]:
    """Generate connected tweet threads for multi-tweet videos.

    Each thread is a list of 2–4 related tweets that share a theme.

    Args:
        count:        Number of threads to generate.
        profile_path: Path to style profile JSON.

    Returns:
        List of threads; each thread is a list of tweet dicts.
    """
    profile = json.loads(Path(profile_path).read_text())
    client  = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    threads: list[list[dict[str, Any]]] = []

    for i in range(count):
        thread_size = random.randint(2, 4)
        try:
            thread = _generate_one_thread(client, profile, thread_size)
            threads.append(thread)
            logger.info("Thread %d/%d generated (%d tweets)", len(threads), count, len(thread))
        except Exception as e:
            logger.error("Failed to generate thread %d/%d: %s", i + 1, count, e)

    return threads


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _build_prompt(profile: dict[str, Any], feedback: str = "") -> str:
    cs = profile.get("content_style", {})
    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (fix these issues in your next version):\n{feedback}\n"
        if feedback else ""
    )
    return _USER_PROMPT.format(
        guidance=profile.get("generation_prompt_guidance", "")[:400],
        emotional_triggers=", ".join(cs.get("emotional_triggers", ["relatability", "humor"])[:4]),
        hook_patterns=", ".join(cs.get("hook_patterns", [])[:3]),
        feedback_block=feedback_block,
    )


def _generate_one_thread(
    client: anthropic.Anthropic,
    profile: dict[str, Any],
    n: int,
) -> list[dict[str, Any]]:
    prompt = _THREAD_PROMPT.format(
        n=n,
        guidance=profile.get("generation_prompt_guidance", "")[:400],
    )
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS * n,
                temperature=_TEMPERATURE,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            tweets = _parse_json_shared(text)
            if isinstance(tweets, list):
                for t in tweets:
                    _validate(t)
                    t["likes"]    = int(t["likes"])
                    t["retweets"] = int(t["retweets"])
                return tweets
            raise ValueError("Expected JSON array for thread")
        except Exception as e:
            if attempt > _MAX_RETRIES:
                raise
            logger.warning("Thread gen attempt %d failed: %s", attempt, e)
            time.sleep(1)
    raise RuntimeError("Thread generation failed")


def _validate(tweet: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - tweet.keys()
    if missing:
        raise ValueError(f"Tweet JSON missing keys: {missing}")
    if not tweet.get("tweet_text"):
        raise ValueError("tweet_text is empty")
