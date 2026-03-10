"""
formats/storytelling/generator.py — Generate stories from a style profile via Claude Haiku.

Public API:
    generate_story(profile)              -> dict
    generate_batch(count, profile_path)  -> list[dict]
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

import anthropic

import config

logger = logging.getLogger(__name__)

_MODEL       = "claude-haiku-4-5-20251001"
_TEMPERATURE = 0.85
_MAX_TOKENS  = 1024
_MAX_RETRIES = 2

_REQUIRED_KEYS = {"title", "hook_line", "story_text", "overlay_phrases", "estimated_duration_seconds"}

_SYSTEM_PROMPT = """\
You are a viral YouTube Shorts scriptwriter. You generate short, compelling stories \
optimised for text-to-speech narration over gameplay footage.

You always output valid JSON and nothing else. No markdown, no commentary, no code fences."""

_USER_PROMPT = """\
Generate a story for a YouTube Short based on this style profile:

CHANNEL STYLE GUIDANCE:
{guidance}

CONTENT STYLE:
- Hook patterns that work: {hook_patterns}
- Tone: {tone}
- Emotional triggers to use: {emotional_triggers}
- Topic categories: {topic_categories}
- Target word count: {word_min}–{word_max} words
- Target duration: {dur_min}–{dur_max} seconds

OUTPUT FORMAT — return exactly this JSON structure:
{{
  "title": "video title under 60 chars",
  "hook_line": "the opening sentence that grabs attention",
  "story_text": "the full narration text — written for TTS, natural speech rhythm, no markdown",
  "overlay_phrases": ["5–15 short key phrases that can be shown as text overlays"],
  "estimated_duration_seconds": integer
}}"""


def generate_story(profile: dict[str, Any]) -> dict[str, Any]:
    """Generate a single story from a style profile.

    Args:
        profile: Style profile dict (loaded from JSON file).

    Returns:
        Story dict with keys: title, hook_line, story_text, overlay_phrases,
        estimated_duration_seconds.

    Raises:
        RuntimeError: If valid JSON is not produced after MAX_RETRIES attempts.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = _build_prompt(profile)

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
            story = _parse_json(text)
            _validate(story)
            logger.info("Generated story: %r (est. %ds)",
                        story["title"], story.get("estimated_duration_seconds", 0))
            return story
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Story generation attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise RuntimeError(f"Story generation failed after {_MAX_RETRIES + 1} attempts") from e
            time.sleep(1)
        except Exception as e:
            logger.warning("Claude call attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError("Story generation failed")


def generate_batch(count: int, profile_path: str) -> list[dict[str, Any]]:
    """Generate multiple stories from a profile file.

    Args:
        count:        Number of stories to generate.
        profile_path: Path to style profile JSON file.

    Returns:
        List of story dicts (may be fewer than count if some fail).
    """
    profile = json.loads(Path(profile_path).read_text())
    stories: list[dict[str, Any]] = []
    for i in range(count):
        try:
            story = generate_story(profile)
            stories.append(story)
            logger.info("Batch progress: %d/%d stories generated", len(stories), count)
        except Exception as e:
            logger.error("Failed to generate story %d/%d: %s", i + 1, count, e)
    return stories


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _build_prompt(profile: dict[str, Any]) -> str:
    cs = profile.get("content_style", {})
    return _USER_PROMPT.format(
        guidance=profile.get("generation_prompt_guidance", "Write engaging, viral short stories."),
        hook_patterns=", ".join(cs.get("hook_patterns", [])[:3]),
        tone=cs.get("tone", "engaging and conversational"),
        emotional_triggers=", ".join(cs.get("emotional_triggers", ["curiosity", "surprise"])[:4]),
        topic_categories=", ".join(cs.get("topic_categories", [])[:4]),
        word_min=cs.get("ideal_word_count", {}).get("min", 80),
        word_max=cs.get("ideal_word_count", {}).get("max", 180),
        dur_min=cs.get("ideal_duration_seconds", {}).get("min", 30),
        dur_max=cs.get("ideal_duration_seconds", {}).get("max", 60),
    )


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _validate(story: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - story.keys()
    if missing:
        raise ValueError(f"Story JSON missing keys: {missing}")
    if not story.get("story_text"):
        raise ValueError("story_text is empty")
