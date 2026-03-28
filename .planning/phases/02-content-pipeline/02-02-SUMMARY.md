---
phase: 02-content-pipeline
plan: "02"
subsystem: database
tags: [sqlite, backlog, status-transitions, probation, crud]

# Dependency graph
requires:
  - phase: 02-content-pipeline/02-01
    provides: test stubs (tests/test_backlog.py RED tests) and DB schema in analysis/db.py
provides:
  - pipeline/backlog.py with all 13 exported functions + 2 private helpers
  - Canonical DDL for backlog_stories, backlog_tweets, niche_state via init_backlog_tables()
  - Full CRUD and status-transition layer for the content backlog
  - Probation system: PROBATION_THRESHOLD=25, maybe_auto_approve(), get_probation_remaining()
affects:
  - 02-03 (reddit scraper will use insert_story)
  - 02-04 (tweet scraper will use insert_tweet)
  - 02-05 (CLI review commands use approve_item, reject_item, mark_used, get_pending_*)
  - 02-06 (pipeline runner uses get_approved_stories, get_approved_tweets, mark_used)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "All backlog DB ops are pure functions accepting sqlite3.Connection — no globals, fully testable in-memory"
    - "INSERT OR IGNORE idempotency pattern for scraper-safe inserts"
    - "Story-specific convenience wrappers (approve_story, reject_story, mark_story_used) match the test API generated in Plan 01"
    - "_ensure_niche_state() called before every niche_state read/write to guarantee row existence"

key-files:
  created:
    - pipeline/backlog.py
  modified: []

key-decisions:
  - "Story-specific wrappers (approve_story/reject_story/mark_story_used) added alongside generic approve_item/reject_item/mark_used because Plan 01 test stubs used the story-specific API; both APIs coexist"
  - "approve_story channel param defaults to empty string so test helpers that omit channel still work; niche_state is only updated when channel is non-empty"
  - "maybe_auto_approve does NOT call increment_reviewed_count — auto-approved items must not advance the probation counter"

patterns-established:
  - "Backlog CRUD: pure functions + sqlite3.Connection parameter — no singleton connections in module"
  - "Probation guard: _ensure_niche_state() before every niche_state access"

requirements-completed:
  - BACKLOG-01
  - BACKLOG-02
  - BACKLOG-03
  - REDDIT-03
  - QUALITY-03

# Metrics
duration: 2min
completed: 2026-03-12
---

# Phase 02 Plan 02: Backlog DB Operations Layer Summary

**SQLite backlog CRUD module with status transitions (pending/approved/rejected/used), INSERT OR IGNORE idempotency, and a PROBATION_THRESHOLD=25 auto-approve system for niche_state**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-12T01:58:20Z
- **Completed:** 2026-03-12T01:59:57Z
- **Tasks:** 1 (TDD — implemented to make RED tests GREEN)
- **Files modified:** 1

## Accomplishments
- Created pipeline/backlog.py with all 13 exported functions + 2 private helpers (_pk, _ensure_niche_state)
- All 7 test_backlog.py tests pass GREEN (up from 0 — module did not exist)
- Probation system implemented: PROBATION_THRESHOLD=25, maybe_auto_approve() skips reviewed-count increment for auto-approvals
- Story-specific convenience wrappers (approve_story, reject_story, mark_story_used) aligned to Plan 01's test API

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement pipeline/backlog.py** - `50917f9` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `pipeline/backlog.py` - Complete DB operations layer: init_backlog_tables, insert_story/tweet, approve/reject/mark_used (generic + story wrappers), get_approved/pending queries, get_status_counts, probation functions

## Decisions Made
- Story-specific wrappers (approve_story, reject_story, mark_story_used) added alongside generic functions because Plan 01 test stubs used the story-specific API. Both coexist without conflict.
- approve_story channel param defaults to '' so tests that omit channel still work. niche_state is only updated when channel is non-empty.
- maybe_auto_approve directly UPDATEs approved status without calling approve_item to avoid double-incrementing the probation counter.

## Deviations from Plan

The plan spec listed `approve_item`, `reject_item`, `mark_used` as the primary API. The actual test stubs from Plan 01 import `approve_story`, `reject_story`, `mark_story_used`. Both APIs were implemented — story-specific wrappers for the test contract, generic functions for the spec contract and future tweet/story parity.

This is a minor interface alignment, not a structural deviation.

**Total deviations:** 0 auto-fixes needed. Plan-vs-test API mismatch resolved by implementing both.
**Impact on plan:** None — all test stubs pass, all plan-spec functions exist.

## Issues Encountered
- Full test suite (`python3 -m pytest tests/`) fails on `test_reddit_scraper.py` (pipeline.reddit_scraper not yet built — Plan 03) and `test_tts.py` (channels.yaml missing in test environment). Both are pre-existing RED tests, not regressions.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- pipeline/backlog.py is complete and fully tested — scrapers (Plans 03/04) and CLI (Plan 05) can import and use the backlog interface immediately
- No blockers for Plan 03 (reddit scraper) or Plan 04 (tweet scraper)

---
*Phase: 02-content-pipeline*
*Completed: 2026-03-12*
