# Codebase Structure

**Analysis Date:** 2026-03-11

## Directory Layout

```
auto-shorts/
├── CLAUDE.md                       # Project specification and rules
├── main.py                         # CLI entry point (orchestrator)
├── config.py                       # Environment loading, shared paths, logging setup
├── requirements.txt                # Python dependencies
│
├── analysis/                       # YouTube channel analysis → style profiles
│   ├── __init__.py
│   ├── db.py                       # SQLite schema and connection helper
│   ├── fetcher.py                  # YouTube Data API v3: fetch channel → videos
│   ├── transcripts.py              # youtube-transcript-api: fetch video transcripts
│   ├── ranker.py                   # Performance scoring and top video ranking
│   ├── visual.py                   # Claude vision: analyze frames and thumbnails
│   └── profiler.py                 # Batch analysis + profile merge → JSON style profile
│
├── formats/                        # Format-specific generation and assembly
│   ├── __init__.py
│   ├── storytelling/               # Reddit-style stories + TTS + gameplay background
│   │   ├── __init__.py
│   │   ├── generator.py            # Claude Haiku: story JSON generation
│   │   ├── quality.py              # Claude Sonnet: story quality scoring
│   │   ├── assembler.py            # FFmpeg: background + audio + subtitles → MP4
│   │   └── [future: special effects modules]
│   │
│   └── tweets/                     # Real tweet screenshots + narration
│       ├── __init__.py
│       ├── generator.py            # Claude Haiku: tweet/thread JSON generation
│       ├── quality.py              # Claude Sonnet: tweet quality scoring
│       ├── renderer.py             # Playwright + HTML template: tweet → PNG screenshot
│       ├── screenshotter.py        # [Unused; Playwright browser control utilities]
│       ├── scraper.py              # twscrape: fetch real tweets from curated accounts
│       ├── assembler.py            # FFmpeg: tweet image + audio + zoom animation → MP4
│       ├── tweet_template.html     # X dark mode HTML template (Inter font, SVG icons)
│       └── [future: thread layout modules]
│
├── pipeline/                       # Shared utilities for media processing
│   ├── __init__.py
│   ├── tts.py                      # ElevenLabs: text → MP3 + word-level timestamps JSON
│   ├── overlay.py                  # Word timestamps → ASS subtitle file (grouped phrases)
│   └── [future: upload.py for YouTube/Instagram]
│
├── assets/                         # Static resources
│   ├── backgrounds/                # Gameplay video clips (MP4) for storytelling format
│   ├── fonts/                      # Font files for text rendering (if used)
│   └── music/                      # Royalty-free music tracks (future: background music mixing)
│
├── data/                           # Runtime data
│   ├── pipeline.db                 # SQLite: channels, videos, style_profiles, analysis
│   ├── twscrape_accounts.db        # twscrape account credentials and session state
│   ├── x.com_cookies.txt           # Netscape format cookies for Playwright (gitignored)
│   └── youtube_cookies.txt         # Netscape format cookies for transcript fetching (gitignored)
│
├── output/                         # Generated videos (timestamped subdirectories)
│   └── {unix_timestamp}/           # Working directory per generation run
│       ├── narration.mp3           # TTS audio
│       ├── timestamps.json         # Word-level timing
│       ├── subtitles.ass           # ASS subtitle file (storytelling only)
│       ├── tweet.png               # Rendered tweet screenshot (tweets only)
│       └── final.mp4               # Final assembled video
│
├── style_profiles/                 # Generated JSON style profiles
│   └── {ChannelName}_{YYYY-MM-DD}.json  # Profile output from analyze command
│
├── logs/                           # Rotating logs
│   └── pipeline.log                # Combined console + file logging
│
├── tests/                          # Unit and integration tests
│   ├── __init__.py
│   ├── test_tts.py                 # Tests for ElevenLabs TTS module
│   ├── test_assembler.py           # Tests for FFmpeg video assembly
│   └── [future: more test modules]
│
├── .planning/                      # GSD planning documents
│   └── codebase/                   # Analysis outputs (this directory)
│       ├── ARCHITECTURE.md         # Layers, data flow, abstractions
│       ├── STRUCTURE.md            # This file
│       ├── CONVENTIONS.md          # Code style patterns
│       ├── TESTING.md              # Test framework and patterns
│       └── [future: STACK.md, INTEGRATIONS.md, CONCERNS.md]
│
└── .git/                           # Git repository
```

## Directory Purposes

**analysis/**
- Purpose: Fetch and analyze YouTube channel data to extract style patterns
- Contains: Data API integration, transcript fetching, performance ranking, vision analysis, profile building
- Key files: `fetcher.py` (YouTube entry point), `db.py` (shared DB access), `profiler.py` (Claude batch analysis)

**formats/**
- Purpose: Format-specific pipelines (storytelling vs. tweets)
- Contains: Generators (Claude Haiku), quality scorers (Claude Sonnet), renderers, assemblers
- Key files: `storytelling/generator.py` and `tweets/generator.py` (format-specific content creation)

**formats/storytelling/**
- Purpose: Generate narrative stories narrated over gameplay backgrounds
- Contains: Story generation, quality control, FFmpeg assembly with subtitle support
- Key files: `generator.py` (story text), `assembler.py` (video composition)

**formats/tweets/**
- Purpose: Generate or scrape tweets, render as X dark mode screenshots, add narration
- Contains: Tweet generation, rendering engine (Playwright + HTML), scraper (twscrape), video assembly
- Key files: `renderer.py` (HTML + Playwright), `scraper.py` (real tweet fetch), `assembler.py` (zoom animation)

**pipeline/**
- Purpose: Shared utilities for audio/subtitle/video processing
- Contains: ElevenLabs TTS, ASS subtitle generation, (future) upload handlers
- Key files: `tts.py` (word-level timestamps), `overlay.py` (phrase grouping)

**assets/**
- Purpose: Static media resources
- Contains: Background video clips (gameplay), fonts, music tracks
- Key files: `backgrounds/*.mp4` (must exist; used in _pick_background())

**data/**
- Purpose: Runtime and persistent state storage
- Contains: SQLite databases (pipeline state, twscrape accounts), cookie files
- Key files: `pipeline.db` (central database), `twscrape_accounts.db` (Twitter auth)

**output/**
- Purpose: Temporary and final video artifacts
- Contains: Per-run working directories with intermediate files and final MP4
- Key files: `{timestamp}/final.mp4` (final video output)

**style_profiles/**
- Purpose: Analyzed channel style patterns in JSON format
- Contains: Output from analyze command; used as input to generate command
- Key files: `{ChannelName}_{date}.json` (generated by profiler.py)

**logs/**
- Purpose: Operational logging for debugging and monitoring
- Contains: Pipeline execution logs with timestamps, levels, module names
- Key files: `pipeline.log` (append-only; no rotation configured yet)

**tests/**
- Purpose: Unit and integration test suites
- Contains: Tests for TTS, assembler, and (future) other modules
- Key files: `test_tts.py`, `test_assembler.py`

## Key File Locations

**Entry Points:**
- `main.py`: Command-line orchestrator; parses args, routes to analyze/generate/setup-twitter
- `config.py`: Environment initialization; all other modules import from here

**Configuration:**
- `.env` (not in repo): API keys, cookie paths, proxy credentials
- `config.py`: Loads .env, defines BASE_DIR, DATA_DIR, OUTPUT_DIR, STYLE_PROFILES_DIR, LOGS_DIR

**Core Logic:**

Analysis pipeline:
- `analysis/fetcher.py`: YouTube API integration (channels, playlists, videos)
- `analysis/transcripts.py`: Transcript fetching with auth priority (cookies → proxy → direct)
- `analysis/ranker.py`: Performance scoring (views, likes, comments, temporal patterns)
- `analysis/profiler.py`: Claude Sonnet batch analysis and profile merge

Storytelling pipeline:
- `formats/storytelling/generator.py`: Claude Haiku story generation
- `formats/storytelling/quality.py`: Quality scoring (Claude Sonnet)
- `formats/storytelling/assembler.py`: FFmpeg: background looping + crop + subtitle burn-in

Tweet pipeline:
- `formats/tweets/generator.py`: Claude Haiku tweet generation (single or thread)
- `formats/tweets/quality.py`: Quality scoring
- `formats/tweets/renderer.py`: Playwright + HTML template rendering
- `formats/tweets/scraper.py`: twscrape tweet fetching
- `formats/tweets/assembler.py`: FFmpeg: zoompan filter for animated zoom

Shared utilities:
- `pipeline/tts.py`: ElevenLabs API with word-level timestamps
- `pipeline/overlay.py`: Timestamp grouping into ASS subtitle phrases

**Testing:**
- `tests/test_tts.py`: ElevenLabs module tests
- `tests/test_assembler.py`: FFmpeg assembly tests

**Data Schema:**
- `analysis/db.py`: SQLite schema (channels, videos, style_profiles)

## Naming Conventions

**Files:**

- **Python modules:** snake_case (e.g., `fetcher.py`, `tweet_template.html`)
- **Classes:** PascalCase (none used in current codebase; preference is functions)
- **Functions:** snake_case (e.g., `generate_story()`, `fetch_channel()`)
- **Test files:** `test_*.py` (e.g., `test_tts.py`)

**Directories:**

- **Package dirs:** snake_case (e.g., `formats/storytelling`, `analysis`)
- **Data dirs:** descriptive lowercase (e.g., `assets`, `output`, `data`, `logs`)
- **Feature dirs:** feature name (e.g., `storytelling`, `tweets`)

**Variables & Constants:**

- **Module constants:** UPPER_SNAKE_CASE (e.g., `_MAX_VIDEOS`, `CANVAS_W`, `_ELEVENLABS_BASE`)
- **Private module members:** `_name` prefix (e.g., `_api_call()`, `_parse_json()`)
- **Function params & locals:** snake_case

**Database:**

- **Tables:** plural snake_case (e.g., `channels`, `videos`, `style_profiles`)
- **Columns:** snake_case (e.g., `view_count`, `published_at`, `performance_score`)

## Where to Add New Code

**New Feature (e.g., new content format):**
- Create: `formats/{format_name}/` directory
- Implement: `generator.py`, `quality.py`, assembler module (e.g., `assembler.py`)
- Optional: `renderer.py` (if rendering needed), `scraper.py` (if real content scraping needed)
- Register: Add CLI command in `main.py` (parse args, call cmd_generate with new format)
- Tests: Add `tests/test_{format_name}_*.py` for each module

**New Generation Step (e.g., background music mixing):**
- If format-agnostic: Add to `pipeline/` (e.g., `music_mixer.py`)
- If format-specific: Add to `formats/{format}/` (e.g., `storytelling/music.py`)
- Call from: Assembler module or add new stage in main.py pipeline

**New Analysis Metric (e.g., engagement rate):**
- Add calculation: `analysis/ranker.py` (add to _calculate_* functions)
- Store in DB: Add column to videos table in `analysis/db.py`
- Use in profile: Reference new metric in `analysis/profiler.py` merge prompt

**New External Integration (e.g., upload to YouTube):**
- Create: `pipeline/upload.py` (or `formats/{format}/upload.py`)
- Implement: Public function (e.g., `upload_video(path, title, description)`)
- Call from: Main.py generate command post-assembly
- Handle auth: Load API key from config.py, add error handling with retries

**Utilities and Helpers:**
- Shared across modules: Place in `pipeline/` (e.g., `pipeline/utils.py`)
- Format-specific: Keep in `formats/{format}/` (e.g., `formats/storytelling/utils.py`)
- Database queries: Add to `analysis/db.py` or keep with calling module

**Tests:**
- Unit tests: `tests/test_{module}.py` (test single function/class)
- Integration tests: `tests/test_{flow}.py` (test end-to-end flow, e.g., `test_analyze_flow.py`)
- Fixtures: Place test data in `tests/fixtures/` (create if needed)

## Special Directories

**output/**
- Purpose: Temporary and final artifacts
- Generated: Yes (created per run with unix timestamp subdirectory)
- Committed: No (gitignored; large video files)
- Cleanup: Manual (or add cleanup script)

**data/**
- Purpose: Persistent runtime state
- Generated: Yes (SQLite databases created on first init_db() call)
- Committed: Partially (pipeline.db versioned; cookies/secrets gitignored)
- Note: Contains .gitignored files for auth (x.com_cookies.txt, youtube_cookies.txt)

**style_profiles/**
- Purpose: Generated analysis outputs
- Generated: Yes (created by analyze command)
- Committed: No (gitignored; regenerable from source data)
- Note: JSON files should be readable/diffable if tracked

**logs/**
- Purpose: Audit trail and debugging
- Generated: Yes (created on first logging call)
- Committed: No (gitignored; rotated regularly)
- Note: Configure rotation in config.py if needed (currently append-only)

**.planning/codebase/**
- Purpose: GSD codebase analysis documents
- Generated: Yes (written by /gsd:map-codebase agent)
- Committed: Yes (part of project documentation)
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md

**assets/backgrounds/**
- Purpose: Source video clips for storytelling format
- Generated: No (manually added)
- Committed: No (gitignored; large media files)
- Note: Must contain at least one MP4; referenced in main.py _pick_background()

---

*Structure analysis: 2026-03-11*
