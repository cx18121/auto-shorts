---
phase: 03-ai-story-generation
plan: 01
subsystem: generation
tags: [anthropic, claude-haiku, story-generation, reddit-adaptation, tts, niche-tones]

# Dependency graph
requires:
  - phase: 02-content-pipeline
    provides: ChannelConfig dataclass, backlog story schema (title, body, subreddit, score)

provides:
  - adapt_reddit_post(post, channel_slug, profile=None) -> dict — Reddit post to TTS script adapter
  - _build_reddit_prompt() — niche tone vs. style profile branching for Reddit adaptation
  - _NICHE_TONES dict — hard-coded tone directives for hypothetical-scenarios and relationships
  - Enhanced _validate() — overlay_phrases substring check added
  - style_profile: str = "" field on ChannelConfig
  - channels.yaml.example updated with style_profile field documentation

affects:
  - 03-ai-story-generation (remaining plans that wire adapt_reddit_post into CLI and backlog flow)
  - main.py (--from-backlog flag wiring in later plans)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Two-function generator module — generate_story() and adapt_reddit_post() share _validate(), _parse_json(), retry pattern, and return same 5-key dict
    - Niche tone lookup table (_NICHE_TONES) — hard-coded per slug, overridden entirely when style profile present
    - _build_reddit_prompt() — single branch point for niche defaults vs. profile guidance

key-files:
  created:
    - tests/test_story_generator.py
  modified:
    - formats/storytelling/generator.py
    - config.py
    - channels.yaml.example
    - tests/test_config_channels.py

key-decisions:
  - "adapt_reddit_post lives in formats/storytelling/generator.py (not a new file) — shares _validate(), _parse_json(), retry loop with generate_story() to avoid duplication"
  - "style_profile field on ChannelConfig defaults to empty string — falsy, no validation needed, existing channels.yaml files unaffected"
  - "Profile overrides niche defaults entirely — _build_reddit_prompt branches on profile presence, no merging"
  - "Post body truncated to 4000 chars before prompt insertion (Haiku context safety) and word-count guard (< 50 words raises ValueError)"

patterns-established:
  - "Reddit adapter pattern: _build_reddit_prompt() fills _REDDIT_USER_PROMPT template; adapt_reddit_post() calls same retry loop as generate_story()"
  - "overlay_phrases substring validation in _validate() — raises ValueError with offending phrase for early failure detection"

requirements-completed: [GEN-01, GEN-02, GEN-03]

# Metrics
duration: 5min
completed: 2026-03-12
---

# Phase 3 Plan 01: Reddit Post Adaptation — Story Generator Summary

**`adapt_reddit_post()` in generator.py adapts Reddit posts to TTS-ready scripts via Claude Haiku, with hard-coded niche tones for hypothetical-scenarios/relationships and style profile override support**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-12T15:49:33Z
- **Completed:** 2026-03-12T15:54:33Z
- **Tasks:** 2 (TDD: RED commit + GREEN commit)
- **Files modified:** 4

## Accomplishments

- `adapt_reddit_post(post, channel_slug, profile=None)` added to `formats/storytelling/generator.py` — same 5-key output dict as `generate_story()`, same retry pattern, uses `_REDDIT_SYSTEM_PROMPT`
- `_NICHE_TONES` dict with contemplative tone for hypothetical-scenarios and empathy tone for relationships; `_build_reddit_prompt()` branches on profile presence vs. niche defaults
- `_validate()` enhanced to check all overlay phrases are exact substrings of `story_text` (fails fast with the offending phrase in the error message)
- `style_profile: str = ""` added to `ChannelConfig`; `channels.yaml.example` updated with field and comment on all three channels
- 30 tests pass (21 new in `test_story_generator.py`, 2 new in `test_config_channels.py`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add style_profile to ChannelConfig + tests (RED)** - `9a5686f` (test)
2. **Task 2: Implement adapt_reddit_post, _build_reddit_prompt, _NICHE_TONES, enhance _validate (GREEN)** - `dae25c3` (feat)

_TDD: Task 1 is the RED commit (tests fail), Task 2 is the GREEN commit (all pass)._

## Files Created/Modified

- `formats/storytelling/generator.py` — Added `_NICHE_TONES`, `_REDDIT_SYSTEM_PROMPT`, `_REDDIT_USER_PROMPT`, `adapt_reddit_post()`, `_build_reddit_prompt()`; enhanced `_validate()` with overlay_phrases substring check
- `config.py` — Added `style_profile: str = ""` field to `ChannelConfig` dataclass after `quality` field
- `channels.yaml.example` — Added `style_profile: ""` with comment to all three channel definitions
- `tests/test_story_generator.py` — New: `TestNicheTones`, `TestBuildRedditPrompt`, `TestValidate`, `TestAdaptRedditPost` classes (21 tests, Anthropic mocked)
- `tests/test_config_channels.py` — Extended with `test_style_profile_optional` and `test_style_profile_set`

## Decisions Made

- `adapt_reddit_post` placed in existing `generator.py` (not a new file) to share `_validate()`, `_parse_json()`, `_parse_json()`, and retry infrastructure with `generate_story()`
- Post body truncated to 4000 chars before prompt insertion as a defensive guard against Haiku context overflow
- `style_profile` field defaults to empty string — falsy check in `_build_reddit_prompt()` is sufficient, no path validation at config load time
- Profile overrides niche defaults entirely when present — no merging of profile and niche tone

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

The full `pytest tests/` suite fails when `test_config_channels.py` runs before other tests because its `tearDown` deletes `channels.yaml`, causing subsequent test modules that `import config` at module level to raise `SystemExit`. This is a pre-existing issue (confirmed via `git stash` check) not caused by this plan. Logged to deferred items.

## Next Phase Readiness

- `adapt_reddit_post()` is callable and returns valid 5-key script dicts — ready for integration with the backlog pipeline
- `style_profile` field is on `ChannelConfig` — main.py `--from-backlog` flow can now load profiles per channel
- Remaining phase 3 plans (CLI wiring, `--from-backlog` flag, quality integration) can proceed immediately

---
*Phase: 03-ai-story-generation*
*Completed: 2026-03-12*
