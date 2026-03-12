---
phase: 02-content-pipeline
plan: "05"
subsystem: scraping
tags: [playwright, tweet-scraper, quality-filter, backlog, sqlite, tdd]

# Dependency graph
requires:
  - phase: 02-content-pipeline-02
    provides: "pipeline/backlog.py insert_tweet() and init_backlog_tables()"
  - phase: 02-content-pipeline-03
    provides: "pipeline/quality_filter.py passes_tweet_quality()"
provides:
  - "formats/tweets/scraper.py: Playwright browser leak fixed with try/finally in _scrape_async"
  - "formats/tweets/scraper.py: scrape_and_store_tweets() — wires scraping → quality filtering → backlog insertion"
affects:
  - 02-content-pipeline
  - main.py scrape command path

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_conn parameter pattern for SQLite testability — pass in-memory conn to avoid channels.yaml at import time"
    - "Lazy module imports inside function body to avoid import-time SystemExit from config.py chain"
    - "TDD: RED (import failure) → GREEN (11 tests passing) flow for new public API functions"

key-files:
  created:
    - tests/test_tweet_scraper_store.py
  modified:
    - formats/tweets/scraper.py

key-decisions:
  - "scrape_and_store_tweets accepts _conn parameter for testability — avoids channels.yaml SystemExit caused by analysis.db -> config.py import chain"
  - "analysis.db and pipeline imports kept lazy (inside function body) rather than module-level to prevent import-time failures in test environments without channels.yaml"
  - "min_likes=1 passed to scrape_top_tweets so quality filtering is fully auditable inside scrape_and_store_tweets; raw data is always retrieved before filtering"
  - "window parameter accepted but unused for API symmetry with scrape_and_store_reddit"

patterns-established:
  - "_conn injection pattern: public pipeline functions accept optional _conn for test isolation without mocking config"

requirements-completed:
  - BACKLOG-01
  - QUALITY-02
  - QUALITY-03

# Metrics
duration: 8min
completed: 2026-03-12
---

# Phase 2 Plan 05: Tweet Scraper — Browser Leak Fix + Pipeline Integration Summary

**Playwright browser resource leak fixed with try/finally, plus scrape_and_store_tweets() wiring tweet scraping to quality filtering and SQLite backlog insertion using per-channel twitter_accounts.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-12T02:02:22Z
- **Completed:** 2026-03-12T02:09:39Z
- **Tasks:** 2 (Task 1: leak fix; Task 2: TDD new function)
- **Files modified:** 2

## Accomplishments

- Fixed Chromium process leak: `_scrape_async` now wraps browser context in try/finally so `browser.close()` is guaranteed to run even when scraping raises an exception
- Added `scrape_and_store_tweets(channel_cfg, window, _conn)` to the public API — uses `channel_cfg.twitter_accounts` (never the global `VIRAL_ACCOUNTS`), applies `passes_tweet_quality`, calls `insert_tweet` for passing tweets, returns `{scraped, passed, inserted, duplicates}` summary dict
- Full TDD cycle: 11 new tests covering accounts routing, quality filtering, duplicate handling, and the browser leak fix itself

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix Playwright browser leak** - `bee513a` (fix)
2. **Task 2: RED — failing tests for scrape_and_store_tweets** - `f748aa2` (test)
3. **Task 2: GREEN — implement scrape_and_store_tweets** - `88288d8` (feat)

**Plan metadata:** _(this commit)_

_Note: TDD task has two commits: test (RED) then feat (GREEN)_

## Files Created/Modified

- `formats/tweets/scraper.py` — `_scrape_async` leak fixed; `scrape_and_store_tweets()` added to public API section; `from __future__ import annotations` and `TYPE_CHECKING` guard added for `ChannelConfig` type hint
- `tests/test_tweet_scraper_store.py` — 11 tests: accounts routing, summary dict shape, quality filtering (likes threshold + URL rejection), duplicate handling, and source-level verification of the try/finally fix

## Decisions Made

- `_conn` injection parameter chosen over module-level imports: `analysis.db.get_connection` imports `config` which triggers `channels.yaml` loading at import time, causing `SystemExit` in test environments. Accepting an optional connection parameter lets tests pass in-memory SQLite directly without any mock complexity.
- Lazy imports for `analysis.db`, `pipeline.backlog`, and `pipeline.quality_filter` kept inside the function body to prevent the same import-chain issue from breaking the module in test environments.
- `min_likes=1` passed to `scrape_top_tweets` so all raw tweets are retrieved; quality filtering happens explicitly in `scrape_and_store_tweets` so every rejection is logged with a reason string.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `_conn` parameter for test isolation**
- **Found during:** Task 2 (implementing scrape_and_store_tweets)
- **Issue:** `analysis.db.get_connection` imports `config.py` which calls `load_channels()` at import time; `load_channels()` raises `SystemExit` if `channels.yaml` is missing. This made the function untestable without a full production environment.
- **Fix:** Added `_conn=None` parameter; function creates its own connection only when `_conn is None`. Tests pass in-memory connections directly.
- **Files modified:** `formats/tweets/scraper.py`, `tests/test_tweet_scraper_store.py`
- **Verification:** All 11 tests pass; production path (`_conn=None`) unchanged
- **Committed in:** `88288d8` (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical for testability)
**Impact on plan:** Fix is minimal and fully backward-compatible; production callers pass no `_conn` and get production DB automatically. No scope creep.

## Issues Encountered

- `test_reddit_scraper.py` has a pre-existing import-level failure (`ModuleNotFoundError: No module named 'pipeline.reddit_scraper'`) — this is a RED stub for a future plan and is not caused by this plan's changes. Verified by running the specific test files that were passing before this plan.

## User Setup Required

None — no external service configuration required.

## Self-Check: PASSED

All files exist and all commits verified.

## Next Phase Readiness

- `scrape_and_store_tweets` is ready to be called from `main.py`'s `generate --format tweets --scrape` command path
- Browser leak is resolved — safe to use in batch scraping without Chromium process accumulation
- Remaining concern: `pipeline/reddit_scraper.py` is still missing (pre-existing); `test_reddit_scraper.py` will fail until that plan executes

---
*Phase: 02-content-pipeline*
*Completed: 2026-03-12*
