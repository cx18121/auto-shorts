---
phase: quick-7
plan: 7
subsystem: cli, reddit-scraper
tags: [cli, reddit, scraper, window]
dependency_graph:
  requires: []
  provides: [scrape --window year]
  affects: [main.py, pipeline/reddit_scraper.py]
tech_stack:
  added: []
  patterns: [WINDOW_MAP lookup for Reddit time_filter]
key_files:
  created: []
  modified:
    - main.py
    - pipeline/reddit_scraper.py
decisions:
  - Reddit's public JSON /top endpoint accepts t=year natively — no other changes needed beyond WINDOW_MAP entry
metrics:
  duration: "2 minutes"
  completed: "2026-03-13"
  tasks_completed: 1
  files_modified: 2
---

# Quick Task 7: Add "year" to --window choices for scrape command

**One-liner:** Added "year" as a valid --window value for scrape, mapping to Reddit's t=year time filter for deep backlog bootstrapping.

## What Was Done

Added support for `--window year` on the `scrape` CLI subcommand. This lets users pull Reddit top posts from the past year, useful when bootstrapping a channel backlog beyond the existing "month" window.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add "year" to CLI choices and WINDOW_MAP | 1d79ac9 | main.py, pipeline/reddit_scraper.py |

## Changes Made

**main.py** (line 93-94):
- `choices=["24h", "month"]` → `choices=["24h", "month", "year"]`
- Help text updated: added "year for deep backlog"

**pipeline/reddit_scraper.py** (WINDOW_MAP, lines 29-32):
- Added `"year": "year"` entry
- Updated `scrape_and_store_reddit` docstring to list "year" in accepted window values

## Verification

```
$ python3 main.py --channel hypothetical-scenarios scrape --help | grep -A2 "window"
  --window {24h,month,year}
        Time window: '24h' for daily (default), 'month' for
        bootstrap fill, 'year' for deep backlog

$ python3 -c "from pipeline.reddit_scraper import WINDOW_MAP; assert WINDOW_MAP['year'] == 'year'"
# exits 0
```

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- main.py modified: confirmed
- pipeline/reddit_scraper.py modified: confirmed
- Commit 1d79ac9: confirmed
