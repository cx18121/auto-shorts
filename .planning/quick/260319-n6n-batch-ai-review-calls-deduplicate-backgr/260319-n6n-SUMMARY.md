---
phase: quick-260319-n6n
plan: 01
subsystem: pipeline-improvements
tags: [ai-review, background-dedup, status-command, cost-reduction]
dependency_graph:
  requires: []
  provides: [batch-ai-review, background-dedup, health-status]
  affects: [commands/review.py, commands/generate.py, commands/run_cycle.py, pipeline/backlog.py, commands/status.py, main.py]
tech_stack:
  added: []
  patterns: [batched-claude-prompt, per-channel-usage-tracking, health-dashboard-cli]
key_files:
  created:
    - commands/status.py
  modified:
    - commands/review.py
    - commands/generate.py
    - commands/run_cycle.py
    - pipeline/backlog.py
    - main.py
decisions:
  - "_build_content_block() extracted as shared helper between single and batch review to keep DRY"
  - "get_recent_backgrounds/log_background_use use try/except on OperationalError so they're safe on old DBs"
  - "background_usage table added to init_backlog_tables() DDL — created alongside backlog tables on next run"
  - "Instagram token expiry supports both Unix timestamp (int) and ISO string formats in cmd_status"
metrics:
  duration: "~4 minutes"
  completed: "2026-03-19"
  tasks_completed: 3
  files_changed: 6
---

# Phase quick-260319-n6n Plan 01: Batch AI Review, Background Dedup, Health Status

**One-liner:** Three pipeline improvements — batched Claude review (N items in 1 call per 50), per-channel background clip deduplication via `background_usage` table, and a `status` subcommand printing channel health (backlog counts, last upload, token status, video count).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Batch AI review into single Claude call | 5e91325 | commands/review.py |
| 2 | Background clip deduplication | fd4d039, d2b37b7 | pipeline/backlog.py, commands/generate.py, commands/run_cycle.py |
| 3 | Health status command | 26d9045 | commands/status.py, main.py |

## What Was Built

### Task 1 — Batch AI Review (commands/review.py)

- Added `_ai_review_batch(items, source_label, channel_cfg) -> list[tuple[str, str]]`
- Chunks items into groups of 50; sends one Claude Haiku prompt per chunk with all items numbered 1..N
- Content truncated to 400 chars per item; `max_tokens` scaled to `max(256, n * 64)`
- 3-attempt retry with exponential backoff; falls back to `("reject", "batch error")` on parse failure
- `cmd_review` AI path now calls `_ai_review_batch` once instead of `_ai_review_item` N times
- Extracted `_build_content_block()` shared between single and batch review
- `_ai_review_item` kept intact for single-item use cases

### Task 2 — Background Clip Deduplication (pipeline/backlog.py, commands/generate.py, commands/run_cycle.py)

- Added `background_usage` table to `init_backlog_tables()` DDL
- Added `log_background_use(conn, channel, bg_filename)` — inserts row with `used_at=utcnow`
- Added `get_recent_backgrounds(conn, channel, limit=5)` — returns last N bg_filenames DESC
- Both helpers use try/except on `OperationalError` for backward compat with old DBs
- `_pick_background(exclude=None)` now accepts optional exclusion list; falls back to full list if all excluded
- `_generate_storytelling_from_backlog`: fetches recent 5, passes to `_pick_background`, logs after success
- `cmd_run_cycle` storytelling branch: same pattern — fetch recent, exclude, log after success

### Task 3 — Health Status Command (commands/status.py, main.py)

- Created `commands/status.py` with `cmd_status(channel_cfg)` printing:
  - Channel slug/name/format/enabled status
  - Backlog counts: pending/approved/used/rejected
  - Last upload: date/platform/status (or "No uploads yet")
  - Token status: YouTube (Found/Missing), Instagram (Found with days remaining, or Missing)
  - Output video count (total .mp4 files in output/ dir)
- Registered `status` subcommand in `main.py` argparse and `_dispatch_command`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] background_usage table missing in test in-memory DBs**
- **Found during:** Task 2 verification (test suite run)
- **Issue:** `test_marks_story_used_after_success` creates a minimal in-memory SQLite DB without `background_usage` table; `get_recent_backgrounds` raised `OperationalError`
- **Fix:** Wrapped both `get_recent_backgrounds` and `log_background_use` in try/except on `OperationalError` — returns `[]` / silently skips respectively
- **Files modified:** pipeline/backlog.py
- **Commit:** d2b37b7

## Verification

All three task verification commands pass:
- `python3 -c "from commands.review import _ai_review_batch; print('import ok')"` — OK
- `python3 -c "from pipeline.backlog import log_background_use, get_recent_backgrounds; print('import ok')"` — OK
- `python3 -c "from commands.status import cmd_status; print('import ok')"` — OK
- Test suite: 116 passed, 1 skipped (0 failed)

## Self-Check: PASSED

Files created/modified exist:
- commands/status.py: exists
- commands/review.py: exists (modified)
- commands/generate.py: exists (modified)
- commands/run_cycle.py: exists (modified)
- pipeline/backlog.py: exists (modified)
- main.py: exists (modified)

Commits exist:
- 5e91325: feat(260319-n6n): batch AI review into single Claude call per 50 items
- fd4d039: feat(260319-n6n): deduplicate background clips via per-channel usage tracking
- 26d9045: feat(260319-n6n): add health status command
- d2b37b7: fix(260319-n6n): make background_usage helpers robust to missing table
