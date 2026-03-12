# Phase 3: AI Story Generation - Research

**Researched:** 2026-03-12
**Domain:** Claude API prompt engineering, Reddit post adaptation, TTS script formatting
**Confidence:** HIGH (all findings grounded in existing codebase and established project patterns)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Script adaptation approach:**
- Clean up verbatim — keep the original Reddit text mostly intact, strip markdown, fix grammar, add TTS-friendly phrasing
- Strip all Reddit-specific references ('AITA', 'throwaway', subreddit mentions, 'edit: wow this blew up') — story stands on its own
- When posts are too long for target duration: condense to fit — Claude compresses the story, removing tangents and tightening sentences while keeping the full arc
- Hook line: only add if needed — Claude judges whether the post already opens strong; if not, prepend a hook

**Niche tone mapping:**
- Hard-coded per niche in the generator code, short 1-2 sentence directives
- Tone guides overall feel only, not word-level choices
- Only storytelling niches get tone mappings (hypothetical-scenarios, relationships)
- Finance niche excluded — it uses tweet format, no AI story generation

**Output script format:**
- Match existing generator.py structure: `title`, `hook_line`, `story_text`, `overlay_phrases`, `estimated_duration_seconds`
- Title: Claude generates a YouTube-optimized title (under 60 chars), not the Reddit post title
- Overlay phrases: must be exact substrings of `story_text` — ensures alignment with TTS timestamps
- Target duration: 45-60 seconds (tighter than the 30-90s requirement range; sweet spot for YouTube Shorts algorithm)

**Style profile integration:**
- When a style profile exists for a channel, it overrides niche defaults entirely — profile is the authority
- Fields used: `generation_prompt_guidance`, `hook_patterns`, `tone`, `emotional_triggers`, `topic_categories`, `ideal_word_count`, `ideal_duration_seconds`, plus `vocabulary_notes`
- If profile specifies `ideal_duration_seconds`, use that instead of the 45-60s default
- Profile path stored as `style_profile` field in `channels.yaml` per channel
- If no profile exists, fall back to hard-coded niche tone defaults

### Claude's Discretion
- Exact prompt engineering and system prompt wording
- How to handle edge cases (posts with images referenced, deleted content, etc.)
- Whether to modify the existing `generator.py` or create a new function alongside it

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GEN-01 | Claude (Haiku) can generate storytelling scripts from Reddit post title + body | New `adapt_reddit_post()` function in `formats/storytelling/generator.py`; same API pattern as existing `generate_story()` |
| GEN-02 | Generated scripts match the niche tone and are formatted for TTS (no markdown, natural speech) | Hard-coded `_NICHE_TONES` dict for hypothetical-scenarios and relationships; system prompt instructs no markdown; validated by `_validate()` |
| GEN-03 | Generation is guided by style profile if one exists for the channel | `style_profile` field added to `ChannelConfig`; profile overrides niche defaults when present; `_build_reddit_prompt()` branches on profile presence |
</phase_requirements>

---

## Summary

Phase 3 adds a second generation mode to `formats/storytelling/generator.py`: adapting real Reddit posts into narration-ready scripts rather than generating stories from scratch. The existing `generate_story()` path (profile-driven original stories) is unchanged. The new `adapt_reddit_post()` function takes a Reddit post dict (title, body, channel slug) and returns the same five-key script dict the TTS → overlay → assembler pipeline already consumes.

The core technical work is prompt engineering. Claude Haiku must receive the raw Reddit post and produce clean TTS-ready narration: no markdown, no subreddit jargon, natural sentence flow, overlay phrases as exact substrings, and duration in the 45-60s sweet spot. Niche tone is injected via a hard-coded lookup table. When a style profile is loaded for the channel, it replaces the niche defaults entirely.

A new `style_profile` field is needed on `ChannelConfig` (optional, defaults to empty string). The CLI's `generate` command gains a `--from-backlog` flag to pull approved stories from the DB and route them through the new adapter. The backlog item is marked `used` after successful generation.

**Primary recommendation:** Add `adapt_reddit_post(post: dict, channel_slug: str, profile: dict | None) -> dict` to the existing `formats/storytelling/generator.py`. Do not create a separate file — the output schema is identical and sharing `_validate()`, `_parse_json()`, and the Anthropic client init avoids duplication.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | installed (claude-haiku-4-5-20251001) | Claude API calls for script generation | Already used in generator.py and quality.py — same client, same retry pattern |
| sqlite3 | stdlib | Read approved stories from backlog_stories | Already used across the pipeline via `pipeline/backlog.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| logging | stdlib | Per-module logger via `logging.getLogger(__name__)` | Every module in the project uses this pattern |
| json | stdlib | Parse Claude JSON output | Same as existing `_parse_json()` in generator.py |
| time | stdlib | Exponential backoff on retries | Same as existing retry loops |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Haiku for generation | Sonnet for generation | Sonnet produces higher quality but costs ~20x more; Haiku at temp 0.85 is the established project standard for generation |
| Hard-coded niche tones | Dynamic tone from channel config | Config-driven is more flexible but adds YAML fields and validation complexity; 2 niches makes hard-coding practical |

**No new dependencies required.** All libraries are already installed.

---

## Architecture Patterns

### Recommended Project Structure
No new files required. Changes are confined to:
```
formats/storytelling/
└── generator.py        # Add: adapt_reddit_post(), _build_reddit_prompt(), _NICHE_TONES

config.py               # Add: style_profile field to ChannelConfig

channels.yaml.example   # Add: style_profile field (optional, empty default)

main.py                 # Add: --from-backlog flag to generate command
                        # Add: _generate_storytelling_from_backlog() pipeline branch
```

### Pattern 1: Two-Function Generator Module
**What:** `generator.py` exposes two public functions with the same return type. `generate_story(profile)` already exists; `adapt_reddit_post(post, channel_slug, profile)` is new.
**When to use:** When a module has two generation modes that share output schema, validation, and retry infrastructure.
**Example:**
```python
# Mirrors the existing generate_story() structure exactly
def adapt_reddit_post(
    post: dict[str, Any],
    channel_slug: str,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt a Reddit post into a narration-ready script.

    Args:
        post:         Backlog story row with keys: title, body, subreddit, score.
        channel_slug: Channel slug — used to look up niche tone defaults.
        profile:      Style profile dict if one exists; overrides niche defaults.

    Returns:
        Script dict with keys: title, hook_line, story_text, overlay_phrases,
        estimated_duration_seconds.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = _build_reddit_prompt(post, channel_slug, profile)

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
            logger.info("Adapted Reddit post → %r (est. %ds)",
                        story["title"], story.get("estimated_duration_seconds", 0))
            return story
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Adapt attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise RuntimeError(f"Post adaptation failed after {_MAX_RETRIES + 1} attempts") from e
            time.sleep(1)
        except Exception as e:
            logger.warning("Claude call attempt %d failed: %s", attempt, e)
            if attempt > _MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Post adaptation failed")
```

### Pattern 2: Niche Tone Lookup Table
**What:** Module-level dict mapping channel slug to a short tone directive string. Profile overrides it entirely when present.
**When to use:** When there are a small, fixed number of variants that don't warrant YAML configuration.
**Example:**
```python
# Hard-coded per the CONTEXT.md decision — 1-2 sentences per niche
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
```

### Pattern 3: Reddit Post Prompt Construction
**What:** `_build_reddit_prompt()` assembles the user message. When `profile` is provided, it uses profile fields (same as `_build_prompt()`). When `profile` is None, it uses the niche tone lookup.
**When to use:** This is the only place niche tone vs. profile branching happens.
**Example:**
```python
def _build_reddit_prompt(
    post: dict[str, Any],
    channel_slug: str,
    profile: dict[str, Any] | None,
) -> str:
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
        tone_directive = _NICHE_TONES.get(channel_slug, "Write in an engaging, conversational tone.")
        guidance = tone_directive
        tone = tone_directive
        hook_patterns = "strong opening question or statement"
        dur_min, dur_max = 45, 60
        word_min, word_max = 100, 160
        vocabulary_notes = ""

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
    )
```

### Pattern 4: ChannelConfig style_profile Field
**What:** Optional string field on `ChannelConfig` storing the path to a style profile JSON. Empty string means "use niche defaults".
**When to use:** Any code that needs to load a profile should check `channel_cfg.style_profile` first.
**Example:**
```python
# In config.py ChannelConfig dataclass — add after existing fields:
style_profile: str = ""
```

The `__post_init__` validation does NOT need to require this field — it is genuinely optional.

### Pattern 5: CLI --from-backlog Flag
**What:** New flag on `generate --format storytelling` that pulls the oldest approved story from `backlog_stories`, adapts it, runs TTS + assembler, and marks it `used`.
**When to use:** This is the primary production path; `--profile` remains for standalone testing.
**Example flow in main.py:**
```python
def _generate_storytelling_from_backlog(
    count: int,
    channel_cfg: config.ChannelConfig,
) -> list[str]:
    from analysis.db import get_connection
    from pipeline.backlog import get_approved_stories, mark_story_used
    from formats.storytelling.generator import adapt_reddit_post
    from formats.storytelling.quality import check_quality

    conn = get_connection()
    profile = None
    if channel_cfg.style_profile:
        profile = json.loads(Path(channel_cfg.style_profile).read_text())

    stories = get_approved_stories(conn, channel_cfg.slug)
    # ... iterate, call adapt_reddit_post, run pipeline, mark_story_used
```

### Anti-Patterns to Avoid
- **Passing raw Reddit body unsanitized to TTS:** Reddit posts contain markdown (`**bold**`, `>quote`, `---`), image references (`[View Poll]`), and junk lines (`edit: wow this blew up`). The prompt must explicitly instruct Claude to strip all of this.
- **Overlay phrases that are not exact substrings:** The overlay module (`pipeline/overlay.py`) relies on word-level TTS timestamps to position phrases. If Claude paraphrases rather than lifts exact text, phrase alignment breaks. The prompt must reinforce this with an explicit example showing correct vs. incorrect behavior.
- **Using Reddit post title as video title:** Post titles often contain subreddit conventions (`[AITA]`, `UPDATE:`, `TW:`). The output title must be Claude-generated and YouTube-optimized.
- **Not constraining word count:** Claude will happily generate 400-word scripts for 45s targets. The prompt must specify both word range and duration range — Claude cross-checks them better when given both.
- **Creating a new file for adapt_reddit_post:** The output schema is identical to `generate_story()`. Splitting into a separate file means duplicating `_validate()`, `_parse_json()`, retry logic, and the Anthropic client. Add the function to the existing module.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reddit markdown stripping | Custom regex stripper | Instruct Claude in the prompt | Claude handles edge cases (nested lists, code blocks, table formatting) better than regex; and it understands context (don't remove content, just reformat) |
| TTS duration estimation | Word count × WPM calculation | Claude's `estimated_duration_seconds` output + existing ElevenLabs TTS | ElevenLabs speaking rate varies by voice and content; let Claude estimate, downstream TTS confirms actual duration |
| JSON output extraction | Complex parsing | Existing `_parse_json()` from generator.py | Already handles code-fenced JSON, whitespace, BOM |
| API retry logic | New retry infrastructure | Existing `time.sleep(2 ** attempt)` pattern from generator.py | Consistent across all Claude calls in the project |

**Key insight:** The prompt is the product. Every "cleaning" step (strip junk, fix phrasing, estimate duration, choose phrases) is better handled by the LLM in a single pass than by a multi-step preprocessing pipeline.

---

## Common Pitfalls

### Pitfall 1: Overlay Phrases Fail Substring Check at Runtime
**What goes wrong:** Claude invents a slightly paraphrased version of a key sentence as an overlay phrase. The overlay module can't match it to a TTS timestamp range and crashes or silently skips it.
**Why it happens:** The model prioritizes making the phrase "punchy" over copying it verbatim.
**How to avoid:** In the prompt, include an explicit constraint: "Each overlay phrase MUST be copied verbatim from story_text — do not paraphrase or shorten." Optionally add a `_validate()` check that asserts `phrase in story["story_text"]` for each phrase.
**Warning signs:** Overlay phrases contain em-dashes, ellipsis, or comma differences that don't match story_text.

### Pitfall 2: Reddit Jargon Leaks Through
**What goes wrong:** The output contains "AITA", "NTA", "throwaway account", "edit: thanks for the awards", or direct subreddit callouts. These sound bizarre in TTS narration.
**Why it happens:** Claude is cleaning up formatting but the model sees these as normal English words and leaves them.
**How to avoid:** Provide an explicit blacklist in the prompt: "Remove: AITA, NTA, ESH, YTA, NTA, throwaway, reddit, subreddit, upvote, downvote, edit:, update:, [removed], [deleted], OP."
**Warning signs:** Unit tests that assert `"AITA" not in story_text` fail.

### Pitfall 3: Posts Too Long Cause Haiku to Truncate Mid-Story
**What goes wrong:** A 1200-word Reddit post sent verbatim hits Haiku's context or attention limits, and the output story cuts off abruptly or loses the ending arc.
**Why it happens:** Haiku has a shorter effective attention window for long-form rewriting tasks compared to Sonnet.
**How to avoid:** Truncate the raw post body to a maximum of 800 words before inserting into the prompt. The condensation instruction handles shortening the story; the truncation prevents context overflow. `post["body"][:4000]` (chars, not words) is a safe ceiling.
**Warning signs:** `estimated_duration_seconds` is accurate but story_text ends mid-sentence or misses the resolution.

### Pitfall 4: Missing `style_profile` Field Breaks ChannelConfig Loading
**What goes wrong:** Adding `style_profile` to `ChannelConfig` without a default causes existing `channels.yaml` files (which don't have the field) to raise `TypeError: __init__() got an unexpected keyword argument`.
**Why it happens:** The `ChannelConfig` dataclass uses `**data` unpacking from YAML, so missing fields are fine but extra fields raise TypeError without a default.
**How to avoid:** Always use `style_profile: str = ""` — an empty string is falsy and signals "use niche defaults". No change needed in existing YAML files.
**Warning signs:** `python main.py --channel hypothetical-scenarios backlog-status` raises TypeError on startup.

### Pitfall 5: `--from-backlog` with Empty Backlog Fails Silently
**What goes wrong:** `cmd_generate` with `--from-backlog` is called but there are zero approved stories. The loop iterates zero times and produces zero videos with no user-facing explanation.
**Why it happens:** `get_approved_stories()` returns an empty list, which is valid.
**How to avoid:** After calling `get_approved_stories()`, immediately check `if not stories: logger.warning(...); return []` and print a clear message.
**Warning signs:** User runs generate and gets "Generated 0/3 videos:" with no explanation.

---

## Code Examples

### Reddit Adaptation System Prompt
```python
# Source: internal design — mirrors _SYSTEM_PROMPT in existing generator.py
_SYSTEM_PROMPT = """\
You are a viral YouTube Shorts scriptwriter. You adapt real Reddit posts into \
short, compelling narration scripts optimised for text-to-speech over gameplay footage.

You always output valid JSON and nothing else. No markdown, no commentary, no code fences."""
```

### Reddit Adaptation User Prompt Template
```python
# Source: internal design — full prompt structure for adapt_reddit_post
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
7. overlay_phrases: pick 5–12 short punchy phrases to display as text overlays — \
   each phrase MUST be copied VERBATIM from story_text, do not paraphrase

OUTPUT FORMAT — return exactly this JSON:
{{
  "title": "YouTube title under 60 chars",
  "hook_line": "the opening sentence",
  "story_text": "full narration — natural speech, no markdown, {word_min}–{word_max} words",
  "overlay_phrases": ["phrase from story_text", "another phrase from story_text"],
  "estimated_duration_seconds": integer
}}"""
```

### Validation Enhancement for Overlay Phrases
```python
# Source: internal design — extends existing _validate() in generator.py
def _validate(story: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - story.keys()
    if missing:
        raise ValueError(f"Story JSON missing keys: {missing}")
    if not story.get("story_text"):
        raise ValueError("story_text is empty")
    # Phase 3 addition: overlay phrases must be exact substrings
    story_text = story["story_text"]
    for phrase in story.get("overlay_phrases", []):
        if phrase and phrase not in story_text:
            raise ValueError(
                f"overlay_phrase not a substring of story_text: {phrase!r}"
            )
```

### Loading Style Profile from ChannelConfig
```python
# Source: internal design — pattern used in _generate_storytelling_from_backlog
import json
from pathlib import Path

def _load_profile(channel_cfg: config.ChannelConfig) -> dict | None:
    """Return style profile dict if configured, else None."""
    if channel_cfg.style_profile:
        path = Path(channel_cfg.style_profile)
        if path.exists():
            return json.loads(path.read_text())
        logger.warning("style_profile path not found: %s", channel_cfg.style_profile)
    return None
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Original story generation only (`generate_story`) | Add Reddit-post adaptation (`adapt_reddit_post`) | Phase 3 | Backlog approved posts become the primary content source; original generation is the fallback |
| `ChannelConfig` has no profile awareness | `style_profile` field added | Phase 3 | Generator modules can load and apply profile without passing extra args through CLI layers |

**Deprecated/outdated:**
- None introduced by this phase. Existing `generate_story()` and `--profile` flag remain fully operational.

---

## Open Questions

1. **Should `adapt_reddit_post` call the quality checker automatically?**
   - What we know: `generate_story()` does NOT call quality internally — the caller (`_generate_with_quality` in main.py) wraps it
   - What's unclear: Whether the Reddit adapter should follow the same pattern (caller wraps) or internally quality-gate
   - Recommendation: Follow the same pattern as `generate_story()` — keep the function pure, let the caller decide on quality checking. This preserves testability.

2. **How many approved stories should `--from-backlog` consume per run?**
   - What we know: `--count` already exists on the generate command
   - What's unclear: Whether to consume exactly `count` stories or consume one at a time
   - Recommendation: Consume up to `count` stories, same as the existing generate loop. If fewer than `count` are approved, log a warning and return what was produced.

3. **Edge case: Reddit post body is empty or very short (< 50 words)**
   - What we know: The quality filter in Phase 2 enforces `min_words: 400` for storytelling niches — so this should not reach the generator
   - What's unclear: Whether to add a defensive check anyway
   - Recommendation: Add a guard (`if len(post.get("body", "").split()) < 50: raise ValueError(...)`) for defensive coding, but do not rely on it as the primary filter.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (confirmed installed — test files use unittest.TestCase, run via pytest) |
| Config file | none — pytest auto-discovers tests/ directory |
| Quick run command | `pytest tests/test_story_generator.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEN-01 | `adapt_reddit_post()` returns dict with all 5 required keys | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_output_schema -x` | ❌ Wave 0 |
| GEN-01 | `adapt_reddit_post()` strips AITA/NTA/throwaway jargon | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_reddit_jargon_stripped -x` | ❌ Wave 0 |
| GEN-01 | `adapt_reddit_post()` estimated duration is 30-90s (acceptance range) | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_duration_in_range -x` | ❌ Wave 0 |
| GEN-02 | Niche tone injected when no profile present (hypothetical-scenarios) | unit | `pytest tests/test_story_generator.py::TestBuildRedditPrompt::test_niche_tone_hypothetical -x` | ❌ Wave 0 |
| GEN-02 | Niche tone injected when no profile present (relationships) | unit | `pytest tests/test_story_generator.py::TestBuildRedditPrompt::test_niche_tone_relationships -x` | ❌ Wave 0 |
| GEN-02 | Output `story_text` contains no markdown characters | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_no_markdown -x` | ❌ Wave 0 |
| GEN-03 | Style profile fields override niche defaults in prompt | unit | `pytest tests/test_story_generator.py::TestBuildRedditPrompt::test_profile_overrides_niche -x` | ❌ Wave 0 |
| GEN-03 | `ChannelConfig` accepts `style_profile` field | unit | `pytest tests/test_config_channels.py::TestChannelConfig::test_style_profile_optional -x` | ❌ Wave 0 (extend existing file) |
| GEN-01 | overlay_phrases are all exact substrings of story_text | unit | `pytest tests/test_story_generator.py::TestValidate::test_overlay_phrases_are_substrings -x` | ❌ Wave 0 |

> Note: GEN-01/GEN-02/GEN-03 tests that call the real Claude API are integration tests and are excluded from automated runs. The unit tests above mock the Anthropic client using `unittest.mock.patch`.

### Sampling Rate
- **Per task commit:** `pytest tests/test_story_generator.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_story_generator.py` — covers GEN-01, GEN-02, GEN-03 (new file, mock Anthropic client)
- [ ] `tests/test_config_channels.py` — extend with `test_style_profile_optional` for GEN-03
- [ ] No new framework install needed — pytest already present

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `formats/storytelling/generator.py` — output schema, retry pattern, `_parse_json`, `_validate`, model constants
- Direct code inspection of `pipeline/backlog.py` — `get_approved_stories` API, row schema (id, channel, subreddit, title, body, score, word_count)
- Direct code inspection of `config.py` — `ChannelConfig` dataclass, field structure, `__post_init__` validation
- Direct code inspection of `main.py` — `_generate_with_quality` pattern, `cmd_generate` dispatch, `_generate_storytelling` flow
- Direct code inspection of `channels.yaml.example` — confirmed storytelling niches: hypothetical-scenarios, relationships; finance-hustle is format=tweets

### Secondary (MEDIUM confidence)
- `formats/storytelling/quality.py` — confirms `_PASS_THRESHOLD=7.0`, Sonnet temp=0.3 for quality, same JSON parse pattern
- `.planning/phases/03-ai-story-generation/03-CONTEXT.md` — all locked decisions, confirmed no new dependencies needed

### Tertiary (LOW confidence)
- None — all findings grounded in direct codebase inspection.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all existing project patterns
- Architecture: HIGH — directly mirrors existing generator.py structure; patterns verified in code
- Pitfalls: HIGH — overlay substring constraint is a concrete runtime failure mode (overlay.py uses exact matching); jargon stripping is a prompt engineering concern confirmed by CONTEXT.md decisions

**Research date:** 2026-03-12
**Valid until:** Stable — no external dependencies. Valid as long as generator.py output schema is unchanged.
