# Phase 2: Content Pipeline - Research

**Researched:** 2026-03-11
**Domain:** Reddit scraping, SQLite backlog state machine, quality filtering, interactive CLI
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Approval model
- Items that pass quality scoring thresholds are **auto-approved** — no human step required
- **Probation period**: first 25 items per niche stay `pending` regardless of score; manual review required before auto-approve activates for that niche
- Probation threshold is tracked in the DB (per niche) — once 25 items have been manually reviewed, auto-approve activates
- Rejected items are kept in DB with `status='rejected'` (never deleted) — supports threshold auditing and tuning
- Same approval rules apply to both Reddit stories and tweets

#### Scraping CLI
- New `scrape` subcommand: `python main.py --channel X scrape --format reddit|tweets`
- Consistent with existing `generate --format` pattern from Phase 1
- **Bootstrap mode**: `--window month` scrapes top posts from the last 30 days (for initial backlog fill)
- **Daily mode**: default window is `24h` (top posts from last 24 hours for ongoing runs)
- Target volume: 25-50 posts per niche per scrape run
- Reddit and tweet scraping share the same `scrape` command; Phase 4 scheduler calls it directly

#### Quality thresholds
- All thresholds are **fully defined in `channels.yaml`** — no hard-coded defaults in code
- Each channel block in channels.yaml includes a `quality` section with threshold fields
- **Reddit stories**:
  - `min_upvotes`: 1000 (posts below this are rejected)
  - `min_words`: 400 (below this = too short to narrate, rejected)
  - `max_words`: 1200 (above this = too long for 90s target, rejected — no truncation)
- **Tweets**:
  - `min_likes`: 1000 (tweets below this are rejected)
- Both extremes rejected strictly — no truncation, no soft flags

#### Backlog DB schema
- Backlog lives in `data/pipeline.db` (existing SQLite DB)
- Two tables: `backlog_stories` and `backlog_tweets`
- Item status flow: `pending` → `approved` → `used` (or `rejected` as terminal state)
- Both tables include: `channel` (niche slug), `status`, `score`/`likes`, `word_count`, `scraped_at`, `approved_at`, `used_at`
- Per-niche probation state tracked in a `niche_state` table: `channel`, `manually_reviewed_count`

#### Review CLI
- `python main.py --channel X review` — item-by-item, full text shown for each item
- Display per item: source (reddit/twitter), subreddit or account, score/likes, word count, full title + full body text
- Interactive prompt per item: `Approve? (y/n/skip):`
- Respects `--channel` flag: `--channel relationships` shows only relationships items; `--channel all` iterates all channels
- Separate `backlog-status` command: `python main.py --channel all backlog-status` prints pending/approved/used/rejected counts per niche — quick health check without triggering review flow
- Probation count tracked and displayed: "Auto-approve activates after X more manual reviews"

### Claude's Discretion

None specified beyond locked decisions.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REDDIT-01 | Pipeline can scrape top posts from configured subreddits using PRAW or Reddit JSON API | PRAW `subreddit.top(time_filter=...)` with read-only client_id/secret; Reddit JSON API as fallback |
| REDDIT-02 | Scraped posts are scored by engagement and filtered by minimum quality thresholds | Threshold logic in quality module using config values from channels.yaml |
| REDDIT-03 | Scraped posts are stored in the SQLite backlog with metadata | `backlog_stories` table in pipeline.db extending existing `init_db()` pattern |
| REDDIT-04 | Scraper respects Reddit rate limits and handles failures gracefully | PRAW auto-handles rate limits; JSON API needs explicit 2s delay; both need try/except per niche |
| BACKLOG-01 | SQLite DB maintains separate backlog queues for stories (per niche) and tweets (per niche) | `backlog_stories` + `backlog_tweets` tables with `channel` column for per-niche isolation |
| BACKLOG-02 | Backlog items have status: pending → approved → used | Status column + `approved_at`/`used_at` timestamps; `niche_state` table for probation tracking |
| BACKLOG-03 | Scheduler only pulls from approved backlog items | `WHERE status='approved'` query interface; scraping and approval are separate operations |
| BACKLOG-04 | CLI command to review and approve/reject pending backlog items | `review` subcommand with `input()` loop; `backlog-status` for quick counts |
| QUALITY-01 | Stories scored on length fit, engagement, content appropriateness | word_count range check + min_upvotes from channel config; no AI needed — pure threshold logic |
| QUALITY-02 | Tweets scored on like count, retweet count, text quality | min_likes from channel config + text heuristics (no links, no spam mentions) |
| QUALITY-03 | Items below quality threshold rejected before entering backlog | Reject at scrape time — never INSERT rejected items as pending, OR insert with status='rejected' for audit trail |
</phase_requirements>

## Summary

Phase 2 builds the content supply chain: a Reddit scraper, tweet scraper integration, quality filter, and SQLite backlog with a state machine. All components sit between raw internet content and the video generation pipeline — nothing in this phase touches TTS, FFmpeg, or uploads.

The Reddit scraper choice is between PRAW (official Python wrapper requiring app credentials) and the public JSON API (`/r/subreddit/top.json?t=day&limit=100`) which requires no credentials. The JSON API is simpler to set up but has tighter rate limits (~10 requests/min unauthenticated vs 60/min for PRAW). Given the requirements call out PRAW or JSON API as options, PRAW is the right default: it handles rate-limit sleeps automatically, provides typed objects, and the `time_filter` parameter maps exactly to the `--window` flag decisions.

The backlog is a straightforward SQLite state machine extending the existing `pipeline.db`. The existing `analysis/db.py` pattern (WAL mode, `sqlite3.Row` factory, `init_db()` DDL function) should be followed precisely. Quality filtering is pure threshold logic — no AI calls needed for this phase. The review CLI uses Python's `input()` in a loop, which works cleanly for the described one-item-at-a-time flow.

**Primary recommendation:** Use PRAW with a read-only Reddit app (script type) for Reddit scraping; extend `analysis/db.py`'s `init_db()` with backlog tables; quality scoring is pure rule-based (no Claude calls).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| praw | >=7.7 | Reddit API access (top posts by time window) | Official Python wrapper; auto-handles rate limits; typed models |
| sqlite3 | stdlib | Backlog persistence | Already in use via `analysis/db.py`; WAL mode already configured |
| pyyaml | already installed | Read quality thresholds from channels.yaml | Already used in `config.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| requests | already installed | Reddit JSON API fallback (no app credentials) | If PRAW credentials unavailable; simpler for read-only bulk fetch |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PRAW | Reddit JSON API | JSON API: zero credentials, but ~10 req/min unauthenticated, no typing; use as fallback |
| PRAW | pushshift/reddit-api-client | pushshift is unreliable; stick with PRAW |

**Installation:**
```bash
pip install praw
```
Add `praw` to `requirements.txt`.

## Architecture Patterns

### Recommended Project Structure
New files to create:
```
formats/
└── storytelling/
    └── scraper.py         # Reddit scraper (new — mirrors tweets/scraper.py structure)
pipeline/
└── backlog.py             # DB operations for backlog tables (new)
pipeline/
└── quality_filter.py      # Threshold-based quality scoring for scraped content (new)
```

Modules to modify:
```
analysis/db.py             # Add init_backlog_tables() called from init_db()
config.py                  # Extend ChannelConfig dataclass with quality fields
channels.yaml.example      # Add quality: section to each channel block
main.py                    # Add scrape, review, backlog-status subcommands
```

### Pattern 1: PRAW Read-Only Initialization
**What:** Create a Reddit instance with `client_id`, `client_secret`, `user_agent` only — no username/password. PRAW automatically handles rate limits internally.
**When to use:** All Reddit scraping calls.
**Example:**
```python
# Source: https://praw.readthedocs.io/en/stable/getting_started/quick_start.html
import praw

reddit = praw.Reddit(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    user_agent="auto-shorts/1.0 (by /u/YOUR_USERNAME)",
    # No username/password = read-only mode
)
reddit.read_only = True  # Explicit read-only; prevents accidental writes
```

### Pattern 2: Top Posts with Time Window
**What:** Fetch up to 100 posts sorted by top, filtered by time window. `time_filter` maps to the `--window` flag (day=24h, month=bootstrap).
**When to use:** Both daily and bootstrap scrape modes.
**Example:**
```python
# Source: https://praw.readthedocs.io/en/stable/code_overview/models/subreddit.html
subreddit = reddit.subreddit("relationship_advice")
posts = list(subreddit.top(time_filter="day", limit=100))
# time_filter: "hour" | "day" | "week" | "month" | "year" | "all"
```

### Pattern 3: SQLite Backlog State Machine
**What:** Extend `init_db()` in `analysis/db.py` with three new tables. Status transitions are done with explicit UPDATE statements, never blind rewrites.
**When to use:** All backlog persistence operations.
**Example:**
```python
# Source: existing analysis/db.py pattern
BACKLOG_DDL = """
CREATE TABLE IF NOT EXISTS backlog_stories (
    id              TEXT PRIMARY KEY,     -- reddit post id
    channel         TEXT NOT NULL,        -- niche slug
    subreddit       TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    score           INTEGER NOT NULL,     -- upvotes
    word_count      INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|used
    scraped_at      TEXT NOT NULL,
    approved_at     TEXT,
    used_at         TEXT
);

CREATE TABLE IF NOT EXISTS backlog_tweets (
    tweet_id        TEXT PRIMARY KEY,
    channel         TEXT NOT NULL,
    username        TEXT NOT NULL,
    tweet_text      TEXT NOT NULL,
    likes           INTEGER NOT NULL,
    retweets        INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    scraped_at      TEXT NOT NULL,
    approved_at     TEXT,
    used_at         TEXT
);

CREATE TABLE IF NOT EXISTS niche_state (
    channel                 TEXT PRIMARY KEY,
    manually_reviewed_count INTEGER NOT NULL DEFAULT 0
);
"""
```

### Pattern 4: Quality Threshold Filter (No AI)
**What:** Pure rule-based rejection using thresholds from `ChannelConfig.quality`. No Claude API calls needed for this phase.
**When to use:** Called immediately after scraping before any DB insert of `pending` items.
**Example:**
```python
def passes_story_quality(post_dict: dict, quality_cfg: dict) -> tuple[bool, str]:
    """Returns (passes, reason). Reason is empty string if passes."""
    if post_dict["score"] < quality_cfg["min_upvotes"]:
        return False, f"upvotes {post_dict['score']} < {quality_cfg['min_upvotes']}"
    if post_dict["word_count"] < quality_cfg["min_words"]:
        return False, f"word_count {post_dict['word_count']} < {quality_cfg['min_words']}"
    if post_dict["word_count"] > quality_cfg["max_words"]:
        return False, f"word_count {post_dict['word_count']} > {quality_cfg['max_words']}"
    return True, ""
```

### Pattern 5: Per-Niche Isolation with `--channel all`
**What:** The `--channel all` loop pattern (established in Phase 1 in `main.py`) must be used for scrape, review, and backlog-status. Each niche's scrape failure is caught and logged without stopping the loop.
**When to use:** All three new subcommands.
**Example:**
```python
# Each niche is independent — failure of one must not block others
for slug, channel_cfg in config.CHANNELS.items():
    try:
        run_scrape(channel_cfg, fmt, window)
    except Exception as e:
        logger.error("Scrape failed for %s: %s", slug, e)
        # continue to next niche
```

### Pattern 6: Interactive Review CLI
**What:** `input()` loop in a terminal — no external library needed. Reads `pending` items ordered by `scraped_at ASC`, displays full text, accepts y/n/skip.
**When to use:** `review` subcommand.
**Example:**
```python
def cmd_review(channel_cfg: ChannelConfig) -> None:
    items = backlog.get_pending_stories(channel_cfg.slug)
    for item in items:
        print(f"\n--- Reddit | r/{item['subreddit']} ---")
        print(f"Score: {item['score']:,}  Words: {item['word_count']}")
        print(f"\n{item['title']}\n\n{item['body']}")
        choice = input("\nApprove? (y/n/skip): ").strip().lower()
        if choice == "y":
            backlog.approve_item("backlog_stories", item["id"], channel_cfg.slug)
        elif choice == "n":
            backlog.reject_item("backlog_stories", item["id"])
        # "skip" or anything else: do nothing
```

### Anti-Patterns to Avoid
- **Hard-coded thresholds in code:** All quality thresholds live in `channels.yaml` — never `if upvotes < 1000` in Python.
- **Deleting rejected items:** Rejected items stay in DB with `status='rejected'` for audit trail and threshold tuning.
- **Calling Claude API for quality scoring in this phase:** Threshold logic only — the `formats/tweets/quality.py` Claude-based scorer is for AI-generated content, not scraped content.
- **Playwright browser context not closed on exception:** The existing `_scrape_async` has a try/except gap where `browser.close()` can be skipped on error. Use `try/finally` or async context manager properly.
- **Inserting duplicate Reddit post IDs:** Use `INSERT OR IGNORE` since the `id` column is PRIMARY KEY — idempotent scrape runs are essential.
- **Fetching selftext for link posts:** PRAW returns `selftext=""` for link posts and `"[removed]"` for removed posts. Filter both before word counting.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reddit rate-limit handling | Custom sleep + retry loop | PRAW built-in | PRAW sleeps automatically when rate-limited; handles 429 responses |
| Reddit pagination | Manual `after` cursor tracking | PRAW ListingGenerator | PRAW's generator yields all items transparently |
| Cookie file parsing | Custom Netscape parser | Already in `scraper.py` `_load_playwright_cookies()` | Already implemented and tested |
| YAML quality config loading | Custom parser | `config.py` `load_channels()` + `ChannelConfig` dataclass | Already wired — just add fields to `ChannelConfig` |

**Key insight:** PRAW abstracts away Reddit's pagination and rate-limit complexity entirely. The JSON API alternative is viable but requires manual cursor (`after`) handling and explicit sleep calls.

## Common Pitfalls

### Pitfall 1: PRAW `selftext` Field Edge Cases
**What goes wrong:** `post.selftext` can be `""` (link post, no body), `"[removed]"` (mod-removed), `"[deleted]"` (user-deleted). Word-counting these produces garbage results — a removed post has 1 word.
**Why it happens:** PRAW returns these sentinel strings rather than None.
**How to avoid:** Filter before insertion:
```python
INVALID_SELFTEXT = {"", "[removed]", "[deleted]"}
if post.selftext in INVALID_SELFTEXT:
    continue  # skip — no usable body text
```
**Warning signs:** Backlog fills with 1-word stories.

### Pitfall 2: Reddit Post `id` vs `name` vs URL
**What goes wrong:** Confusing `post.id` (e.g. `"abc123"`) with `post.name` (e.g. `"t3_abc123"`) when storing the primary key. PRAW uses `id` for the short ID; `name` prefixes it with `t3_`.
**Why it happens:** Reddit's API uses `name` (fullname) for many operations but `id` in URLs.
**How to avoid:** Store `post.id` (the short form) as the primary key — matches URL slugs, simpler for dedup.

### Pitfall 3: Playwright Browser Leak on Scrape Error
**What goes wrong:** If `_scrape_async` raises between `browser = await pw.chromium.launch()` and `await browser.close()`, the browser process is orphaned. Over multiple scrape runs, leaked Chromium processes accumulate.
**Why it happens:** Current `_scrape_async` uses try/except per-account but no `finally` around `browser.close()`.
**How to avoid:** Wrap the entire scrape body in `try/finally`:
```python
browser = await pw.chromium.launch(headless=True)
try:
    # ... all scraping ...
finally:
    await browser.close()
```
**Warning signs:** `ps aux | grep chromium` shows multiple orphan processes after scrape runs.

### Pitfall 4: `--window` CLI Flag Maps to PRAW `time_filter`
**What goes wrong:** `--window month` should pass `time_filter="month"` to PRAW, and `--window 24h` (daily) should pass `time_filter="day"`. The mapping must be explicit — PRAW does not accept `"24h"`.
**Why it happens:** The CLI decision uses `24h` as the display label but PRAW uses `"day"`.
**How to avoid:** Map at the CLI boundary:
```python
WINDOW_MAP = {"24h": "day", "month": "month"}
time_filter = WINDOW_MAP.get(args.window, "day")
```

### Pitfall 5: `ChannelConfig` Dataclass Field Addition Breaking Load
**What goes wrong:** Adding `quality` as a new field to `ChannelConfig` without a default value causes `channels.yaml.example` files without the `quality:` section to fail validation on import.
**Why it happens:** `ChannelConfig.__post_init__` validates all fields; missing YAML keys become missing kwargs to `__init__`.
**How to avoid:** Add `quality: dict = field(default_factory=dict)` with a default, then validate inside `__post_init__` that required keys exist if the field is populated. Update `channels.yaml.example` in the same task.

### Pitfall 6: `niche_state` Row Missing on First Probation Check
**What goes wrong:** First scrape run queries `niche_state` for probation count, but the row doesn't exist yet — `SELECT` returns None, and `None < 25` raises a TypeError.
**Why it happens:** `INSERT OR IGNORE` pattern isn't used for initialization.
**How to avoid:** Use `INSERT OR IGNORE INTO niche_state (channel, manually_reviewed_count) VALUES (?, 0)` at the start of any function that reads probation state.

## Code Examples

Verified patterns from official sources:

### PRAW Read-Only Top Posts
```python
# Source: https://praw.readthedocs.io/en/stable/code_overview/models/subreddit.html
import praw

def scrape_subreddit_top(
    subreddit_name: str,
    time_filter: str,  # "day" | "week" | "month"
    limit: int,
    reddit: praw.Reddit,
) -> list[dict]:
    """Fetch top posts from a subreddit. Returns list of post dicts."""
    results = []
    try:
        sub = reddit.subreddit(subreddit_name)
        for post in sub.top(time_filter=time_filter, limit=limit):
            if post.selftext in {"", "[removed]", "[deleted]"}:
                continue
            results.append({
                "id": post.id,
                "title": post.title,
                "body": post.selftext,
                "score": post.score,
                "word_count": len(post.selftext.split()),
                "subreddit": subreddit_name,
                "url": f"https://reddit.com{post.permalink}",
            })
    except Exception as e:
        logger.warning("Failed scraping r/%s: %s", subreddit_name, e)
    return results
```

### Idempotent Backlog Insert
```python
# INSERT OR IGNORE ensures re-running scrape doesn't duplicate items
def insert_story(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert story into backlog. Returns True if inserted, False if already exists."""
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        """INSERT OR IGNORE INTO backlog_stories
           (id, channel, subreddit, title, body, score, word_count, status, scraped_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (item["id"], item["channel"], item["subreddit"],
         item["title"], item["body"], item["score"], item["word_count"], now),
    )
    return cursor.rowcount > 0
```

### Probation-Aware Auto-Approve
```python
PROBATION_THRESHOLD = 25

def maybe_auto_approve(conn: sqlite3.Connection, channel: str, item_id: str, table: str) -> None:
    """Auto-approve item if niche has passed probation."""
    row = conn.execute(
        "SELECT manually_reviewed_count FROM niche_state WHERE channel = ?", (channel,)
    ).fetchone()
    if row and row["manually_reviewed_count"] >= PROBATION_THRESHOLD:
        now = datetime.utcnow().isoformat()
        conn.execute(
            f"UPDATE {table} SET status='approved', approved_at=? WHERE id=?",
            (now, item_id),
        )
```

### Channels.yaml Quality Section (Extended)
```yaml
# channels.yaml.example addition
relationships:
  name: "Relationships"
  format: storytelling
  voice_id: "REPLACE_WITH_ELEVENLABS_VOICE_ID"
  subreddits:
    - relationship_advice
    - AITAH
    - AmItheAsshole
    - tifu
    - TrueOffMyChest
  twitter_accounts:
    - RelationshipAdvic
  quality:
    min_upvotes: 1000
    min_words: 400
    max_words: 1200
    min_likes: 1000      # for tweet format; ignored for storytelling
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| twscrape for tweet scraping | Playwright cookie scraper | Phase 1 (this project) | twscrape brittle after X API changes; already replaced |
| PRAW with username/password | Read-only PRAW (client_id + secret only) | PRAW 7.x | Simpler; no account credentials stored |

**Deprecated/outdated:**
- `setup-twitter` command: Already a no-op stub; `formats/tweets/scraper.py` uses Playwright cookies exclusively.
- twscrape: Listed in `requirements.txt` but the codebase no longer calls it. Can leave for now — removing is out of scope.

## Open Questions

1. **Reddit app credentials storage**
   - What we know: PRAW requires `client_id` and `client_secret`; these aren't in `.env` yet.
   - What's unclear: Should these be per-channel in `channels.yaml` or global in `.env`? They're read-only app credentials shared across all niches.
   - Recommendation: Add `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` to `.env` and `config.py` as global constants. One Reddit app serves all channels.

2. **Tweet scraper account list for finance-hustle**
   - What we know: The existing `VIRAL_ACCOUNTS` list in `scraper.py` is general-purpose. `finance-hustle` channel has its own `twitter_accounts` list in channels.yaml (naval, morganhousel, etc.).
   - What's unclear: Should `scrape --format tweets` use `channel_cfg.twitter_accounts` instead of the hardcoded `VIRAL_ACCOUNTS`?
   - Recommendation: Yes — pass `channel_cfg.twitter_accounts` as the `accounts` parameter to `scrape_top_tweets()`. This is the natural use of per-channel config.

3. **Probation threshold hardcoded vs configurable**
   - What we know: CONTEXT.md says 25 items per niche is the probation threshold.
   - What's unclear: Should this be a constant in code or configurable per-channel in channels.yaml?
   - Recommendation: Define as a module-level constant (`PROBATION_THRESHOLD = 25`) in `pipeline/backlog.py`. It can be promoted to config later without changing the interface.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Python `unittest` (stdlib) — matches existing test files |
| Config file | none — tests run via `python -m pytest tests/` or `python tests/test_*.py` |
| Quick run command | `python -m pytest tests/test_backlog.py tests/test_reddit_scraper.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REDDIT-01 | `scrape_subreddit_top()` returns list of post dicts | unit (mock PRAW) | `python -m pytest tests/test_reddit_scraper.py::test_scrape_returns_posts -x` | ❌ Wave 0 |
| REDDIT-02 | Posts below min_upvotes are filtered out | unit | `python -m pytest tests/test_quality_filter.py::test_story_upvote_filter -x` | ❌ Wave 0 |
| REDDIT-03 | `insert_story()` persists to backlog_stories with correct fields | unit (in-memory SQLite) | `python -m pytest tests/test_backlog.py::test_insert_story -x` | ❌ Wave 0 |
| REDDIT-04 | Scrape loop continues when one subreddit raises exception | unit | `python -m pytest tests/test_reddit_scraper.py::test_per_subreddit_failure_isolation -x` | ❌ Wave 0 |
| BACKLOG-01 | `init_backlog_tables()` creates all three tables | unit (in-memory SQLite) | `python -m pytest tests/test_backlog.py::test_tables_created -x` | ❌ Wave 0 |
| BACKLOG-02 | Status transitions: pending→approved, pending→rejected, approved→used | unit | `python -m pytest tests/test_backlog.py::test_status_transitions -x` | ❌ Wave 0 |
| BACKLOG-03 | `get_approved_items()` returns only approved rows | unit | `python -m pytest tests/test_backlog.py::test_get_approved_only -x` | ❌ Wave 0 |
| BACKLOG-04 | `review` CLI with mock input approves/rejects items | integration (subprocess) | `python -m pytest tests/test_cli_review.py::test_review_approve -x` | ❌ Wave 0 |
| QUALITY-01 | Story rejected if words < min_words or > max_words | unit | `python -m pytest tests/test_quality_filter.py::test_story_word_count_bounds -x` | ❌ Wave 0 |
| QUALITY-02 | Tweet rejected if likes < min_likes | unit | `python -m pytest tests/test_quality_filter.py::test_tweet_likes_filter -x` | ❌ Wave 0 |
| QUALITY-03 | Rejected items never appear in approved query | unit | `python -m pytest tests/test_backlog.py::test_rejected_not_in_approved -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_backlog.py tests/test_quality_filter.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backlog.py` — covers BACKLOG-01, BACKLOG-02, BACKLOG-03, REDDIT-03, QUALITY-03
- [ ] `tests/test_reddit_scraper.py` — covers REDDIT-01, REDDIT-04 (uses `unittest.mock.patch` for PRAW)
- [ ] `tests/test_quality_filter.py` — covers REDDIT-02, QUALITY-01, QUALITY-02
- [ ] `tests/test_cli_review.py` — covers BACKLOG-04 (subprocess, mock stdin)
- [ ] `pytest` install: `pip install pytest` — if not present (not in requirements.txt yet)

## Sources

### Primary (HIGH confidence)
- PRAW official docs (praw.readthedocs.io) — `subreddit.top()`, `time_filter` values, read-only auth pattern
- Reddit JSON API (til.simonwillison.net, jcchouinard.com) — public endpoint format, `t=` parameter, rate limits
- `analysis/db.py` (project codebase) — WAL mode, `sqlite3.Row`, `init_db()` DDL pattern to follow
- `formats/tweets/scraper.py` (project codebase) — Playwright cookie approach, async scrape pattern, browser lifecycle

### Secondary (MEDIUM confidence)
- PRAW rate limit behavior (praw.readthedocs.io/ratelimits) — auto-sleep on 429, `ratelimit_seconds` config
- SQLite WAL mode + queue state machine pattern — multiple sources agree on `BEGIN IMMEDIATE` for status transitions

### Tertiary (LOW confidence)
- Reddit unauthenticated JSON API rate limit (~10 req/min) — reported by multiple secondary sources; not in official Reddit docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PRAW is well-documented; sqlite3 is stdlib; existing codebase patterns verified by reading source
- Architecture: HIGH — follows established patterns in this codebase; no novel technical choices
- Pitfalls: HIGH for PRAW selftext edge cases (documented Reddit behavior); MEDIUM for rate limit specifics

**Research date:** 2026-03-11
**Valid until:** 2026-09-01 (stable — PRAW and SQLite are stable; Reddit JSON API format rarely changes)
