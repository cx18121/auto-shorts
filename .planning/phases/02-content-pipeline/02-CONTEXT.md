# Phase 2: Content Pipeline - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Reddit posts and tweets are scraped, scored, and stored in a per-channel backlog that the scheduler (Phase 4) can pull from. This phase delivers: Reddit scraper, tweet scraper integration, backlog DB schema, quality scoring, and the review/backlog-status CLI commands. Video generation and upload are NOT in scope — this phase ends at approved items sitting in the backlog.

</domain>

<decisions>
## Implementation Decisions

### Approval model
- Items that pass quality scoring thresholds are **auto-approved** — no human step required
- **Probation period**: first 25 items per niche stay `pending` regardless of score; manual review required before auto-approve activates for that niche
- Probation threshold is tracked in the DB (per niche) — once 25 items have been manually reviewed, auto-approve activates
- Rejected items are kept in DB with `status='rejected'` (never deleted) — supports threshold auditing and tuning
- Same approval rules apply to both Reddit stories and tweets

### Scraping CLI
- New `scrape` subcommand: `python main.py --channel X scrape --format reddit|tweets`
- Consistent with existing `generate --format` pattern from Phase 1
- **Bootstrap mode**: `--window month` scrapes top posts from the last 30 days (for initial backlog fill)
- **Daily mode**: default window is `24h` (top posts from last 24 hours for ongoing runs)
- Target volume: 25-50 posts per niche per scrape run
- Reddit and tweet scraping share the same `scrape` command; Phase 4 scheduler calls it directly

### Quality thresholds
- All thresholds are **fully defined in `channels.yaml`** — no hard-coded defaults in code
- Each channel block in channels.yaml includes a `quality` section with threshold fields
- **Reddit stories**:
  - `min_upvotes`: 1000 (posts below this are rejected)
  - `min_words`: 400 (below this = too short to narrate, rejected)
  - `max_words`: 1200 (above this = too long for 90s target, rejected — no truncation)
- **Tweets**:
  - `min_likes`: 1000 (tweets below this are rejected)
- Both extremes rejected strictly — no truncation, no soft flags

### Backlog DB schema
- Backlog lives in `data/pipeline.db` (existing SQLite DB)
- Two tables: `backlog_stories` and `backlog_tweets`
- Item status flow: `pending` → `approved` → `used` (or `rejected` as terminal state)
- Both tables include: `channel` (niche slug), `status`, `score`/`likes`, `word_count`, `scraped_at`, `approved_at`, `used_at`
- Per-niche probation state tracked in a `niche_state` table: `channel`, `manually_reviewed_count`

### Review CLI
- `python main.py --channel X review` — item-by-item, full text shown for each item
- Display per item: source (reddit/twitter), subreddit or account, score/likes, word count, full title + full body text
- Interactive prompt per item: `Approve? (y/n/skip):`
- Respects `--channel` flag: `--channel relationships` shows only relationships items; `--channel all` iterates all channels
- Separate `backlog-status` command: `python main.py --channel all backlog-status` prints pending/approved/used/rejected counts per niche — quick health check without triggering review flow
- Probation count tracked and displayed: "Auto-approve activates after X more manual reviews"

</decisions>

<specifics>
## Specific Ideas

- Bootstrap scrape (`--window month`) is meant to be run once per niche to seed the initial backlog before the daily cadence takes over
- The probation display message should make the threshold explicit so the user knows how many more reviews unlock auto-approve

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data/pipeline.db` (SQLite): Existing DB with WAL mode; backlog tables extend it — no new DB file needed
- `analysis/db.py`: Existing schema + connection factory pattern to follow for new backlog tables
- `formats/tweets/scraper.py`: Existing twscrape-based tweet scraper — wires into the new `scrape --format tweets` command
- `config.py`: `CHANNELS` dict (added in Phase 1) — `get_channel(slug)` provides per-channel config including quality thresholds from channels.yaml
- `main.py` argparse: Existing subcommand pattern + `--channel` global flag — `scrape`, `review`, `backlog-status` added as new subcommands

### Established Patterns
- Functions over classes; type hints on all functions
- External API calls: 3 retries + exponential backoff; failed items log and continue
- Logging via `logging.getLogger(__name__)` in every module; INFO for steps, WARNING for retries, ERROR for failures
- `--channel` is always required; `--channel all` runs sequentially across all three niches

### Integration Points
- `main.py`: Add `scrape`, `review`, `backlog-status` to argparse subcommands; route through `--channel`
- `channels.yaml`: Add `quality:` section to each channel block with threshold fields
- `data/pipeline.db`: New `backlog_stories`, `backlog_tweets`, `niche_state` tables
- `formats/tweets/scraper.py`: Called by `scrape --format tweets`; existing Playwright + cookie auth path
- Phase 4 scheduler will call `scrape --format reddit` and `scrape --format tweets` as subprocesses

### Concerns to address
- twscrape authentication is brittle (noted in codebase concerns); consider whether Playwright cookie scraper should fully replace it in this phase
- Playwright browser resource leaks on error paths — fix before batch scraping runs

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-content-pipeline*
*Context gathered: 2026-03-11*
