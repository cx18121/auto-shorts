"""
formats/storytelling/generator.py — Adapt Reddit posts into narration scripts via Claude Haiku.

Public API:
    adapt_reddit_post(post, channel_slug)       -> dict
"""

import json
import logging
import time
from typing import Any

import anthropic

import config
from pipeline.claude_utils import parse_json as _parse_json_shared

logger = logging.getLogger(__name__)

_MODEL       = "claude-haiku-4-5-20251001"
_TEMPERATURE = 0.85
_MAX_TOKENS  = 1024
_MAX_RETRIES = 2

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client

_REQUIRED_KEYS = {"title", "hook_line", "story_text", "estimated_duration_seconds", "description", "hashtags"}

# ---------------------------------------------------------------------------
# Niche tone directives (per-channel defaults)
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
{system_context}
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
  "title": "YouTube title under 60 chars, ends with '?', no ellipsis, no clickbait",
  "hook_line": "the opening sentence",
  "story_text": "full narration — natural speech, no markdown, {word_min}–{word_max} words",
  "estimated_duration_seconds": integer,
  "description": "2-3 sentences that CONTINUE the scenario from the title (do NOT repeat it), ends with a period, 150-400 chars, no hashtags",
  "hashtags": ["tag1", "tag2", "tag3"]
}}"""


def adapt_reddit_post(
    post: dict[str, Any],
    channel_slug: str,
    feedback: str = "",
) -> dict[str, Any]:
    """Adapt a Reddit post into a narration-ready script via Claude Haiku.

    Args:
        post:         Backlog story row with keys: title, body (and optionally subreddit, score).
        channel_slug: Channel slug — used to look up niche tone defaults from _NICHE_TONES.
        feedback:     Optional rejection reason from a previous attempt to guide regeneration.

    Returns:
        Script dict with keys: title, hook_line, story_text, estimated_duration_seconds,
        description, hashtags.

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

    client = _get_client()
    analytics_context = _get_analytics_context(channel_slug)
    prompt = _build_reddit_prompt(truncated_post, channel_slug, feedback=feedback, analytics_context=analytics_context)

    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                system=[{"type": "text", "text": _REDDIT_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
            text = ""
            for block in resp.content:
                if block.type == "text":
                    text = block.text.strip()
                    break
            if not text:
                raise ValueError("No TextBlock in Claude response")
            story = _parse_json_shared(text)
            _validate(story)
            logger.info(
                "Adapted Reddit post -> title=%r desc=%r hashtags=%s (est. %ds)",
                story["title"], story.get("description", "")[:50],
                story.get("hashtags", []),
                story.get("estimated_duration_seconds", 0),
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


def _get_analytics_context(channel: str) -> str:
    """Build analytics context string from video_insights data.

    Returns an empty string if no data is available yet.
    """
    try:
        from pipeline.db import get_connection
        from pipeline.analytics import get_generation_recommendations
        conn = get_connection()
        try:
            recs = get_generation_recommendations(conn, channel, days=30)
        finally:
            conn.close()
        title_hints = recs.get("title_hints", [])
        hook_style = recs.get("hook_style", "")
        hook_examples = recs.get("hook_examples", [])
        body_style = recs.get("body_style", "")
        preferred_bgs = recs.get("preferred_backgrounds", [])
        avoid = recs.get("avoid", [])

        if not title_hints and not hook_style:
            return ""

        parts = ["\nCHANNEL ANALYTICS (apply to title and full script):"]

        if title_hints:
            parts.append("TITLE HINTS:")
            for h in title_hints[:4]:
                parts.append(f"  - {h}")

        if hook_style:
            parts.append(f"\nHOOK STYLE (HIGHEST WEIGHT — first 5 seconds must grab attention):")
            parts.append(f"  - {hook_style}")
            if hook_examples:
                parts.append("  Examples from top-performing videos:")
                for ex in hook_examples[:3]:
                    parts.append(f"    - \"{ex}\"")

        if body_style:
            parts.append(f"\nBODY TRANSCRIPT STYLE:")
            parts.append(f"  - {body_style}")

        if preferred_bgs:
            parts.append(f"\nPREFERRED BACKGROUNDS: {', '.join(preferred_bgs)}")

        # New OAuth-enriched performance metrics
        if recs.get("avg_view_percentage"):
            parts.append(f"\nPERFORMANCE BENCHMARKS (from top videos):")
            parts.append(f"  - Avg watch duration: {recs['avg_view_duration_seconds']}s per view")
            parts.append(f"  - Avg retention rate: {recs['avg_view_percentage']}% of video")
            parts.append(f"  - Avg likes per video: {recs['avg_engagement_likes']}")
            parts.append(f"  - Top video views: {recs['top_view_count']:,}")
            parts.append(f"  - Videos analyzed: {recs['total_videos_analyzed']}")

        if avoid:
            parts.append(f"\nAVOID:")
            for a in avoid:
                parts.append(f"  - {a}")

        return "\n".join(parts)
    except Exception as exc:
        logger.warning("_get_analytics_context: failed for channel=%s — %s", channel, exc)
        return ""


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _build_reddit_prompt(
    post: dict[str, Any],
    channel_slug: str,
    feedback: str = "",
    analytics_context: str = "",
) -> str:
    """Build the user message for Reddit post adaptation using niche tone defaults."""
    tone_directive = _NICHE_TONES.get(
        channel_slug, "Write in an engaging, conversational tone."
    )
    guidance = tone_directive
    tone = tone_directive
    hook_patterns = "strong opening question or statement"
    vocabulary_notes = ""

    gen: dict = {}
    try:
        import config as _config
        ch = _config.CHANNELS.get(channel_slug)
        if ch:
            gen = ch.generation
    except Exception:
        pass
    dur_min  = gen.get("dur_min",  45)
    dur_max  = gen.get("dur_max",  60)
    word_min = gen.get("word_min", 100)
    word_max = gen.get("word_max", 160)

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
        system_context=analytics_context,
    )


def _validate(story: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - story.keys()
    if missing:
        raise ValueError(f"Story JSON missing keys: {missing}")
    if not story.get("story_text"):
        raise ValueError("story_text is empty")
    if not story.get("description"):
        raise ValueError("description is empty")
    if not isinstance(story.get("hashtags"), list):
        raise ValueError("hashtags must be a list")
    story_text = story["story_text"]
    for phrase in story.get("overlay_phrases", []):
        if phrase not in story_text:
            raise ValueError(
                f"overlay_phrase {phrase!r} is not a substring of story_text"
            )
