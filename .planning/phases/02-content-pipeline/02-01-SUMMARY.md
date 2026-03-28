---
phase: 02-content-pipeline
plan: "01"
subsystem: database
tags: [sqlite, pytest, praw, backlog, quality-filter, tdd]

# Dependency graph
requires:
  - phase: 01-niche-config-multi-channel-foundation
    provides: ChannelConfig dataclass, channels.yaml structure, analysis/db.py init_db() pattern

provides:
  - init_backlog_tables() DDL function in analysis/db.py with backlog_stories, backlog_tweets, niche_state
  - ChannelConfig.quality field (dict, default_factory=dict) for per-channel thresholds
  - channels.yaml.example quality: blocks for all three channels
  - pytest and praw>=7.7 in requirements.txt
  - Four RED test stubs (test_backlog.py, test_reddit_scraper.py, test_quality_filter.py, test_cli_review.py)

affects:
  - 02-02 (backlog module — imports init_backlog_tables from analysis.db, tests turn GREEN)
  - 02-03 (reddit scraper — test_reddit_scraper.py defines behavioral contract)
  - 02-04 (quality filter — test_quality_filter.py defines behavioral contract)
  - 02-05 (CLI review — test_cli_review.py integration stub)
  - 02-06 (tweet scraper — uses backlog_tweets table)

# Tech tracking
tech-stack:
  added: [praw>=7.7, pytest>=7.0]
  patterns:
    - TDD RED stubs define behavioral contracts before implementation
    - init_backlog_tables(conn) separate function pattern for organized DDL
    - quality dict on ChannelConfig read via .get() in downstream code (no validation at config load time)

key-files:
  created:
    - tests/test_backlog.py
    - tests/test_reddit_scraper.py
    - tests/test_quality_filter.py
    - tests/test_cli_review.py
  modified:
    - analysis/db.py
    - config.py
    - channels.yaml.example
    - requirements.txt

key-decisions:
  - "quality field on ChannelConfig uses default_factory=dict — empty dict is valid; downstream code uses .get() so missing keys return None without validation errors at load time"
  - "init_backlog_tables() takes conn parameter (not called via get_connection() itself) — allows in-memory SQLite usage in tests"
  - "test_cli_review.py uses @unittest.skip stub — full integration requires Plan 02-02 backlog module and Plan 02-05 CLI review command to be complete first"

patterns-established:
  - "TDD RED stubs: test files import not-yet-built modules; ImportError is the correct RED state"
  - "In-memory SQLite in tests: sqlite3.connect(':memory:') + init_backlog_tables(conn) pattern"

requirements-completed: [BACKLOG-01, BACKLOG-02, BACKLOG-03, REDDIT-03, QUALITY-01, QUALITY-02, QUALITY-03, REDDIT-01, REDDIT-04, BACKLOG-04]

# Metrics
duration: 6min
completed: 2026-03-12
---

# Phase 2 Plan 01: Foundation Schema + RED Test Stubs Summary

**SQLite backlog schema (3 tables), ChannelConfig.quality dict field, and four RED test stub files that define behavioral contracts for Plans 02-02 through 02-05**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-12T01:50:09Z
- **Completed:** 2026-03-12T01:55:31Z
- **Tasks:** 2
- **Files modified:** 8 (4 modified + 4 created)

## Accomplishments
- Extended pipeline.db schema with backlog_stories, backlog_tweets, and niche_state tables via init_backlog_tables()
- Added quality: dict field to ChannelConfig dataclass with per-channel thresholds in channels.yaml.example
- Created four RED test stub files covering all 10 Phase 2 requirements (BACKLOG-01 through BACKLOG-04, REDDIT-01/03/04, QUALITY-01/02/03)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend DB schema, add quality to ChannelConfig, update example** - `47a2686` (feat)
2. **Task 2: Create RED test stubs for all Phase 2 modules** - `04f9530` (test)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks both have single commits — RED state requires no passing tests to refactor_

## Files Created/Modified
- `analysis/db.py` - Added init_backlog_tables(conn) with 3-table DDL; called from init_db()
- `config.py` - Added `quality: dict = field(default_factory=dict)` to ChannelConfig
- `channels.yaml.example` - Added quality: block to all 3 channels with threshold values
- `requirements.txt` - Added praw>=7.7 and pytest>=7.0
- `tests/test_backlog.py` - RED stubs: init_backlog_tables, insert_story, approve/reject/used transitions, get_approved_stories
- `tests/test_reddit_scraper.py` - RED stubs: scrape_subreddit_top, selftext filters, per-subreddit failure isolation
- `tests/test_quality_filter.py` - RED stubs: passes_story_quality, passes_tweet_quality with threshold checks
- `tests/test_cli_review.py` - Integration stub with @unittest.skip (collects, skips, doesn't block CI)

## Decisions Made
- quality field defaults to empty dict with no __post_init__ validation — downstream code uses .get() so absent keys return None gracefully
- init_backlog_tables accepts conn parameter rather than calling get_connection() internally, enabling in-memory SQLite in unit tests
- test_cli_review.py uses @unittest.skip because full integration requires both Plan 02-02 (backlog module) and Plan 02-05 (CLI review command) to exist

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- channels.yaml (not channels.yaml.example) must exist at the Windows path (/mnt/c/...) because config.py resolves BASE_DIR via Path(__file__).parent which points to the WSL mount of the Windows files. Copied channels.yaml.example to channels.yaml at the Windows path for verification runs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DB schema contracts are in place; Plan 02-02 can implement pipeline/backlog.py and turn test_backlog.py GREEN
- ChannelConfig.quality is available; Plans 02-03/04 can read thresholds via channel_cfg.quality.get(...)
- pytest infrastructure ready; all downstream plans use pytest for TDD

---
*Phase: 02-content-pipeline*
*Completed: 2026-03-12*
