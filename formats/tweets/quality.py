"""
formats/tweets/quality.py — Score generated tweets with Claude Sonnet.

Public API:
    check_quality(tweet, profile) -> dict
"""

import json
import logging
import time
from typing import Any

import anthropic

import config

logger = logging.getLogger(__name__)

_MODEL          = "claude-sonnet-4-6"
_TEMPERATURE    = 0.3
_PASS_THRESHOLD = 7.0

_SYSTEM_PROMPT = """\
You are a quality evaluator for viral YouTube Shorts tweet screenshot content. \
Return only valid JSON, nothing else."""

_USER_PROMPT = """\
Evaluate this tweet for use as a YouTube Shorts screenshot video.

CHANNEL STYLE GUIDANCE:
{guidance}

TWEET TO EVALUATE:
@{username}: {tweet_text}
Likes: {likes:,}  Retweets: {retweets:,}
Hook type: {hook_type}

Score each dimension 1–10:
- punchiness: how immediately grabbing the text is
- originality: how fresh and non-generic the take feels
- screenshot_worthiness: would a viewer actually screenshot and share this?
- style_match: how well it fits the channel style

Return exactly this JSON:
{{
  "punchiness": int,
  "originality": int,
  "screenshot_worthiness": int,
  "style_match": int,
  "overall": float,
  "reason": "1-2 sentence explanation",
  "passed": bool
}}

- overall = (punchiness*0.3 + screenshot_worthiness*0.3 + originality*0.2 + style_match*0.2)
- passed = true if overall >= {threshold}"""


def check_quality(tweet: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Score a generated tweet against the style profile.

    Args:
        tweet:   Tweet dict from generator.generate_tweet().
        profile: Style profile dict.

    Returns:
        Quality dict with scores, overall, reason, and passed flag.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = _USER_PROMPT.format(
        guidance=profile.get("generation_prompt_guidance", "")[:400],
        username=tweet.get("username", ""),
        tweet_text=tweet.get("tweet_text", ""),
        likes=int(tweet.get("likes", 0)),
        retweets=int(tweet.get("retweets", 0)),
        hook_type=tweet.get("hook_type", ""),
        threshold=_PASS_THRESHOLD,
    )

    for attempt in range(1, 4):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=512,
                temperature=_TEMPERATURE,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            result["passed"] = float(result.get("overall", 0)) >= _PASS_THRESHOLD
            logger.info(
                "Tweet quality: overall=%.1f  passed=%s  reason=%s",
                result.get("overall", 0), result["passed"], result.get("reason", "")[:80],
            )
            return result
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Tweet quality check attempt %d failed: %s", attempt, e)
            if attempt == 3:
                return {"overall": 0.0, "passed": False, "reason": str(e)}
            time.sleep(1)
        except Exception as e:
            logger.warning("Claude quality call failed (attempt %d): %s", attempt, e)
            if attempt == 3:
                return {"overall": 0.0, "passed": False, "reason": str(e)}
            time.sleep(2 ** attempt)

    return {"overall": 0.0, "passed": False, "reason": "all attempts failed"}
