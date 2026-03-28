---
phase: quick-8
plan: 8
subsystem: pipeline/backlog
tags: [backlog, review, sorting, tweets]
dependency_graph:
  requires: []
  provides: [get_pending_tweets ordered by computed score DESC]
  affects: [cmd_review in main.py]
tech_stack:
  added: []
  patterns: [SQL computed expression in ORDER BY]
key_files:
  modified:
    - pipeline/backlog.py
decisions:
  - "ORDER BY (likes + retweets * 3) DESC uses SQL computed expression — no schema change needed"
metrics:
  duration: "< 1 min"
  completed_date: "2026-03-13"
  tasks_completed: 1
  files_modified: 1
---

# Quick Task 8: Sort Backlog by Score in Review Command Summary

**One-liner:** Changed `get_pending_tweets` ORDER BY from `likes DESC` to `(likes + retweets * 3) DESC` so reviewers see highest-quality tweets first.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Sort pending tweets by computed score in get_pending_tweets | 29b874c | pipeline/backlog.py |

## Changes Made

Updated `get_pending_tweets` in `pipeline/backlog.py` (line 336) to order results by the established tweet scoring formula `likes + retweets * 3` descending instead of `likes` alone. The formula is consistent with the scoring formula used elsewhere in the codebase (confirmed in tests/test_tweet_scraper_store.py). No schema change was required — this is a SQL computed expression in the ORDER BY clause.

Also updated the function docstring to reflect the new ordering.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

Inline assertion test passed:
- Tweet A (100 likes, 50 retweets) score = 250 ranked above Tweet B (200 likes, 5 retweets) score = 215
- `PASS: tweets sorted by likes + retweets*3 DESC`

## Self-Check: PASSED

- [x] `pipeline/backlog.py` modified and committed (29b874c)
- [x] Verification test passes
- [x] `get_pending_stories` unchanged (no regression risk — separate function)
