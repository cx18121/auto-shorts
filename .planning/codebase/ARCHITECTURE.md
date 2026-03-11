# Architecture

**Analysis Date:** 2026-03-11

## Pattern Overview

**Overall:** Pipeline-based content generation and analysis system with format-specific branches (storytelling and tweets)

**Key Characteristics:**
- Layered architecture: analysis → generation → assembly
- Modular format handlers (storytelling and tweets are separate pipelines with shared utilities)
- CLI-driven orchestration with command-based routing
- Database-backed state (SQLite for channel data, videos, profiles, and analysis results)
- External API integration (YouTube, ElevenLabs, Claude, Playwright, twscrape)
- Quality-gate pattern with retry logic for generated content

## Layers

**Configuration Layer:**
- Purpose: Load environment variables, initialize logging, define shared paths
- Location: `config.py`
- Contains: API keys, directory paths, logging setup
- Depends on: dotenv (for .env loading)
- Used by: All modules

**Data Persistence Layer:**
- Purpose: SQLite schema definition and connection management
- Location: `analysis/db.py`
- Contains: Database initialization, connection factory with Row factory enabled, schema for channels/videos/style_profiles
- Depends on: sqlite3
- Used by: fetcher, profiler, transcripts, ranker modules

**Analysis Layer:**
- Purpose: Fetch YouTube channel data, analyze transcripts, rank videos, profile styles
- Location: `analysis/`
- Contains: fetcher (YouTube API), transcripts (transcript fetching with proxy/cookie auth), ranker (performance scoring), profiler (Claude-powered batch analysis)
- Depends on: Google API client, youtube-transcript-api, requests, anthropic
- Used by: CLI (analyze command)

**Generation Layer:**
- Purpose: Create content (stories or tweets) guided by style profiles via Claude Haiku
- Location: `formats/{storytelling,tweets}/generator.py`
- Contains: Story generation (storytelling), tweet generation with optional threading (tweets)
- Depends on: anthropic (Claude Haiku, temp 0.85), profile JSON
- Used by: CLI (generate command)

**Quality Gate Layer:**
- Purpose: Score generated content with Claude Sonnet (temp 0.3), reject and retry until passing
- Location: `formats/{storytelling,tweets}/quality.py`
- Contains: Quality scoring against profile constraints
- Depends on: anthropic (Claude Sonnet)
- Used by: main.py (_generate_with_quality wrapper)

**Rendering/Formatting Layer:**
- Purpose: Convert abstract content into media-ready formats
- Location: `formats/{storytelling,tweets}/renderer.py`, `pipeline/`
- Contains:
  - TTS: ElevenLabs API → MP3 + word-level timestamps JSON
  - Overlay: Word timestamps → ASS subtitle file
  - Renderer (tweets): HTML template + Playwright → PNG screenshot
  - Scraper (tweets): twscrape → real tweet fetch
- Depends on: requests, Playwright, PIL, twscrape, ElevenLabs API
- Used by: Assembly layer

**Assembly Layer:**
- Purpose: Combine rendered assets with FFmpeg into final video
- Location: `formats/{storytelling,tweets}/assembler.py`
- Contains:
  - Storytelling: background + narration + subtitles → MP4 (looped, cropped, trimmed)
  - Tweets: tweet image + narration + zoom animation → MP4
- Depends on: subprocess (FFmpeg), Path utilities
- Used by: CLI (generate command via _run_*_pipeline)

**Orchestration Layer:**
- Purpose: Command routing, pipeline sequencing, error handling
- Location: `main.py`
- Contains: CLI (argparse), three command handlers (analyze, generate, setup-twitter)
- Depends on: argparse, logging, all lower layers
- Used by: User entry point

## Data Flow

**Analyze Flow:**

1. User runs `python main.py analyze --channels URL [--visual]`
2. `cmd_analyze()` in main.py sequences four steps:
   - `fetch_channel()` → YouTube API → resolve channel, fetch Shorts metadata → store in DB (channels table, videos table)
   - `fetch_transcripts()` → youtube-transcript-api (with cookie/proxy auth) → store transcript text in videos.transcript
   - `rank_channel()` → calculate performance scores, identify top performers, store derived metrics
   - (optional) `analyse_visuals()` → Claude vision → store visual_analysis and thumbnail_analysis JSON
3. `build_profile()` → Claude Sonnet (batch analysis at _BATCH_SIZE=7 videos, then merge) → JSON style profile
4. Profile saved to `style_profiles/` and stored in DB (style_profiles table)

**Generate Flow (Storytelling):**

1. User runs `python main.py generate --format storytelling --profile PATH --count N`
2. For each count iteration:
   - `_generate_with_quality()` loop (up to 3 retries):
     - `generate_story(profile)` → Claude Haiku (temp 0.85) → story JSON (title, hook_line, story_text, overlay_phrases, duration)
     - `check_quality(story, profile)` → Claude Sonnet (temp 0.3) → quality dict with overall score
     - If score < 7.0, reject and retry; else accept
   - `_run_storytelling_pipeline()`:
     - `generate_tts(story_text)` → ElevenLabs API → narration.mp3 + timestamps.json
     - `generate_ass(timestamps.json)` → word-level timestamps grouped into phrases → subtitles.ass
     - `assemble_video(background, audio, subs)` → FFmpeg → final.mp4
3. Output paths printed to user

**Generate Flow (Tweets):**

Mode A - AI Generated:
1. User runs `python main.py generate --format tweets --profile PATH --count N [--thread]`
2. For each count (or thread) iteration:
   - `_generate_with_quality()` loop:
     - `generate_tweet(profile)` or `generate_thread(count, profile)` → Claude Haiku → tweet JSON (or list of tweets)
     - `check_quality(tweet, profile)` → Claude Sonnet → quality scoring
   - `_run_tweet_pipeline()`:
     - `render_tweet(tweet)` → HTML template + Playwright → tweet.png (1080×1920)
     - `generate_tts(tweet_text)` → ElevenLabs → narration.mp3 + timestamps.json
     - `assemble_tweet_video(image, audio)` → FFmpeg (zoompan filter) → final.mp4

Mode B - Real Tweet Scraping:
1. User runs `python main.py generate --format tweets --scrape --count N [--min-likes MIN]`
2. `_scrape_tweets(count, min_likes)`:
   - `scrape_top_tweets(n=count*3, min_likes=min_likes)` → twscrape → list of real tweets (filtered: text-only, no replies/retweets)
   - For each scraped tweet, same pipeline as Mode A (render → TTS → assemble)

**Twitter Setup Flow:**

1. User runs `python main.py setup-twitter --username U --password P --email E [--email-password EP] [--cookies C]`
2. `setup_account()` → twscrape account storage in `data/twscrape_accounts.db`

**State Management:**

- **Transient state:** Working directories created per run (based on unix timestamp) in `output/`
- **Persistent state:** SQLite database at `data/pipeline.db` stores:
  - channels: metadata for analyzed channels
  - videos: Shorts metadata, transcripts, performance scores, analysis JSON
  - style_profiles: Generated profiles and their settings
- **Style profiles:** JSON files in `style_profiles/` with schema: content_style, visual_style, title_patterns, thumbnail_patterns, posting_strategy, generation_prompt_guidance
- **Logs:** Pipeline logs written to `logs/pipeline.log` (rotating via logging.FileHandler)

## Key Abstractions

**Style Profile:**
- Purpose: Encodes channel characteristics learned from analysis to guide generation
- Examples: `style_profiles/ChannelName_2026-03-11.json`
- Pattern: JSON object with nested sections for content rules, visual preferences, posting patterns, and direct prompt guidance for generators

**Tweet (dict abstraction):**
- Purpose: Unified representation for both AI-generated and real tweets
- Fields: `display_name`, `username`, `tweet_text`/`text`, `likes`, `retweets`, `verified`, `profile_image_url` (optional)
- Used by: renderer, assembler, quality checker

**Story (dict abstraction):**
- Purpose: Unified representation for generated stories
- Fields: `title`, `hook_line`, `story_text`, `overlay_phrases`, `estimated_duration_seconds`
- Used by: quality checker, assembler

**TTS Output (dict):**
- Purpose: Encapsulates TTS generation results
- Fields: `audio_path` (MP3), `timestamps_path` (JSON with word-level timing), `duration_seconds` (float)
- Pattern: Always returned together; consumer knows to expect all three

**Video Record (SQLite Row):**
- Purpose: Central repository for metadata + computed analysis
- Key derived fields: `performance_score`, `is_top_performer`, `visual_analysis`, `thumbnail_analysis`
- Pattern: Fetched as Row objects with dict-like access; scores are reals, binary flags are INTEGERs

## Entry Points

**CLI Entry Point:**
- Location: `main.py:main()`
- Triggers: User command line invocation `python main.py [command]`
- Responsibilities: Argument parsing, command routing to cmd_analyze/cmd_generate/cmd_setup_twitter

**Analyze Pipeline:**
- Location: `main.py:cmd_analyze()`
- Triggers: `analyze` command
- Responsibilities: Sequence fetcher → transcripts → ranker → (optional) visual → profiler; log progress

**Generate Storytelling Pipeline:**
- Location: `main.py:_generate_storytelling()`
- Triggers: `generate` command with `--format storytelling`
- Responsibilities: Loop generation, quality check, TTS, overlay, assembly for N stories

**Generate Tweet Pipeline (AI):**
- Location: `main.py:_generate_tweets()` (no scrape flag)
- Triggers: `generate` command with `--format tweets` and `--profile`
- Responsibilities: Generate/score tweets, render, TTS, assemble

**Generate Tweet Pipeline (Scrape):**
- Location: `main.py:_scrape_tweets()`
- Triggers: `generate` command with `--format tweets --scrape`
- Responsibilities: Fetch real tweets, render, TTS, assemble

**Setup Twitter:**
- Location: `main.py:cmd_setup_twitter()`
- Triggers: `setup-twitter` command
- Responsibilities: Persist Twitter account credentials to twscrape DB

## Error Handling

**Strategy:** Try-except with 3 retries and exponential backoff for external API calls; failed items log with context and continue (never block pipeline)

**Patterns:**

- YouTube API (`_api_call` in fetcher.py): Catches HttpError for rate limits (403, 429) and other exceptions; exponential backoff 2^attempt seconds; raises RuntimeError after 3 attempts
- ElevenLabs (`_call_with_retry` in tts.py): Catches requests.RequestException; logs warnings; re-raises after 3 attempts
- Claude calls (profiler.py, generators, quality modules): Generic Exception catch; log warning; sleep 2^attempt seconds; raise after 3 attempts
- Transcripts (transcripts.py): Per-video try-except; logs but continues to next video; returns count of successful fetches
- FFmpeg calls (assemblers): Subprocess returns non-zero; raises CalledProcessError; caught in main.py _run_*_pipeline; logs and returns None (item skipped)

**Quality gate:** Generate → Quality check → If fail, retry up to _MAX_QUALITY_RETRIES (3); if all fail, log error and skip item

## Cross-Cutting Concerns

**Logging:** Every module logs via `logging.getLogger(__name__)`; configured in config.py with console + file handlers; patterns include:
- INFO for major steps: "ANALYZING CHANNEL", "[1/4] Fetching", "Generated story"
- WARNING for retries and non-fatal issues: "rate limit", "rejected"
- ERROR for failures: "Pipeline failed", "No channel found"

**Validation:**
- Argument validation in main.py (--profile required unless --scrape; --count must be int)
- JSON validation in generators (_parse_json with markdown fence stripping; _validate checks required keys)
- Database checks (file existence in assemblers before FFmpeg)

**Authentication:**
- API keys loaded from .env via config.py (ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, YOUTUBE_API_KEY)
- YouTube transcripts: Priority order cookies (http_client with MozillaCookieJar) → Webshare proxy → direct (no auth)
- Twitter account: twscrape handles login; credentials loaded from DB

**Rate limiting:**
- YouTube playlist fetch: sleeps between pages via logging info
- Transcript fetch: explicit 3-second sleep between videos (_MAX_TRANSCRIPTS cap at 50 per run)
- Claude calls: exponential backoff on failure
- ElevenLabs: exponential backoff on failure

---

*Architecture analysis: 2026-03-11*
