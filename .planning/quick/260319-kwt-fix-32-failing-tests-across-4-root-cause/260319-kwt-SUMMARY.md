---
phase: quick
plan: 260319-kwt
subsystem: tests
tags: [test-fixes, imports, mocking, isolation]
key-files:
  modified:
    - tests/test_run_cycle.py
    - tests/test_reddit_scraper.py
    - tests/test_story_generator.py
    - tests/test_config_channels.py
    - formats/storytelling/generator.py
decisions:
  - "test_config_channels tearDown restores shared mock config to sys.modules so subsequent tests do not trigger channels.yaml SystemExit"
  - "commands.generate and commands.scrape mocked before commands.run_cycle import; commands.scrape mock then removed so cmd_upload_history tests get the real module"
  - "overlay_phrases substring validation added to _validate() in generator.py — minimal correct behavior required by existing test"
metrics:
  duration: "~15 minutes"
  completed: "2026-03-19"
  tasks_completed: 3
  files_modified: 5
---

# Quick Task 260319-kwt: Fix 32 Failing Tests Across 4 Root Causes — Summary

Fixed all 32 failing tests caused by stale imports (post-dbdac78 refactor), wrong mock interfaces, and global state pollution.

## What Was Done

Fixed 4 root causes across 4 test files with no behavior changes to production code (except one minimal validation addition).

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Fix test_run_cycle.py imports and mock targets | 8729e46 | tests/test_run_cycle.py |
| 2 | Fix test_reddit_scraper.py, test_story_generator.py, test_config_channels.py | eb740d2 | tests/test_reddit_scraper.py, tests/test_story_generator.py, tests/test_config_channels.py, formats/storytelling/generator.py |
| 3 (iteration) | Fix cross-test config mock tearDown for full suite | 1185450 | tests/test_config_channels.py |

## Root Cause Analysis and Fixes

### Root Cause 1: Stale Imports in test_run_cycle.py (18 tests)

After the dbdac78 refactor, `cmd_run_cycle` and `cmd_upload_history` moved from `main.py` to `commands/run_cycle.py` and `commands/scrape.py`. All test imports still pointed to `main`.

**Fix:**
- Changed all `from main import cmd_run_cycle` to `from commands.run_cycle import cmd_run_cycle`
- Changed all `from main import cmd_upload_history` to `from commands.scrape import cmd_upload_history`
- Updated all `patch("main.xxx")` to `patch("commands.run_cycle.xxx")` for functions imported into that namespace
- Pre-injected mock `commands.generate` and `commands.scrape` into sys.modules before importing `commands.run_cycle` (to prevent real config load), then restored real `commands.scrape` for upload_history tests
- Added `patch("pipeline.upload.save_metadata_file")` in full-flow test to prevent FileNotFoundError

### Root Cause 2: PRAW Interface in test_reddit_scraper.py (1 test)

`scrape_subreddit_top` was rewritten to use `requests.get` (no PRAW), but the test still mocked a PRAW Reddit object and passed it as the first argument.

**Fix:**
- Rewrote `test_scrape_returns_posts` to mock `pipeline.reddit_scraper.requests.get` returning a proper Reddit JSON response structure
- Rewrote `test_selftext_filter_empty` with the same requests.get mock approach
- Fixed `test_per_subreddit_failure_isolation`: removed `mock_reddit` parameter from `scrape_channel_subreddits` call, updated side_effect signature to match new 3-arg API `(subreddit_name, time_filter, limit)`

### Root Cause 3: Config SystemExit in test_story_generator.py (1 test in original; cross-test isolation)

`formats/storytelling/generator.py` imports `config` at module level. When test_config_channels.py ran in the full suite and its tearDown deleted config from sys.modules, subsequent imports of generator triggered the real config.py which raised SystemExit on missing channels.yaml.

Additionally, the original 1 failing test (`test_overlay_phrases_are_substrings_invalid`) tested behavior not yet implemented: `_validate()` did not check that overlay_phrases were substrings of story_text.

**Fix:**
- Added `sys.modules.setdefault("config", _mock_config)` at module level in test_story_generator.py
- Added overlay_phrases substring validation to `_validate()` in generator.py (7 lines, minimal correctness addition)

### Root Cause 4: Global State Pollution in test_config_channels.py (12 tests)

When test_config_channels.py ran after test_run_cycle.py's module-level mock, `importlib.reload(config)` failed because sys.modules["config"] was a MagicMock (not a real module). When it ran before test_run_cycle.py, its tearDown deleted real config from sys.modules, leaving a gap that caused subsequent test files' lazy imports to trigger channels.yaml SystemExit.

**Fix:**
- setUp: `del sys.modules["config"]` before reload to strip any mock (regardless of run order)
- tearDown: delete real config and restore a shared mock config object so test files running after `test_config_channels` still find a mock config in sys.modules

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] commands.scrape mock removed post-import so cmd_upload_history works**
- Found during: Task 1
- Issue: Mocking `commands.scrape` at module level prevented the real `cmd_upload_history` from being importable for upload history tests
- Fix: Pre-inject mock for commands.run_cycle import, then delete the mock from sys.modules so subsequent imports of `commands.scrape` get the real module
- Files modified: tests/test_run_cycle.py

**2. [Rule 1 - Bug] save_metadata_file missing from test mocks**
- Found during: Task 1 (test_storytelling_full_flow)
- Issue: test called cmd_run_cycle with a mock video path `/tmp/output/final.mp4` but `save_metadata_file` tried to write `/tmp/output/final.txt` which requires the directory to exist
- Fix: Added `patch("pipeline.upload.save_metadata_file")` to the full-flow test
- Files modified: tests/test_run_cycle.py

**3. [Rule 1 - Bug] Full suite: test_config_channels tearDown left no config in sys.modules**
- Found during: Task 3 (full suite verification)
- Issue: After tearDown deleted real config without restoring a mock, test_run_cycle and test_story_generator test methods triggered real config imports (from analysis.db, pipeline.backlog etc.) which raised SystemExit
- Fix: tearDown now restores the shared mock config to sys.modules after each test
- Files modified: tests/test_config_channels.py

## Verification

```
python3 -m pytest tests/ -v
# Result: 119 passed, 1 skipped in 94.61s
```

- All 32 previously-failing tests now pass
- No regressions (27 previously-passing tests still pass)
- test_config_channels.py passes both in isolation and in full suite run
- The 1 skipped test (pre-existing) is unrelated to this work

## Self-Check: PASSED

Commits verified:
- 8729e46 — test_run_cycle.py imports/mocks
- eb740d2 — reddit scraper, story generator, generator.py _validate
- 1185450 — config tearDown isolation fix
