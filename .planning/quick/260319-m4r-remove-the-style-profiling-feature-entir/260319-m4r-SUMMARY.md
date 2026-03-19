---
phase: quick-260319-m4r
plan: 01
subsystem: pipeline
tags: [refactor, cleanup, dead-code-removal]
dependency_graph:
  requires: []
  provides: [pipeline/db.py]
  affects: [commands/generate.py, commands/run_cycle.py, formats/storytelling/generator.py, config.py]
tech_stack:
  added: []
  patterns: [pipeline.db as canonical DB module]
key_files:
  created:
    - pipeline/db.py
  modified:
    - config.py
    - main.py
    - commands/generate.py
    - commands/run_cycle.py
    - formats/storytelling/generator.py
    - pipeline/backlog.py
    - pipeline/reddit_scraper.py
    - formats/tweets/scraper.py
    - commands/scrape.py
    - commands/review.py
    - channels.yaml.example
    - CLAUDE.md
    - tests/test_run_cycle.py
    - tests/test_config_channels.py
    - tests/test_story_generator.py
    - tests/test_tweet_scraper_store.py
    - tests/test_cli_channel_flag.py
  deleted:
    - analysis/ (entire directory: db.py, fetcher.py, profiler.py, ranker.py, transcripts.py, visual.py, __init__.py)
    - commands/analyze.py
    - formats/storytelling/quality.py
    - formats/tweets/generator.py
    - formats/tweets/quality.py
    - style_profiles/ (directory)
decisions:
  - Deleted formats/storytelling/quality.py and formats/tweets/quality.py entirely since both contained only profile-based Claude scoring with no non-profile logic
  - Deleted formats/tweets/generator.py entirely since all functions were profile-based AI generation
  - test_cli_channel_flag.py tests updated to use backlog-status instead of analyze command (tests verify --channel flag behavior, not the specific subcommand)
  - style_profiles/ directory deleted along with 4 existing JSON files inside it
metrics:
  duration: "9 minutes"
  tasks_completed: 3
  files_modified: 17
  files_deleted: 12
  completed_date: "2026-03-19"
---

# Phase quick-260319-m4r Plan 01: Remove Style Profiling Feature Summary

**One-liner:** Deleted the analysis/ directory, analyze CLI command, style profile fields, and all profile-based generation/quality code — pipeline now uses only backlog and scrape paths.

## What Was Done

### Task 1: Relocate analysis/db.py to pipeline/db.py, delete analysis/ directory

Created `pipeline/db.py` as a drop-in replacement for `analysis/db.py` with identical `get_connection()`, `init_db()`, and `init_backlog_tables` re-export. Deleted the entire `analysis/` directory (7 files) and `commands/analyze.py`. Updated all 7 files that imported from `analysis.db` to use `pipeline.db`.

### Task 2: Remove all style profile code

- **config.py**: Removed `STYLE_PROFILES_DIR` constant and `style_profile: str = ""` field from `ChannelConfig`
- **main.py**: Removed `analyze` subcommand, `--profile` flag, analyze dispatch, and profile validation block
- **commands/generate.py**: Removed `_load_style_profile()`, `_generate_storytelling()` (profile path), `_generate_tweets()` (profile path); simplified `cmd_generate` signature; backlog stories now auto-pass quality
- **commands/run_cycle.py**: Removed `_load_style_profile` import and usage; quality lambda now always returns `{"passed": True, "overall": 10.0}`
- **formats/storytelling/generator.py**: Removed `generate_story()`, `generate_batch()`, `_build_prompt()`; removed `profile` parameter from `adapt_reddit_post()` and `_build_reddit_prompt()`; now always uses niche tone defaults from `_NICHE_TONES`
- **Deleted**: `formats/storytelling/quality.py`, `formats/tweets/generator.py`, `formats/tweets/quality.py` (all profile-only)
- **tests**: Removed 2 style_profile tests from test_config_channels.py, removed test_profile_overrides_niche and updated call signatures in test_story_generator.py, removed style_profile from mock config in test_run_cycle.py, replaced analyze command with backlog-status in test_cli_channel_flag.py

### Task 3: Update CLAUDE.md and verify

Updated CLAUDE.md to remove analysis system docs, style profile schema, analyze CLI examples, and `--profile` flag. Fixed a remaining docstring reference in `formats/tweets/scraper.py`. All 116 tests pass (1 pre-existing skip).

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written with one minor addition:

**[Rule 2 - Missing]** Updated `channels.yaml.example` to remove `style_profile` fields from all 3 channel definitions. The plan mentioned removing `style_profile` from `ChannelConfig` but didn't explicitly call out updating the example YAML. Added to keep config file consistent.

## Verification

```
grep -rn "style.profile|profiler|analyze|analysis\." --include="*.py" . | grep -v __pycache__ | grep -v .planning
# Returns nothing (only harmless comment updated to "Niche tone directives (per-channel defaults)")

python3 -m pytest tests/ -v
# 116 passed, 1 skipped

ls analysis/ 2>/dev/null
# Directory gone

ls style_profiles/ 2>/dev/null
# Directory gone

python3 -c "from pipeline.db import get_connection; get_connection(); print('OK')"
# OK
```

## Self-Check: PASSED

- pipeline/db.py: exists and importable
- analysis/ directory: deleted
- style_profiles/ directory: deleted
- commands/analyze.py: deleted
- Commits: a17dbf6, 177bf2a, fb5720c
