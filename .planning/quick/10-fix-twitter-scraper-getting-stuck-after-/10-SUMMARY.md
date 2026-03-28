---
phase: quick-10
plan: 10
subsystem: formats/tweets/scraper
tags: [bugfix, playwright, twitter, scraper, hang]
dependency_graph:
  requires: []
  provides: [hang-resistant-home-feed-navigation]
  affects: [formats/tweets/scraper.py]
tech_stack:
  added: []
  patterns: [playwright-commit-navigation, login-wall-detection]
key_files:
  created: []
  modified:
    - formats/tweets/scraper.py
decisions:
  - "Use wait_until=commit for /home URLs — domcontentloaded never fires when X keeps WebSockets open"
  - "Login wall detection via URL marker check after navigation commit — catches stale cookies immediately"
  - "Separate wait_for_load_state with its own timeout so a slow DOMContentLoaded does not abort the scrape"
metrics:
  duration: "3 min"
  completed: "2026-03-13"
  tasks: 1
  files: 1
---

# Phase quick-10 Plan 10: Fix Twitter Scraper Hanging on x.com/home Summary

**One-liner:** Replaced domcontentloaded navigation on x.com/home with commit-based goto plus login-wall redirect detection to eliminate indefinite hangs on stale cookies.

## What Was Built

Patched `_scrape_page_playwright` in `formats/tweets/scraper.py` with three targeted changes:

1. **Commit-based navigation for /home URLs** — `wait_until="commit"` resolves as soon as Playwright commits the navigation request, before the page's persistent WebSocket/XHR activity can hold the event loop open.

2. **Separate DOMContentLoaded wait with a hard timeout** — after the `commit` goto, a `wait_for_load_state("domcontentloaded", timeout=15_000)` gives the page 15 seconds to fully load. On timeout the exception is swallowed with a `logger.debug` message and scraping continues — a partial DOM is still usable.

3. **Login-wall redirect detection** — immediately after navigation, `page.url` is inspected for `/i/flow/`, `/login`, and `/i/nojs_router`. Any of these indicates X redirected away from the home feed because cookies are stale. The function logs a clear warning with re-export instructions and returns `[]` instead of waiting for a tweet selector that will never appear.

## Deviations from Plan

None — plan executed exactly as written.

## Tasks

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Add login-wall detection and hang-resistant navigation to _scrape_page_playwright | c942f9a | formats/tweets/scraper.py |

## Self-Check: PASSED

- `formats/tweets/scraper.py` exists and parses without syntax errors
- Commit c942f9a present in git log
- `wait_until="commit"` present for /home URLs
- Login wall marker check present (`/i/flow/`, `/login`, `/i/nojs_router`)
- Separate `wait_for_load_state("domcontentloaded", timeout=15_000)` present
