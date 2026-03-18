---
phase: quick-260318-lld
plan: 1
subsystem: formats/tweets/scraper
tags: [scraper, playwright, anti-detection, twitter, x.com]
dependency_graph:
  requires: []
  provides: [anti-detection browser launch, resilient profile page navigation]
  affects: [formats/tweets/scraper.py]
tech_stack:
  added: []
  patterns: [commit-based navigation, navigator.webdriver removal, fallback selector strategy]
key_files:
  created: []
  modified:
    - formats/tweets/scraper.py
decisions:
  - Extend commit-based navigation to all X.com URLs (not just /home) — profile pages exhibit the same websocket-keeps-open issue
  - Add 2s hydration delay before querying tweet cards — lets React/Next.js bundle finish rendering before DOM query
  - Fallback selector uses article instead of article[data-testid="tweet"] in wait_for_selector — broadest possible match when X serves degraded page
metrics:
  duration: "~2 minutes"
  completed: "2026-03-18"
  tasks_completed: 2
  files_modified: 1
---

# Phase quick-260318-lld Plan 1: Fix Twitter Scraper Hanging on Account Profile Pages Summary

**One-liner:** Anti-detection Chromium launch (Chrome 131 UA, navigator.webdriver removal, locale/TZ) plus commit-based navigation with DOMContentLoaded fallback and article fallback selector for all X.com profile pages.

## What Was Built

The Twitter/X.com Playwright scraper was hanging indefinitely when navigating to account profile pages (e.g., x.com/WhatIfAlt). The root cause was two-fold:

1. X.com detects headless Chromium via `navigator.webdriver` and serves a degraded page where `[data-testid="tweet"]` cards never render.
2. Profile pages used `domcontentloaded` wait which can hang because X.com keeps WebSocket connections open indefinitely.

The previous fix (quick task 10) addressed the `/home` URL hang with commit-based navigation, but profile pages were still using the old `domcontentloaded` path.

### Task 1: Anti-detection browser launch

- Added `--disable-blink-features=AutomationControlled` to Chromium launch args
- Added `--disable-features=IsolateOrigins,site-per-process`, `--disable-infobars`, `--no-first-run`
- Updated Chrome version in user agent from 122 to 131 (less suspicious)
- Added `locale="en-US"` and `timezone_id="America/New_York"` to browser context
- Added `add_init_script` to set `navigator.webdriver` to `undefined` before cookies are loaded

### Task 2: Resilient profile page navigation

- Changed all X.com navigation to use `wait_until="commit"` (removed the `"/home" in url` conditional)
- DOMContentLoaded wait now always runs after commit (removed the `if nav_wait == "commit":` guard)
- Added `page.wait_for_timeout(2_000)` hydration delay before querying tweet cards
- Replaced single `wait_for_selector` with try/except chain: primary `[data-testid="tweet"]` → fallback `article` → return `[]` with warning
- Added article fallback in scroll loop card collection query

## Deviations from Plan

None — plan executed exactly as written.

## Verification

- `python3 -c "import ast; ast.parse(open('formats/tweets/scraper.py').read()); print('OK')"` passes for both tasks
- Manual scraper test (requires valid cookies) will confirm no hanging: `python3 -c "from formats.tweets.scraper import scrape_top_tweets; tweets = scrape_top_tweets(n=3, min_likes=100, accounts=['WhatIfAlt'], include_home=False); print(f'Got {len(tweets)} tweets')"`

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | f445dfc | feat(quick-260318-lld): add anti-detection to Playwright browser launch |
| 2 | 8e10b27 | feat(quick-260318-lld): resilient profile page navigation for all X.com URLs |

## Self-Check: PASSED
