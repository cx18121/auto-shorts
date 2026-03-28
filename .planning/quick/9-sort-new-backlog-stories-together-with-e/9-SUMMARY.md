---
phase: quick
plan: 9
subsystem: pipeline/backlog
tags: [backlog, sort, review, stories]
dependency_graph:
  requires: []
  provides: [get_pending_stories with DATE(scraped_at) DESC, score DESC ordering]
  affects: [main.py cmd_review]
tech_stack:
  added: []
  patterns: [SQLite DATE() function for day-level grouping]
key_files:
  created: []
  modified:
    - pipeline/backlog.py
decisions:
  - "Used DATE(scraped_at) DESC rather than scraped_at DESC to group items by day — prevents 1-second timestamp differences from splitting items scraped in the same daily batch"
metrics:
  duration: ~5 minutes
  completed: 2026-03-13
---

# Quick Task 9: Sort New Backlog Stories Together With Existing by Scrape Date Summary

**One-liner:** Changed `get_pending_stories` sort from global `score DESC` to `DATE(scraped_at) DESC, score DESC` so daily scrapes always surface at the top of the review queue above the year-window bootstrap backlog.

## What Was Done

### Task 1: Inspect DB and fix get_pending_stories sort order

Changed `get_pending_stories` in `pipeline/backlog.py`:

- **Before:** `ORDER BY score DESC` — year-window posts (50K+ upvotes) always dominated, daily posts (500–10K upvotes) sank to the bottom
- **After:** `ORDER BY DATE(scraped_at) DESC, score DESC` — today's batch appears first, ordered by score within the day

Updated the docstring to: "Return pending stories for *channel*, newest scraped batch first, then by score DESC within each batch."

**Verification:** In-memory SQLite test confirmed a story with score 5000 scraped today appears before a story with score 50000 scraped in January. All 7 existing `test_backlog.py` tests continue to pass.

**Commit:** `9977039`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Used DATE() truncation instead of raw scraped_at for sort**

- **Found during:** Task 1 verification
- **Issue:** The plan specified `ORDER BY scraped_at DESC, score DESC` but the verification test inserted two "new" rows 1 second apart on the same day and expected them to sort by score. Raw `scraped_at DESC` would put the later-scraped lower-score item first, failing the assertion.
- **Fix:** Used `DATE(scraped_at) DESC, score DESC` to group items by calendar day, matching the intended "batch" semantics and making the test pass.
- **Files modified:** `pipeline/backlog.py`
- **Commit:** `9977039` (included in the task commit)

## Self-Check: PASSED

- `pipeline/backlog.py` — FOUND
- commit `9977039` — FOUND
