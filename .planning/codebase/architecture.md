# Codebase Architecture — Auto-Shorts Pipeline

**Analysis Date:** 2026-03-18

---

## Overview

Auto-Shorts is a CLI-driven video production pipeline that generates YouTube Shorts and Instagram Reels in two formats: **storytelling** (Reddit posts narrated over gameplay) and **tweets** (X/Twitter screenshots with TTS narration). The system is designed around a human-in-the-loop backlog — content is scraped, manually (or AI) reviewed, and then produced and uploaded on demand or via cron.

---

## File Inventory

### Root

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point — 1,463 lines. All commands dispatch here. Serves as parser, dispatcher, orchestrator, interactive UI, and OAuth wizard. |
| `config.py` | Loads `.env`, defines `ChannelConfig` dataclass, parses `channels.yaml`, exposes all path and API key constants. Module-level side effects: loads `.env`, configures logging, creates output dirs, loads all channels at import time. |
| `channels.yaml` | Per-channel config: format, subreddits, twitter accounts, voice ID, quality thresholds, hashtags, OAuth credentials. |
| `requirements.txt` | Python dependencies. |

### `pipeline/` — Shared pipeline components

| File | Lines | Purpose |
|------|-------|---------|
| `pipeline/tts.py` | 158 | ElevenLabs TTS API → MP3 + word-level timestamp JSON. Single public fn: `generate_tts(text, output_dir) -> dict`. |
| `pipeline/overlay.py` | 220 | Converts word timestamps to ASS subtitle file with karaoke-style yellow highlighting. Single public fn: `generate_ass(timestamps_path, output_path, speed_factor)`. |
| `pipeline/backlog.py` | 464 | All SQLite operations for `backlog_stories`, `backlog_tweets`, and `niche_state` tables. Status state machine: `pending → approved → used` (or `rejected`). Probation system: 25 manual reviews required before auto-approve activates. Also provides story-specific convenience wrappers (approve_story, reject_story, mark_story_used) that duplicate the generic approve_item/reject_item/mark_used functions. |
| `pipeline/quality_filter.py` | 93 | Threshold-based quality checks (no Claude). `passes_story_quality` checks upvotes + word count. `passes_tweet_quality` checks likes, URL presence, and @-mention count. All thresholds come from `ChannelConfig.quality`. |
| `pipeline/reddit_scraper.py` | 232 | Reddit public JSON scraper (no API key). Fetches top posts from configured subreddits, quality-filters, and inserts into backlog. |
| `pipeline/upload.py` | 594 | YouTube OAuth upload, Instagram Graph API upload, token refresh, Claude Haiku metadata generation, upload DB logging. |

### `formats/storytelling/` — Reddit/story video format

| File | Lines | Purpose |
|------|-------|---------|
| `formats/storytelling/assembler.py` | 406 | FFmpeg-based video assembly. Two modes: `assemble_video()` (full-screen gameplay + subtitles) and `assemble_split_video()` (gameplay background + scrolling Reddit post PNG overlay + subtitles). |
| `formats/storytelling/generator.py` | 341 | Claude Haiku content generator. Two public fns: `generate_story(profile)` creates AI-originated stories; `adapt_reddit_post(post, channel_slug, profile)` rewrites a real Reddit post into a narration script. |
| `formats/storytelling/quality.py` | 113 | Claude Sonnet quality evaluator. Scores on hook_strength, coherence, engagement, length_appropriateness, style_match (0–10). Pass threshold: 7.0. |
| `formats/storytelling/reddit_renderer.py` | 146 | Renders story text as a Reddit dark-mode screenshot PNG using Playwright + HTML template. Used only when `assemble_split_video()` is called; not in the primary `run-cycle` flow. |
| `formats/storytelling/reddit_template.html` | — | HTML template for Reddit dark-mode post UI. |

### `formats/tweets/` — Tweet screenshot video format

| File | Lines | Purpose |
|------|-------|---------|
| `formats/tweets/assembler.py` | 183 | FFmpeg assembly: static tweet PNG + narration audio + slow zoompan → MP4. Optionally mixes in background music from `assets/music/`. |
| `formats/tweets/generator.py` | 243 | Claude Haiku tweet generator. `generate_tweet(profile)` creates a single AI tweet; `generate_thread(count, profile_path)` creates thematically connected multi-tweet batches. |
| `formats/tweets/quality.py` | 113 | Claude Sonnet quality evaluator for tweets. Scores punchiness, originality, screenshot_worthiness, style_match. Pass threshold: 7.0. |
| `formats/tweets/renderer.py` | 226 | Renders a tweet dict as a 1080×1920 PNG using HTML template + Playwright. Composes tweet screenshot centered on black canvas. This is the primary renderer used by the backlog-based production flow. |
| `formats/tweets/scraper.py` | 630 | Playwright-based X.com scraper. Authenticates via Netscape cookie file (`data/x.com_cookies.txt`). Scrapes curated account profiles + home feed. Filters retweets, replies, media tweets, and low-engagement posts. Fully async internally (`asyncio.run()`), sync public API. |
| `formats/tweets/screenshotter.py` | 113 | Screenshots a real live tweet URL using Playwright. Defined but **not called from any current flow** — effectively dead code. |
| `formats/tweets/tweet_template.html` | — | HTML template for X dark-mode tweet UI. |

### `analysis/` — YouTube channel analysis

| File | Lines | Purpose |
|------|-------|---------|
| `analysis/db.py` | 111 | SQLite connection helper and schema init for `channels`, `videos`, `style_profiles` tables. Also delegates to `pipeline/backlog.py` for backlog tables (creating a cross-module DDL split). |
| `analysis/fetcher.py` | 296 | YouTube Data API v3 client. Resolves channel by URL/handle/ID, paginates uploads playlist (cap: 50), fetches video metadata, filters to Shorts (≤61s). |
| `analysis/transcripts.py` | 136 | Fetches YouTube transcripts via `youtube-transcript-api`. Auth priority: cookies → Webshare proxy → direct. Rate-limited (3s delay). `_ytt_api` is instantiated at module import time as a module-level singleton. |
| `analysis/ranker.py` | 193 | Scores videos by views-per-day relative to channel average. Marks top 20% as `is_top_performer`. Computes channel-level aggregates (posting frequency, best hours/days, top tags). |
| `analysis/profiler.py` | 306 | Multi-step Claude Sonnet analysis: batch analysis of top-performer videos (7 per batch) → merge into unified style profile JSON → save to `style_profiles/` directory and DB. |
| `analysis/visual.py` | 323 | Optional visual analysis: downloads videos via yt-dlp, extracts 9 frames via FFmpeg, sends to Claude Sonnet vision API, saves JSON to DB. |

### `tests/`

| File | Purpose |
|------|---------|
| `tests/test_assembler.py` | Standalone integration test for `assemble_video()` — not a pytest unit test; requires pre-built artifacts. |
| `tests/test_backlog.py` | Unit tests for `pipeline/backlog.py` state transitions using in-memory SQLite. |
| `tests/test_cli_channel_flag.py` | Tests `--channel all` dispatch behavior. |
| `tests/test_cli_review.py` | Tests `cmd_review()` flow. |
| `tests/test_config_channels.py` | Tests `ChannelConfig` validation logic. |
| `tests/test_quality_filter.py` | Tests threshold-based quality filters. |
| `tests/test_reddit_scraper.py` | Tests Reddit scraper with mocked HTTP. |
| `tests/test_run_cycle.py` | Tests full `cmd_run_cycle()` — disabled channel, empty backlog fallback, upload skip conditions, mark-used behavior. Heavy mocking. |
| `tests/test_story_generator.py` | Tests `adapt_reddit_post()` and `generate_story()` with Claude mocked. |
| `tests/test_tts.py` | Standalone integration test — hits real ElevenLabs API. |
| `tests/test_tweet_scraper_store.py` | Tests `scrape_and_store_tweets()`. |
| `tests/test_upload.py` | Tests upload module DB operations and metadata generation. |

---

## Architecture Pattern

The system follows a **pipeline/orchestrator pattern** with a central CLI dispatcher. All commands flow through `main.py`, which sequences calls to the appropriate domain modules.

```
channels.yaml
     │
config.py (ChannelConfig, loaded at import time)
     │
main.py (CLI dispatcher — all commands enter here)
     ├── analyze command
     │     └── analysis/ pipeline: fetch → transcripts → rank → [visual] → profile
     ├── scrape command
     │     ├── pipeline/reddit_scraper.py (storytelling channels)
     │     └── formats/tweets/scraper.py (tweets channels)
     ├── review command
     │     └── pipeline/backlog.py (approve/reject/probation)
     ├── generate command
     │     ├── [storytelling] generator → quality → TTS → overlay → assembler
     │     └── [tweets]       generator → quality → renderer → TTS → assembler
     └── run-cycle command
           ├── backlog.py → pick top approved item
           ├── generate video (same internal pipeline as generate command)
           ├── upload.py → YouTube + Instagram
           └── backlog.py → mark_used
```

---

## Data Flow — Storytelling Format

1. `scrape` command calls `scrape_and_store_reddit()` → Reddit public JSON API → `passes_story_quality()` → `insert_story()` into `backlog_stories` (status=`pending`)
2. `review` command presents pending items; user or Claude approves → status=`approved`
3. `run-cycle` or `generate --from-backlog` picks first approved story (ordered by `approved_at ASC`)
4. `adapt_reddit_post()` calls Claude Haiku to rewrite the Reddit post as a narration script
5. `_generate_with_quality()` wrapper may retry up to 3× with rejection feedback passed back to generator
6. `generate_tts()` calls ElevenLabs → MP3 + word timestamps JSON
7. `generate_ass()` converts timestamps → ASS subtitle file (4 words/block, 2 lines, yellow highlight on active word)
8. `assemble_video()` runs FFmpeg: loops background clip at random start point, center-crops to 9:16, burns subtitles, speeds up audio 1.4× and boosts volume 1.5×
9. `generate_upload_metadata()` calls Claude Haiku for title/description/hashtags
10. `upload_to_youtube()` and `upload_to_instagram()` (run-cycle only)
11. `mark_story_used()` transitions status to `used`

## Data Flow — Tweets Format

1. `scrape` command calls `scrape_and_store_tweets()` → Playwright scrapes X.com (cookie-authenticated home feed + curated accounts) → `passes_tweet_quality()` → `insert_tweet()` into `backlog_tweets`
2. `review` command (same as storytelling)
3. `run-cycle` or `generate --from-backlog` picks first approved tweet (ordered by `approved_at ASC`)
4. `render_tweet()` calls Playwright → fills HTML template → screenshots → composites on 1080×1920 black canvas
5. `generate_tts()` narrates `"@username says: {tweet_text}"`
6. `assemble_tweet_video()` runs FFmpeg: loops static PNG image with slow zoompan (1.0× → ~1.05× over full duration), mixes in optional background music from `assets/music/`, speeds up audio 1.3×
7. Upload metadata + uploads (same as storytelling)
8. `mark_used()` on `backlog_tweets`

---

## Format Comparison

| Aspect | Storytelling | Tweets |
|--------|-------------|--------|
| Content source | Reddit public JSON API (no auth) | X.com via Playwright + cookie auth |
| Content length | 100–1200 words (configurable per channel) | Single tweet ≤240 chars |
| AI rewrite step | Yes — `adapt_reddit_post()` rewrites for narration | No — tweet text used verbatim |
| Visual layer | Full-screen gameplay + ASS subtitle karaoke | Static tweet screenshot PNG on black canvas |
| Motion effect | Video loop with random start point | Slow zoompan on still image |
| Audio speed multiplier | 1.4× | 1.3× |
| Background | Gameplay video clip from `assets/backgrounds/` | Black canvas (optionally + music from `assets/music/`) |
| TTS script | Adapted narration text | `"@username says: {text}"` |
| Quality dimensions | hook_strength, coherence, engagement, length_appropriateness, style_match | punchiness, originality, screenshot_worthiness, style_match |
| Split-screen mode | Available via `assemble_split_video()` + `reddit_renderer.py` | Not applicable |

---

## `main.py` — Detailed Structure and Pain Points

`main.py` is 1,463 lines and serves as: CLI parser, command dispatcher, pipeline orchestrator, interactive TUI, and OAuth setup wizard. This consolidation is the primary structural problem in the codebase.

### Function Map

```
main()                                — argparse setup + channel dispatch
_dispatch_command()                   — routes args.command to cmd_* functions

# Commands
cmd_analyze()                         — orchestrates analysis/ pipeline (4 steps)
cmd_generate()                        — routes to one of 5 sub-flows based on flags
cmd_scrape()                          — scrapes reddit or tweets into backlog
cmd_review()                          — interactive or AI-based backlog review
cmd_backlog_status()                  — prints backlog counts per channel
cmd_run_cycle()                       — full automated cycle (230 lines)
cmd_upload_history()                  — prints upload audit log
cmd_setup_twitter()                   — no-op wrapper (kept for backwards compat)
cmd_setup_youtube()                   — OAuth 2.0 desktop flow
cmd_setup_instagram()                 — token exchange + /me fetch (115 lines of HTTP inline)

# Generate sub-flows (called by cmd_generate)
_generate_storytelling()              — AI-generated stories
_generate_storytelling_from_backlog() — approved posts → video
_generate_tweets()                    — AI-generated tweets
_generate_tweets_from_backlog()       — approved tweets → video
_scrape_tweets()                      — real scrape + immediate video (bypasses backlog)

# Pipeline runners (called by both generate and run-cycle)
_run_storytelling_pipeline()          — TTS → subtitles → assemble (storytelling)
_run_tweet_pipeline()                 — render → TTS → assemble (tweets)

# Shared helpers
_generate_with_quality()              — generate + quality-check + retry loop
_generate_silent_audio()              — ffmpeg null source for --no-audio testing
_save_video_metadata()                — generate + write .txt metadata file
_pick_background()                    — random clip from assets/backgrounds/
_interactive_pick()                   — TUI for selecting backlog stories
_interactive_pick_tweets()            — TUI for selecting backlog tweets (near-duplicate of above)
_ai_review_item()                     — Claude Haiku review for single item (inline, not in a module)
```

### Pain Points in `main.py`

**1. Duplicated pipeline execution code across 3 call sites.**
`_run_storytelling_pipeline()` is called from `_generate_storytelling()`, `_generate_storytelling_from_backlog()`, and `cmd_run_cycle()`. Similarly `_run_tweet_pipeline()` is called from `_generate_tweets()`, `_generate_tweets_from_backlog()`, and `cmd_run_cycle()`. Additionally, `_scrape_tweets()` (the `generate --scrape` flow) does NOT call `_run_tweet_pipeline()` — it inlines its own 3-step render/TTS/assemble sequence directly, creating a third code path doing the same thing. This means the `_scrape_tweets()` flow uses `tweet["text"]` while `_run_tweet_pipeline()` uses `tweet["tweet_text"]` — a subtle key inconsistency.

**2. `_ai_review_item()` is an embedded Claude call (not in a module).**
This ~60-line function at line ~978 constructs an Anthropic client, builds a prompt, and parses JSON — the same pattern as `formats/*/quality.py`, but living directly in `main.py` without separation or testability. The model is hardcoded inline as `"claude-haiku-4-5-20251001"` rather than referencing a shared constant.

**3. `cmd_setup_instagram()` is 115 lines of OAuth logic in the CLI module.**
Lines ~843–957 handle token exchange, `/me` API call with retry loop, and file writing. This belongs in `pipeline/upload.py` (which already owns all other upload concerns) but is stranded in `main.py`.

**4. `cmd_run_cycle()` is 230 lines.**
It handles: enabled check, backlog query + scrape fallback (both formats), video generation (both formats, with inline profile loading that duplicates logic from `_generate_storytelling_from_backlog()`), metadata generation, YouTube upload + error handling, Instagram upload + `INSTAGRAM_PUBLIC_BASE_URL` env var lookup, DB logging, mark-used, and summary. This is the densest function in the codebase.

**5. Two near-identical interactive picker functions.**
`_interactive_pick()` (stories, ~321–347) and `_interactive_pick_tweets()` (tweets, ~350–375) are the same TUI pattern with different column headings. Both could be replaced by one function with a column spec.

**6. Style profile loading duplicated in two places.**
Both `_generate_storytelling_from_backlog()` and `cmd_run_cycle()` contain identical blocks loading and JSON-parsing the style profile from `channel_cfg.style_profile`. Neither calls the other.

**7. Top-level import inconsistency.**
`main.py` imports `generate_tts`, `generate_ass`, and `assemble_video` at the top level (lines 20–22) but imports nearly everything else lazily inside function bodies. This means TTS, overlay, and storytelling assembler always pay import cost regardless of which command is run.

---

## Schema — SQLite (`data/pipeline.db`)

```sql
-- Analysis pipeline tables (defined in analysis/db.py::init_db())
channels         -- YouTube channel metadata
videos           -- Video metadata + derived metrics + transcript text + visual analysis JSON blobs
style_profiles   -- Generated style profile JSON records (also stored as files in style_profiles/)

-- Backlog tables (defined in pipeline/backlog.py::init_backlog_tables())
backlog_stories  -- Reddit posts with status: pending → approved → used | rejected
backlog_tweets   -- X/Twitter tweets with same state machine
niche_state      -- Per-channel manually_reviewed_count (probation tracking)

-- Upload table (defined in pipeline/upload.py::init_upload_table())
uploads          -- Upload audit log (platform, video_id, title, status, error_msg, uploaded_at)
```

**Schema duplication issue:** The DDL for `backlog_stories`, `backlog_tweets`, and `niche_state` is defined identically in two files: `pipeline/backlog.py::init_backlog_tables()` (canonical) and `analysis/db.py::init_backlog_tables()` (delegates to the former but also contains a full copy). Both must be kept in sync if schema changes.

---

## Module Dependency Graph

```
config.py  ←──────────────────────────────── imported by every module
    │
analysis/db.py  ←──── analysis/fetcher, transcripts, ranker, profiler, visual
                ←──── pipeline/backlog (delegates DDL)
                ←──── main.py (run-cycle, review, backlog-status, upload-history)
    │
pipeline/backlog.py  ←──── main.py
                     ←──── pipeline/reddit_scraper.py
                     ←──── formats/tweets/scraper.py

pipeline/tts.py  ←──── main.py (top-level import + lazy)
pipeline/overlay.py  ←──── main.py (top-level import + lazy)
pipeline/upload.py  ←──── main.py
pipeline/quality_filter.py  ←──── pipeline/reddit_scraper.py
                             ←──── formats/tweets/scraper.py
pipeline/reddit_scraper.py  ←──── main.py (cmd_scrape)

formats/storytelling/assembler.py  ←──── main.py (top-level + lazy)
formats/storytelling/generator.py  ←──── main.py
formats/storytelling/quality.py  ←──── main.py
formats/storytelling/reddit_renderer.py  ←──── (not wired into main CLI flow)

formats/tweets/assembler.py  ←──── main.py
formats/tweets/generator.py  ←──── main.py
formats/tweets/quality.py  ←──── main.py
formats/tweets/renderer.py  ←──── main.py
formats/tweets/scraper.py  ←──── main.py (cmd_scrape)
formats/tweets/screenshotter.py  ←──── NOTHING (dead code)
```

---

## Key Configuration Constants

| Constant | Location | Value |
|----------|----------|-------|
| `AUDIO_SPEED` (storytelling) | `formats/storytelling/assembler.py` | 1.4 |
| `AUDIO_SPEED` (tweets) | `formats/tweets/assembler.py` | 1.3 |
| `BLOCK_SIZE` | `pipeline/overlay.py` | 4 words per subtitle block |
| `LINE_SIZE` | `pipeline/overlay.py` | 2 words per line |
| `_MAX_QUALITY_RETRIES` | `main.py` | 3 |
| `_PASS_THRESHOLD` | both `quality.py` files | 7.0 |
| `PROBATION_THRESHOLD` | `pipeline/backlog.py` | 25 manual reviews |
| `_MAX_VIDEOS` | `analysis/fetcher.py` | 50 |
| `_MAX_DURATION_SECONDS` | `analysis/fetcher.py` | 61s (Shorts filter) |
| `_TOP_PERFORMER_PCT` | `analysis/ranker.py` | 0.20 (top 20%) |
| `_DEFAULT_BACKGROUND` | `main.py` | `assets/backgrounds/subwaysurfers.mp4` |
| `_SILENT_DURATION` | `main.py` | 10.0s (for --no-audio testing) |

---

## Disconnected / Dead Code

- **`formats/tweets/screenshotter.py`** — Screenshots real X post URLs via Playwright. Not imported or called from anywhere. Dead code.
- **`formats/storytelling/reddit_renderer.py` and `assemble_split_video()`** — The split-screen Reddit post overlay layout is fully implemented but not wired into `run-cycle` or `generate --from-backlog`. Only reachable via direct Python import.
- **`setup-twitter` command** — Calls `setup_account()` in `formats/tweets/scraper.py` which is now a documented no-op stub (Playwright uses cookie files, not account credentials). The command still appears in the CLI parser.

---

## Inter-Format Code Duplication

The following implementations are copy-pasted between the two format modules:

| Duplicated Pattern | Storytelling Location | Tweets Location |
|-------------------|-----------------------|-----------------|
| `_probe_duration()` — ffprobe to get audio duration | `formats/storytelling/assembler.py:170` | `formats/tweets/assembler.py:163` — identical |
| `_run_ffmpeg()` — subprocess FFmpeg runner | `formats/storytelling/assembler.py:248` | `formats/tweets/assembler.py:175` — identical |
| `_parse_json()` — strip markdown fences + json.loads | `formats/storytelling/generator.py:326` | `formats/tweets/generator.py:228` — identical |
| Markdown fence stripping (inline, not a function) | `formats/storytelling/quality.py:91` | `formats/tweets/quality.py:91`, `analysis/profiler.py:227`, `analysis/visual.py:288`, `pipeline/upload.py:519` — same 4-line pattern in 5 places |
| `_compose_on_canvas()` — Pillow composite on black canvas | `formats/storytelling/reddit_renderer.py` (Pillow) | `formats/tweets/renderer.py:183` — near-identical |
| 3-attempt retry Claude loop | `formats/storytelling/quality.py:80` | `formats/tweets/quality.py:81` — same structure |
| `generate_batch()` — loop N times calling generate | `formats/storytelling/generator.py:162` | `formats/tweets/generator.py:126` — identical pattern |

---

## Output Directory Structure

Each video production run creates a timestamped directory:

```
output/
└── {unix_timestamp}/
    ├── narration.mp3       # ElevenLabs TTS audio
    ├── timestamps.json     # Word-level alignment data
    ├── subtitles.ass       # ASS subtitle file (storytelling only)
    ├── tweet.png           # Rendered tweet screenshot (tweets only)
    ├── reddit_post.png     # Rendered Reddit post PNG (split-screen, if used)
    ├── final.mp4           # Assembled video
    └── final.txt           # Upload metadata (title, description, hashtags)
```

The run ID is `int(time.time())`, which creates a 1-second collision window if two videos are produced in rapid succession.

---

## Error Handling Strategy

- **External API calls:** 3 retries with exponential backoff (`2^attempt` seconds). Failed items log and continue — never block the pipeline.
- **Quality gate:** `_generate_with_quality()` retries up to `_MAX_QUALITY_RETRIES` (3) times, passing the rejection reason as feedback to the generator on each retry. If all retries fail, item is skipped.
- **FFmpeg failures:** `_run_ffmpeg()` logs the last 20 lines of stderr and raises `RuntimeError`. Caught in `_run_storytelling_pipeline()` / `_run_tweet_pipeline()` which return `None`. Callers check for `None` and skip.
- **Run-cycle isolation:** YouTube and Instagram uploads are each in independent try/except blocks so a YouTube failure does not prevent an Instagram attempt.
- **Backlog fallback:** `cmd_run_cycle()` will call `cmd_scrape()` once if the approved backlog is empty, then re-query before giving up.

---

## Testing Approach

Tests are a mix of true pytest unit tests and standalone integration scripts:

- **Pytest unit tests** (`tests/test_backlog.py`, `test_cli_*.py`, `test_config_channels.py`, `test_quality_filter.py`, `test_reddit_scraper.py`, `test_run_cycle.py`, `test_story_generator.py`, `test_tweet_scraper_store.py`, `test_upload.py`): Use `unittest.TestCase` + mocking. Mock `config` module at import time with `sys.modules.setdefault()` to avoid requiring `channels.yaml`. Use in-memory SQLite for DB operations.
- **Standalone integration scripts** (`tests/test_assembler.py`, `tests/test_tts.py`): Run via `python tests/test_xxx.py`, require real API keys and pre-built artifacts. Not discovered by pytest in normal runs.
- **No conftest.py or pytest.ini:** Tests insert `sys.path` manually. No shared fixtures.
- **No coverage enforcement or CI configuration** detected.

---

*Architecture analysis: 2026-03-18*
