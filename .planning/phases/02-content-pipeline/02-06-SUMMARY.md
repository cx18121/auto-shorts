---
phase: 02-content-pipeline
plan: "06"
subsystem: cli
tags: [argparse, cli, backlog, review, scrape, sqlite]

# Dependency graph
requires:
  - phase: 02-content-pipeline/02-02
    provides: "pipeline/backlog.py get_pending_stories, get_pending_tweets, approve_item, reject_item, get_status_counts, get_probation_remaining"
  - phase: 02-content-pipeline/02-04
    provides: "pipeline/reddit_scraper.py scrape_and_store_reddit()"
  - phase: 02-content-pipeline/02-05
    provides: "formats/tweets/scraper.py scrape_and_store_tweets()"
provides:
  - "main.py: scrape subcommand wired to reddit_scraper.scrape_and_store_reddit() and tweets scraper.scrape_and_store_tweets()"
  - "main.py: review subcommand with y/n/skip interactive loop and probation message"
  - "main.py: backlog-status subcommand printing pending/approved/used/rejected table per channel"
affects:
  - phase-03-video-generation
  - phase-04-scheduler

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy imports inside cmd_* handlers to avoid config.py/channels.yaml load at import time"
    - "channel_cfg.format field drives reddit vs tweet path selection in cmd_review()"

key-files:
  created: []
  modified:
    - main.py

key-decisions:
  - "Reddit scraper import uses pipeline.reddit_scraper (not formats/storytelling/scraper) — Plan 04 placed it there as authoritative per test contract"
  - "cmd_review branches on channel_cfg.format to select backlog table and pending-item query — one function handles both formats"
  - "cmd_backlog_status is called per channel by the --channel all loop in main(); header prints per-channel but function is correct"

patterns-established:
  - "cmd_* handler pattern: each CLI subcommand has a dedicated top-level function with lazy imports"

requirements-completed:
  - BACKLOG-03
  - BACKLOG-04
  - REDDIT-04

# Metrics
duration: 3min
completed: 2026-03-12
---

# Phase 2 Plan 06: CLI Wiring — scrape, review, backlog-status Summary

**Three new CLI subcommands wired to channel-aware handlers completing Phase 2 content pipeline operational interface: scrape drives backlog ingestion, review provides human probation gating, backlog-status gives health-check counts.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-12T02:12:41Z
- **Completed:** 2026-03-12T02:16:00Z
- **Tasks:** 1 (Task 2 is human-verify checkpoint)
- **Files modified:** 1

## Accomplishments

- Added `scrape` argparse subcommand with `--format {reddit,tweets}` and `--window {24h,month}`, routed to `pipeline.reddit_scraper.scrape_and_store_reddit()` or `formats.tweets.scraper.scrape_and_store_tweets()`
- Added `review` subcommand with interactive y/n/skip loop, probation countdown message, and per-format item display (Reddit: title/body/score vs Twitter: tweet_text/likes/retweets)
- Added `backlog-status` subcommand printing pending/approved/used/rejected table per channel
- All 39 tests pass (1 skip expected: test_cli_review.py)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add scrape, review, backlog-status subcommands** - `f8bc8f2` (feat)

**Plan metadata:** _(this commit)_

## Files Created/Modified

- `main.py` — argparse subcommands (scrape, review, backlog-status) added; cmd_scrape(), cmd_review(), cmd_backlog_status() handler functions added; _dispatch_command() routing extended

## Decisions Made

- `cmd_scrape` imports from `pipeline.reddit_scraper` (not `formats.storytelling.scraper`) — Plan 04 determined the module location based on the authoritative test contract
- `cmd_review` branches on `channel_cfg.format == "tweets"` to select the appropriate pending-item query and display format — one function handles both content types
- `cmd_backlog_status` signature accepts `channel_cfg` (not `None`-default for "all") because `--channel all` iterates via the `main()` loop — the header prints once per channel in this mode

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reddit scraper import path corrected**
- **Found during:** Task 1 (implementing cmd_scrape)
- **Issue:** Plan interface spec showed `from formats.storytelling.scraper import scrape_and_store_reddit` but Plan 04 placed the module at `pipeline.reddit_scraper` (test file was authoritative contract)
- **Fix:** Used `from pipeline.reddit_scraper import scrape_and_store_reddit` to match actual module location
- **Files modified:** main.py
- **Verification:** `python3 main.py --channel relationships scrape --help` runs without ImportError
- **Committed in:** f8bc8f2 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — import path mismatch from Plan 04 relocation)
**Impact on plan:** Fix is trivial and necessary for correctness. The plan's interface section referenced the original intended path, but Plan 04's execution summary and STATE.md decisions already documented the actual location.

## Issues Encountered

None — channels.yaml needed to be created from channels.yaml.example for CLI testing; this is a pre-existing environment requirement.

## User Setup Required

None — no external service configuration required beyond existing credentials already documented.

## Next Phase Readiness

- Full Phase 2 content pipeline operational: scrape → quality-filter → backlog insert → human review → approved queue
- `scrape`, `review`, `backlog-status` ready for Phase 4 scheduler to call directly
- Reddit credentials (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET) still needed for live Reddit scraping
- X cookies (data/x.com_cookies.txt) still needed for live tweet scraping

## Self-Check: PASSED

- `main.py` modified — confirmed present
- Commit `f8bc8f2` — verified via git log

---
*Phase: 02-content-pipeline*
*Completed: 2026-03-12*
