# Phase 3: AI Story Generation - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Claude generates narration-ready story scripts from Reddit post titles and bodies, matching niche tone and style profiles. Only storytelling-format niches (hypothetical-scenarios, relationships) are in scope — finance uses tweets, not generated stories. The output feeds into the existing TTS → overlay → assembler pipeline. Quality scoring and backlog are already built (Phase 2).

</domain>

<decisions>
## Implementation Decisions

### Script adaptation approach
- **Clean up verbatim** — keep the original Reddit text mostly intact, strip markdown, fix grammar, add TTS-friendly phrasing
- Strip all Reddit-specific references ('AITA', 'throwaway', subreddit mentions, 'edit: wow this blew up') — story stands on its own
- When posts are too long for target duration: **condense to fit** — Claude compresses the story, removing tangents and tightening sentences while keeping the full arc
- Hook line: **only add if needed** — Claude judges whether the post already opens strong; if not, prepend a hook

### Niche tone mapping
- **Hard-coded per niche** in the generator code, short 1-2 sentence directives
- Tone guides overall feel only, not word-level choices
- Only storytelling niches get tone mappings (hypothetical-scenarios, relationships)
- Finance niche excluded — it uses tweet format, no AI story generation

### Output script format
- **Match existing generator.py structure**: `title`, `hook_line`, `story_text`, `overlay_phrases`, `estimated_duration_seconds`
- Title: **Claude generates** a YouTube-optimized title (under 60 chars), not the Reddit post title
- Overlay phrases: must be **exact substrings** of `story_text` — ensures alignment with TTS timestamps
- Target duration: **45-60 seconds** (tighter than the 30-90s requirement range; sweet spot for YouTube Shorts algorithm)

### Style profile integration
- When a style profile exists for a channel, it **overrides niche defaults** entirely — profile is the authority
- Fields used: `generation_prompt_guidance`, `hook_patterns`, `tone`, `emotional_triggers`, `topic_categories`, `ideal_word_count`, `ideal_duration_seconds`, plus `vocabulary_notes`
- If profile specifies `ideal_duration_seconds`, use that instead of the 45-60s default
- Profile path stored as `style_profile` field in `channels.yaml` per channel
- If no profile exists, fall back to hard-coded niche tone defaults

### Claude's Discretion
- Exact prompt engineering and system prompt wording
- How to handle edge cases (posts with images referenced, deleted content, etc.)
- Whether to modify the existing `generator.py` or create a new function alongside it

</decisions>

<specifics>
## Specific Ideas

- The existing `formats/storytelling/generator.py` generates original stories from style profiles — Phase 3 adds a new capability: adapting real Reddit posts into scripts
- The same JSON output structure means the downstream pipeline (TTS, overlay, assembler) works unchanged
- Overlay phrases as exact substrings is important because `pipeline/overlay.py` uses word-level TTS timestamps to position them

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `formats/storytelling/generator.py`: Existing generator with `generate_story()`, `_build_prompt()`, `_parse_json()`, `_validate()` — same output schema needed
- `pipeline/tts.py`: `generate_tts(text)` — consumes `story_text` field directly
- `pipeline/overlay.py`: Uses word-level timestamps — overlay_phrases must be exact substrings of story_text
- `pipeline/backlog.py`: `get_approved_stories(channel)` — provides Reddit posts to generate from
- `config.py`: `ChannelConfig` dataclass with `get_channel(slug)` — will need `style_profile` field added

### Established Patterns
- Anthropic API: Haiku for generation (temp 0.85), max_tokens=1024, JSON output with explicit schema in system prompt
- 3 retries with exponential backoff on API calls
- Functions over classes, type hints on all functions, logging via `logging.getLogger(__name__)`

### Integration Points
- `pipeline/backlog.py`: Source of approved Reddit posts (title + body + metadata)
- `channels.yaml`: New `style_profile` field pointing to style profile JSON path
- `main.py`: Generation command already exists (`generate --format storytelling`) — may need Reddit-source variant
- `formats/storytelling/assembler.py`: Consumes the generated script dict unchanged

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-ai-story-generation*
*Context gathered: 2026-03-12*
