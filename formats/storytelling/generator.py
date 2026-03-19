"""
formats/storytelling/generator.py — Generate stories from a style profile via Claude Haiku.

Public API:
    generate_story(profile)                                   -> dict
    generate_batch(count, profile_path)                       -> list[dict]
    adapt_reddit_post(post, channel_slug, profile=None)       -> dict
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

import anthropic

import config
from pipeline.claude_utils import parse_json as _parse_json_shared

logger = logging.getLogger(__name__)

_MODEL       = "claude-haiku-4-5-20251001"
_TEMPERATURE = 0.85
_MAX_TOKENS  = 1024
_MAX_RETRIES = 2

_REQUIRED_KEYS = {"title", "hook_line", "story_text", "estimated_duration_seconds"}

# ---------------------------------------------------------------------------
# Niche tone directives (used when no style profile is available)
# ---------------------------------------------------------------------------
_NICHE_TONES: dict[str, str] = {
    "hypothetical-scenarios": (
        "Write in a contemplative, philosophical tone. "
        "Invite the listener to genuinely consider the scenario."
    ),
    "relationships": (
        "Write with warmth and empathy. "
        "Honor the emotional weight of the situation without being dramatic."
    ),
}

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
{feedback_block}
OUTPUT FORMAT — return exactly this JSON structure:
{{
  "title": "video title under 60 chars",
  "hook_line": "the opening sentence that grabs attention",
  "story_text": "the full narration text — written for TTS, natural speech rhythm, no markdown",
  "estimated_duration_seconds": integer
}}"""

# ---------------------------------------------------------------------------
# Reddit adaptation prompts
# ---------------------------------------------------------------------------
_REDDIT_SYSTEM_PROMPT = """\
You are a viral YouTube Shorts scriptwriter. You adapt real Reddit posts into \
short, compelling narration scripts optimised for text-to-speech over gameplay footage.

You always output valid JSON and nothing else. No markdown, no commentary, no code fences."""

_REDDIT_USER_PROMPT = """\
Adapt this Reddit post into a YouTube Short narration script.

TONE GUIDANCE:
{guidance}

STYLE NOTES:
- Tone: {tone}
- Opening style: {hook_patterns}
- Vocabulary notes: {vocabulary_notes}

DURATION AND LENGTH:
- Target duration: {dur_min}–{dur_max} seconds when read aloud at a natural pace
- Target word count: {word_min}–{word_max} words
{feedback_block}
SOURCE POST:
Title: {post_title}
Body: {post_body}

ADAPTATION RULES:
1. Keep the story's core facts and arc intact — do not invent events
2. Rewrite for natural spoken English — no markdown, no lists, no headers
3. Remove ALL Reddit-specific language: AITA, NTA, YTA, ESH, throwaway, subreddit, \
edit:, update:, OP, [removed], [deleted], "thanks for the awards", upvotes, downvotes
4. If the post opens strongly, keep that opening as the hook. If not, add a strong hook sentence.
5. If the post is too long, condense it — remove tangents, tighten sentences, keep the full arc
6. Generate a YouTube-optimised video title under 60 characters (NOT the Reddit post title)

OUTPUT FORMAT — return exactly this JSON:
{{
  "title": "YouTube title under 60 chars",
  "hook_line": "the opening sentence",
  "story_text": "full narration — natural speech, no markdown, {word_min}–{word_max} words",
  "estimated_duration_seconds": integer
}}"""


def generate_story(profile: dict[str, Any], feedback: str = "") -> dict[str, Any]:
    """Generate a single story from a style profile.

    Args:
        profile:  Style profile dict (loaded from JSON file).
        feedback: Optional rejection reason from a previous attempt to guide regeneration.

    Returns:
        Story dict with keys: title, hook_line, story_text, estimated_duration_seconds.

    Raises:
        RuntimeError: If valid JSON is not produced after MAX_RETRIES attempts.
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
            story = _parse_json_shared(text)
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


def adapt_reddit_post(
    post: dict[str, Any],
    channel_slug: str,
    profile: dict[str, Any] | None = None,
    feedback: str = "",
) -> dict[str, Any]:
    """Adapt a Reddit post into a narration-ready script via Claude Haiku.

    Args:
        post:         Backlog story row with keys: title, body (and optionally subreddit, score).
        channel_slug: Channel slug — used to look up niche tone defaults when no profile.
        profile:      Style profile dict if one exists; overrides niche defaults entirely.
        feedback:     Optional rejection reason from a previous attempt to guide regeneration.

    Returns:
        Script dict with keys: title, hook_line, story_text, estimated_duration_seconds.

    Raises:
        ValueError:   If the post body is fewer than 50 words.
        RuntimeError: If valid JSON is not produced after MAX_RETRIES attempts.
    """
    body = post.get("body", "")
    if len(body.split()) < 50:
        raise ValueError(
            f"Post body too short ({len(body.split())} words); minimum is 50 words."
        )

    # Truncate to 4000 chars to avoid context overflow with Haiku
    truncated_body = body[:4000]
    truncated_post = {**post, "body": truncated_body}

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = _build_reddit_prompt(truncated_post, channel_slug, profile, feedback=feedback)

    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                system=_REDDIT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            story = _parse_json_shared(text)
            _validate(story)
            logger.info(
                "Adapted Reddit post -> %r (est. %ds)",
                story["title"], story.get("estimated_duration_seconds", 0),
            )
            return story
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Adapt attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise RuntimeError(
                    f"Post adaptation failed after {_MAX_RETRIES + 1} attempts"
                ) from e
            time.sleep(1)
        except Exception as e:
            logger.warning("Claude call attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError("Post adaptation failed")


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
        guidance=profile.get("generation_prompt_guidance", "Write engaging, viral short stories."),
        hook_patterns=", ".join(cs.get("hook_patterns", [])[:3]),
        tone=cs.get("tone", "engaging and conversational"),
        emotional_triggers=", ".join(cs.get("emotional_triggers", ["curiosity", "surprise"])[:4]),
        topic_categories=", ".join(cs.get("topic_categories", [])[:4]),
        word_min=cs.get("ideal_word_count", {}).get("min", 80),
        word_max=cs.get("ideal_word_count", {}).get("max", 180),
        dur_min=cs.get("ideal_duration_seconds", {}).get("min", 30),
        dur_max=cs.get("ideal_duration_seconds", {}).get("max", 60),
        feedback_block=feedback_block,
    )


def _build_reddit_prompt(
    post: dict[str, Any],
    channel_slug: str,
    profile: dict[str, Any] | None,
    feedback: str = "",
) -> str:
    """Build the user message for Reddit post adaptation.

    When a style profile is provided it overrides niche defaults entirely.
    When no profile is present, niche tone is looked up from _NICHE_TONES.
    """
    if profile:
        cs = profile.get("content_style", {})
        guidance = profile.get("generation_prompt_guidance", "")
        tone = cs.get("tone", "engaging and conversational")
        hook_patterns = ", ".join(cs.get("hook_patterns", [])[:3])
        dur_min = cs.get("ideal_duration_seconds", {}).get("min", 45)
        dur_max = cs.get("ideal_duration_seconds", {}).get("max", 60)
        word_min = cs.get("ideal_word_count", {}).get("min", 100)
        word_max = cs.get("ideal_word_count", {}).get("max", 160)
        vocabulary_notes = profile.get("vocabulary_notes", "")
    else:
        tone_directive = _NICHE_TONES.get(
            channel_slug, "Write in an engaging, conversational tone."
        )
        guidance = tone_directive
        tone = tone_directive
        hook_patterns = "strong opening question or statement"
        dur_min, dur_max = 45, 60
        word_min, word_max = 100, 160
        vocabulary_notes = ""

    feedback_block = (
        f"\nPREVIOUS ATTEMPT FEEDBACK (fix these issues in your next version):\n{feedback}\n"
        if feedback else ""
    )
    return _REDDIT_USER_PROMPT.format(
        guidance=guidance,
        tone=tone,
        hook_patterns=hook_patterns,
        dur_min=dur_min,
        dur_max=dur_max,
        word_min=word_min,
        word_max=word_max,
        vocabulary_notes=vocabulary_notes,
        post_title=post.get("title", ""),
        post_body=post.get("body", ""),
        feedback_block=feedback_block,
    )


def _validate(story: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - story.keys()
    if missing:
        raise ValueError(f"Story JSON missing keys: {missing}")
    if not story.get("story_text"):
        raise ValueError("story_text is empty")
