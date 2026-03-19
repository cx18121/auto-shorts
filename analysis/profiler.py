"""
analysis/profiler.py — Build a style profile JSON from channel analysis data.

Public API:
    build_profile(channel_id, aggregates, include_visual=False) -> str
        Returns the path to the saved profile JSON.
"""

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

import config
from analysis.db import get_connection
from pipeline.claude_utils import strip_markdown_fences

logger = logging.getLogger(__name__)

_MODEL       = "claude-sonnet-4-6"
_BATCH_SIZE  = 7   # videos per analysis batch
_TOP_N       = 30  # max videos to analyse


def build_profile(channel_id: str, aggregates: dict[str, Any], include_visual: bool = False) -> str:
    """Generate a style profile JSON from a channel's analysed data.

    Args:
        channel_id:      Channel ID in the database.
        aggregates:      Dict returned by ranker.rank_channel().
        include_visual:  Whether to include visual/thumbnail analysis data.

    Returns:
        Path to the saved style profile JSON file.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    channel = _load_channel(channel_id)
    videos  = _load_top_videos(channel_id, _TOP_N, include_visual)
    logger.info("Building profile for %s using %d top videos", channel["name"], len(videos))

    # --- Batch analyses ---
    batch_results: list[str] = []
    for i in range(0, len(videos), _BATCH_SIZE):
        batch = videos[i:i + _BATCH_SIZE]
        logger.info("Analysing batch %d/%d (%d videos)…",
                    i // _BATCH_SIZE + 1, -(-len(videos) // _BATCH_SIZE), len(batch))
        result = _analyse_batch(client, batch, channel["name"], include_visual)
        batch_results.append(result)

    # --- Final merge ---
    logger.info("Merging %d batch results into unified profile…", len(batch_results))
    profile = _merge_batches(client, batch_results, channel, aggregates)

    # --- Save ---
    out_path = _save_profile(channel_id, channel["name"], profile)
    logger.info("Style profile saved → %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------

_BATCH_PROMPT = """You are analysing YouTube Shorts videos to identify what makes them successful.

Channel: {channel_name}

Here are {n} top-performing videos with their metadata and transcripts:

{video_data}

Analyse patterns across these videos and return a JSON object:
{{
  "hook_patterns": ["list 3-5 opening sentence structures that recur"],
  "narrative_structure": "how stories/content are typically built",
  "tone": "voice and tone description",
  "vocabulary_notes": "notable word choices, phrases, style markers",
  "emotional_triggers": ["emotions targeted: outrage/curiosity/relatability/humor/etc"],
  "topic_categories": ["ranked topic types from most to least common"],
  "title_patterns": ["title formulas or structures that appear"],
  "visual_patterns": "any patterns from visual/thumbnail analysis if provided",
  "top_performer_traits": "what specifically separates these top videos from average"
}}

Return only the JSON object."""


def _format_video_for_batch(v: dict[str, Any], include_visual: bool) -> str:
    parts = [
        f"Title: {v['title']}",
        f"Views: {v['view_count']:,}  Likes: {v['like_count']:,}  Duration: {v['duration_seconds']}s",
        f"Performance score: {v['performance_score']:.2f}x channel average",
    ]
    if v.get("transcript"):
        transcript_snippet = v["transcript"][:800]
        parts.append(f"Transcript excerpt: {transcript_snippet}")
    if include_visual and v.get("visual_analysis"):
        try:
            va = json.loads(v["visual_analysis"])
            parts.append(f"Visual style: {va.get('overall_visual_style', '')}")
            parts.append(f"Background: {va.get('background_type', '')}  Pace: {va.get('editing_pace', '')}")
        except (json.JSONDecodeError, TypeError):
            pass
    if include_visual and v.get("thumbnail_analysis"):
        try:
            ta = json.loads(v["thumbnail_analysis"])
            parts.append(f"Thumbnail: {ta.get('effectiveness', '')}")
        except (json.JSONDecodeError, TypeError):
            pass
    return "\n".join(parts)


def _analyse_batch(
    client: anthropic.Anthropic,
    videos: list[dict[str, Any]],
    channel_name: str,
    include_visual: bool,
) -> str:
    video_data = "\n\n---\n\n".join(
        _format_video_for_batch(v, include_visual) for v in videos
    )
    prompt = _BATCH_PROMPT.format(
        channel_name=channel_name,
        n=len(videos),
        video_data=video_data,
    )
    return _claude_text_call(client, prompt, max_tokens=2048)


# ---------------------------------------------------------------------------
# Profile merge
# ---------------------------------------------------------------------------

_MERGE_PROMPT = """You are building a final style profile for a YouTube Shorts channel.

Channel: {channel_name}
Subscribers: {subscribers:,}
Videos analysed: {num_videos}

Channel statistics:
- Avg duration (top performers): {avg_duration_top:.0f}s
- Avg duration (all videos): {avg_duration_all:.0f}s
- Posting frequency: every {posting_freq:.1f} days
- Best performing hours (UTC): {best_hours}
- Best performing days: {best_days}
- Common tags: {top_tags}
- Common title words: {title_words}

Batch analysis results:
{batch_results}

Using all of the above, produce a comprehensive style profile as a JSON object matching exactly this schema:
{{
  "channel_name": "{channel_name}",
  "format_detected": "storytelling or tweets or other",
  "analyzed_at": "{today}",
  "num_videos_analyzed": {num_videos},
  "content_style": {{
    "hook_patterns": ["array of hook structures that work"],
    "narrative_structure": "description",
    "tone": "description",
    "vocabulary_notes": "description",
    "emotional_triggers": ["array"],
    "topic_categories": ["ranked array"],
    "ideal_word_count": {{"min": int, "max": int}},
    "ideal_duration_seconds": {{"min": int, "max": int}}
  }},
  "visual_style": {{
    "text_overlay_format": "description",
    "background_type": "description",
    "color_palette": "description",
    "editing_pace": "fast/medium/slow with description",
    "face_on_screen": "yes/no/sometimes",
    "recurring_elements": ["array"]
  }},
  "title_patterns": {{
    "avg_length": int,
    "common_structures": ["array of title formulas"],
    "power_words": ["array"]
  }},
  "thumbnail_patterns": {{
    "style": "description",
    "text_usage": "description",
    "dominant_colors": ["array"],
    "emotional_tone": "description"
  }},
  "posting_strategy": {{
    "best_days": ["array"],
    "best_hours": ["array"],
    "avg_posting_frequency_days": float
  }},
  "generation_prompt_guidance": "A paragraph written as direct instructions to a content generator. Capture the essence of what makes this channel's content work — specific hooks, tone, emotional beats, structure. Should be injected directly into generation prompts."
}}

Return only the JSON object, no other text."""


def _merge_batches(
    client: anthropic.Anthropic,
    batch_results: list[str],
    channel: Any,
    aggregates: dict[str, Any],
) -> dict[str, Any]:
    prompt = _MERGE_PROMPT.format(
        channel_name=channel["name"],
        subscribers=channel["subscriber_count"] or 0,
        num_videos=aggregates.get("num_top_performers", 0),
        avg_duration_top=aggregates.get("avg_duration_top_performers", 0),
        avg_duration_all=aggregates.get("avg_duration_all", 0),
        posting_freq=aggregates.get("avg_posting_frequency_days", 0),
        best_hours=aggregates.get("best_performing_hour_of_day", []),
        best_days=aggregates.get("best_performing_day_of_week", []),
        top_tags=", ".join(aggregates.get("most_common_tags", [])[:10]),
        title_words=", ".join(aggregates.get("most_common_title_words", [])[:15]),
        batch_results="\n\n===\n\n".join(batch_results),
        today=date.today().isoformat(),
    )

    for attempt in range(1, 4):
        try:
            text = _claude_text_call(client, prompt, max_tokens=4096)
            return json.loads(strip_markdown_fences(text))
        except json.JSONDecodeError as e:
            logger.warning("Profile merge returned invalid JSON (attempt %d): %s", attempt, e)
            if attempt == 3:
                return {"error": "invalid JSON", "raw": text[:500]}
            time.sleep(2 ** attempt)
    return {}


# ---------------------------------------------------------------------------
# File save
# ---------------------------------------------------------------------------

def _save_profile(channel_id: str, channel_name: str, profile: dict[str, Any]) -> str:
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in channel_name)
    filename = f"{safe_name}_{date.today().isoformat()}.json"
    out_path = config.STYLE_PROFILES_DIR / filename
    out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    # Also store in DB
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO style_profiles (channel_id, name, format, profile_json, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (channel_id, channel_name, profile.get("format_detected", "unknown"),
              json.dumps(profile)))

    return str(out_path)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _load_channel(channel_id: str) -> Any:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
    if not row:
        raise ValueError(f"Channel {channel_id} not in database")
    return row


def _load_top_videos(channel_id: str, top_n: int, include_visual: bool) -> list[dict[str, Any]]:
    cols = ("id, title, view_count, like_count, duration_seconds, "
            "performance_score, transcript")
    if include_visual:
        cols += ", visual_analysis, thumbnail_analysis"
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {cols} FROM videos WHERE channel_id=? AND is_top_performer=1 "
            f"ORDER BY performance_score DESC LIMIT ?",
            (channel_id, top_n),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Claude text call
# ---------------------------------------------------------------------------

def _claude_text_call(client: anthropic.Anthropic, prompt: str, max_tokens: int = 2048) -> str:
    for attempt in range(1, 4):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=max_tokens,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            logger.warning("Claude call failed (attempt %d): %s", attempt, e)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Claude call failed after retries")
