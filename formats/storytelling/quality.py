"""
formats/storytelling/quality.py — Score generated stories with Claude Sonnet.

Public API:
    check_quality(story, profile) -> dict
"""

import json
import logging
import time
from typing import Any

import anthropic

import config
from pipeline.claude_utils import strip_markdown_fences

logger = logging.getLogger(__name__)

_MODEL          = "claude-sonnet-4-6"
_TEMPERATURE    = 0.3
_PASS_THRESHOLD = 7.0
_MAX_RETRIES    = 3

_SYSTEM_PROMPT = """\
You are a quality evaluator for viral YouTube Shorts scripts. \
You score scripts against a channel style profile and return only valid JSON."""

_USER_PROMPT = """\
Evaluate this YouTube Shorts story against the channel style profile.

STYLE PROFILE GUIDANCE:
{guidance}

TARGET TONE: {tone}
TARGET EMOTIONAL TRIGGERS: {emotional_triggers}

STORY TO EVALUATE:
Title: {title}
Hook: {hook_line}
Story: {story_text}

Score each dimension 1–10 and return exactly this JSON:
{{
  "hook_strength": int,
  "coherence": int,
  "engagement": int,
  "length_appropriateness": int,
  "style_match": int,
  "overall": float,
  "reason": "1-2 sentence explanation of the main strengths or weaknesses",
  "passed": bool
}}

- overall = weighted average: hook_strength*0.3 + engagement*0.25 + coherence*0.2 + style_match*0.15 + length_appropriateness*0.1
- passed = true if overall >= {threshold}"""


def check_quality(story: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Score a generated story against the style profile.

    Args:
        story:   Story dict from generator.generate_story().
        profile: Style profile dict.

    Returns:
        Quality dict with scores, overall, reason, and passed flag.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    cs = profile.get("content_style", {})

    prompt = _USER_PROMPT.format(
        guidance=profile.get("generation_prompt_guidance", "")[:500],
        tone=cs.get("tone", ""),
        emotional_triggers=", ".join(cs.get("emotional_triggers", [])[:4]),
        title=story.get("title", ""),
        hook_line=story.get("hook_line", ""),
        story_text=story.get("story_text", "")[:600],
        threshold=_PASS_THRESHOLD,
    )

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=512,
                temperature=_TEMPERATURE,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = strip_markdown_fences(resp.content[0].text)
            result = json.loads(text)
            # Ensure passed reflects threshold even if Claude got it wrong
            result["passed"] = float(result.get("overall", 0)) >= _PASS_THRESHOLD
            logger.info(
                "Quality check: overall=%.1f  passed=%s  reason=%s",
                result.get("overall", 0), result["passed"], result.get("reason", "")[:80],
            )
            return result
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Quality check attempt %d failed: %s", attempt, e)
            if attempt == _MAX_RETRIES:
                return {"overall": 0.0, "passed": False, "reason": f"evaluation error: {e}"}
            time.sleep(1)
        except Exception as e:
            logger.warning("Claude quality call failed (attempt %d): %s", attempt, e)
            if attempt == _MAX_RETRIES:
                return {"overall": 0.0, "passed": False, "reason": str(e)}
            time.sleep(2 ** attempt)

    return {"overall": 0.0, "passed": False, "reason": "all attempts failed"}
