---
phase: 02-content-pipeline
plan: "04"
subsystem: scraping
tags: [praw, reddit, backlog, quality-filter, sqlite]

# Dependency graph
requires:
  - phase: 02-content-pipeline/02-02
    provides: pipeline/backlog.py insert_story() and pipeline/quality_filter.py passes_story_quality()
  - phase: 02-content-pipeline/02-03
    provides: test_reddit_scraper.py test stubs (RED phase)
provides:
  - pipeline/reddit_scraper.py — PRAW-based Reddit scraper with quality filter and backlog insertion
  - REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT constants in config.py
affects: [main.py scrape command, phase-03-video-generation storytelling format]

# Tech tracking
tech-stack:
  added: [praw>=7.7 (already in requirements.txt, installed in environment)]
  patterns:
    - Lazy imports inside function body to avoid config.py/channels.yaml loading at import time (testability pattern)
    - WINDOW_MAP constant for time window string → PRAW time_filter translation

key-files:
  created:
    - pipeline/reddit_scraper.py
  modified:
    - config.py
    - tests/test_reddit_scraper.py

key-decisions:
  - "Reddit scraper lives at pipeline/reddit_scraper.py (not formats/storytelling/scraper.py) — test file was authoritative"
  - "Lazy imports of config, praw, analysis.db inside scrape_and_store_reddit() to avoid channels.yaml dependency at import time"
  - "is_self check before selftext check — link posts filtered first to avoid parsing garbage body text"
  - "Store post.id (short form) not post.name (fullname with t3_ prefix)"

patterns-established:
  - "Lazy-import pattern: defer config imports to function body when module must be testable standalone"
  - "Isolation pattern: per-subreddit try/except in scrape_channel_subreddits so one failing subreddit never blocks others"

requirements-completed: [REDDIT-01, REDDIT-02, REDDIT-03, REDDIT-04]

# Metrics
duration: 4min
completed: 2026-03-12
---

# Phase 02 Plan 04: Reddit Scraper Summary

**PRAW-based Reddit scraper at pipeline/reddit_scraper.py with per-subreddit isolation, selftext filtering, quality thresholds via passes_story_quality(), and backlog insertion via insert_story()**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-12T02:02:36Z
- **Completed:** 2026-03-12T02:06:16Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT to config.py
- Implemented scrape_subreddit_top() — fetches top posts, skips link posts and invalid selftext
- Implemented scrape_channel_subreddits() — merges all subreddits with dedup by post id, per-subreddit failure isolation
- Implemented scrape_and_store_reddit() — creates PRAW client, runs quality filter, inserts to backlog, returns summary dict
- All 3 tests in test_reddit_scraper.py pass (RED -> GREEN)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Reddit env vars to config.py** - `1eeb880` (chore)
2. **Task 2: Implement pipeline/reddit_scraper.py** - `fbad7cc` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified
- `pipeline/reddit_scraper.py` - PRAW scraper with scrape_subreddit_top, scrape_channel_subreddits, scrape_and_store_reddit
- `config.py` - Added REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT constants
- `tests/test_reddit_scraper.py` - Fixed unused `import config` that caused SystemExit; fixed side_effect signature to match actual function API

## Decisions Made
- Reddit scraper was placed at `pipeline/reddit_scraper.py` rather than `formats/storytelling/scraper.py` — the test file was the authoritative contract (it imported from `pipeline.reddit_scraper`)
- Used lazy imports inside `scrape_and_store_reddit()` body for config, praw, analysis.db — this avoids triggering `channels.yaml` loading at import time, keeping the module testable in isolation
- `is_self` check comes before selftext validity check — link posts may have non-empty selftext that is junk content

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_reddit_scraper.py: removed unused `import config` in test body**
- **Found during:** Task 2 (TDD GREEN phase)
- **Issue:** `import config` at line 79 in test body caused SystemExit (channels.yaml not found), blocking test execution
- **Fix:** Removed the unused import — it was dead code, nothing in the test used it
- **Files modified:** tests/test_reddit_scraper.py
- **Verification:** test_per_subreddit_failure_isolation collected and ran
- **Committed in:** fbad7cc (Task 2 commit)

**2. [Rule 1 - Bug] Fixed side_effect signature in TestPerSubredditFailureIsolation**
- **Found during:** Task 2 (TDD GREEN phase)
- **Issue:** side_effect(subreddit_name, limit=25) had wrong arity — actual scrape_subreddit_top takes (reddit, subreddit_name, time_filter, limit), so mock was called with 4 args and TypeError resulted
- **Fix:** Updated side_effect to match actual signature: (reddit, subreddit_name, time_filter="day", limit=25)
- **Files modified:** tests/test_reddit_scraper.py
- **Verification:** All 3 tests pass
- **Committed in:** fbad7cc (Task 2 commit)

**3. [Rule 3 - Blocking] Used lazy imports to avoid channels.yaml import-time failure**
- **Found during:** Task 2 (initial test run after creating pipeline/reddit_scraper.py)
- **Issue:** `import config` at module level caused channels.yaml SystemExit during test collection
- **Fix:** Moved config, praw, analysis.db imports inside scrape_and_store_reddit() body; removed module-level praw import
- **Files modified:** pipeline/reddit_scraper.py
- **Verification:** `from pipeline.reddit_scraper import scrape_and_store_reddit` imports without error
- **Committed in:** fbad7cc (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs in test file, 1 Rule 3 blocking import)
**Impact on plan:** All fixes necessary to reach GREEN. No scope creep. The test file had stale API assumptions from when the function signature was first drafted.

## Issues Encountered
- The plan specified `formats/storytelling/scraper.py` as the output artifact, but the test file imported from `pipeline.reddit_scraper`. The test file was treated as authoritative (TDD contract).

## User Setup Required
**External services require manual configuration before `scrape_and_store_reddit()` will work against live Reddit API:**
- `REDDIT_CLIENT_ID` — from https://www.reddit.com/prefs/apps (Create App → script type)
- `REDDIT_CLIENT_SECRET` — same app page
- `REDDIT_USER_AGENT` — any descriptive string, e.g. "auto-shorts/1.0 (by /u/yourusername)"

## Next Phase Readiness
- Reddit scraper complete; wiring to `main.py scrape --format storytelling` is the remaining step
- All backlog/quality/scraper tests green (17 tests across test_reddit_scraper, test_backlog, test_quality_filter)
- test_tts.py and test_config_channels.py require channels.yaml to exist — pre-existing issue, out of scope

---
*Phase: 02-content-pipeline*
*Completed: 2026-03-12*
