# External Integrations

**Analysis Date:** 2026-03-11

## APIs & External Services

**Anthropic Claude API:**
- Service: LLM-based content generation and analysis
- What it's used for:
  - Story generation via `formats/storytelling/generator.py` (Claude Haiku 4.5)
  - Tweet generation via `formats/tweets/generator.py` (Claude Haiku 4.5)
  - Story quality checking via `formats/storytelling/quality.py` (Claude Sonnet 4-6)
  - Tweet quality checking via `formats/tweets/quality.py` (Claude Sonnet 4-6)
  - Visual frame analysis via `analysis/visual.py` (Claude Sonnet 4-6)
  - Thumbnail analysis via `analysis/visual.py` (Claude Sonnet 4-6)
- SDK/Client: `anthropic` Python package
- Auth: API key via `ANTHROPIC_API_KEY` environment variable
- Endpoint: `https://api.anthropic.com`
- Models:
  - `claude-haiku-4-5-20251001` for generation (temp 0.85, lower cost/faster)
  - `claude-sonnet-4-6` for analysis (temp 0.3, higher quality)
- Request format: JSON with explicit schema in system prompt
- Error handling: 3 retries with exponential backoff (2^n seconds)

**YouTube Data API v3:**
- Service: YouTube channel and video metadata
- What it's used for:
  - Fetch channel metadata (name, subscriber count) via `analysis/fetcher.py`
  - List Shorts videos from channel uploads playlist
  - Fetch video details (title, description, view/like/comment counts, duration, captions)
  - Retrieve video transcripts (uses `youtube-transcript-api` separately)
- SDK/Client: `google-api-python-client`
- Auth: API key only (no OAuth) via `YOUTUBE_API_KEY` environment variable
- Endpoint: `https://www.googleapis.com/youtube/v3`
- Rate limiting:
  - Hard cap: 50 videos per fetch run to avoid IP bans during transcript phase
  - Pagination handled via `pageToken`
  - Exponential backoff on 403/429 errors
- Error handling: 3 retries with exponential backoff
- Implementation: `analysis/fetcher.py`

**YouTube Transcript API:**
- Service: Fetch video transcripts for analysis
- What it's used for: Extract transcripts from Shorts to guide content analysis
- Client: `youtube-transcript-api` Python package
- Auth: Multiple priority strategies:
  1. **Cookies (highest priority):** Netscape-format cookies from browser
     - Path: `YOUTUBE_COOKIES_PATH` environment variable
     - Loaded into `requests.Session` with `MozillaCookieJar`
     - Bypasses IP bans
  2. **Proxy (fallback):** Webshare proxy service
     - Username: `WEBSHARE_PROXY_USERNAME`
     - Password: `WEBSHARE_PROXY_PASSWORD`
     - Uses `WebshareProxyConfig`
  3. **Direct (last resort):** Unauthenticated requests
- Rate limiting: 3-second delay between requests, max 50 videos per run
- Error handling: 3 retries for non-terminal errors (SSL drops), skip terminal errors (no transcript, unavailable)
- Implementation: `analysis/transcripts.py`

**ElevenLabs Text-to-Speech:**
- Service: High-quality voice synthesis with word-level timestamps
- What it's used for: Convert story/tweet text to narration audio
- API: REST HTTP endpoint
- Endpoint: `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps`
- Auth: API key via `XI-API-KEY` header
- Configuration:
  - `ELEVENLABS_API_KEY` environment variable
  - `ELEVENLABS_VOICE_ID` environment variable
- Request format:
  - Model: `eleven_multilingual_v2`
  - Stability: 0.5
  - Similarity boost: 0.75
  - Always requests word-level timestamps
- Response: Base64-encoded MP3 + character/word alignment data
- Error handling: 3 retries with exponential backoff (2^n seconds)
- Output files per call (stored in working directory):
  - `narration.mp3` - Audio file
  - `timestamps.json` - Word-level timing data
- Implementation: `pipeline/tts.py`

**X.com / Twitter (Playwright Scraping):**
- Service: Fetch real viral tweets for content generation
- What it's used for: Scrape high-engagement tweets from curated accounts and home feed
- Client: Playwright (headless Chromium automation)
- Auth: Browser cookies (Netscape format)
  - Path: `data/x.com_cookies.txt` (loaded via `TWITTER_COOKIES_PATH`)
  - Must be manually exported from browser using "Get cookies.txt LOCALLY" Chrome extension
- Scraping sources:
  - Curated account profiles: `VIRAL_ACCOUNTS` list in `formats/tweets/scraper.py`
  - Authenticated home feed (algorithmically diverse)
- Filters: Text-only tweets (no media, no replies, no retweets)
- Data extraction:
  - Tweet ID, text, author (@handle), display name
  - Engagement metrics (likes, retweets, views)
  - Profile image URL, verified status, created_at timestamp
  - Engagement score: `likes + retweets * 3`
- Rate limiting: 1.5s pause between page loads, 2.5s between account profiles
- Error handling: Non-blocking - failed accounts log and continue
- Implementation: `formats/tweets/scraper.py` (async with `asyncio`)

## Data Storage

**Databases:**
- **SQLite3** (primary)
  - Location: `data/pipeline.db`
  - Connection: Standard `sqlite3` module with WAL mode enabled
  - Schema: `analysis/db.py`
  - Tables: `channels`, `videos`, `style_profiles`
  - Used for: All pipeline state (fetched videos, transcripts, performance scores, analysis blobs)

**File Storage:**
- Local filesystem only (no S3 or cloud storage)
- Directories:
  - `output/` - Generated video MP4 files
  - `data/` - SQLite database, cookies, accounts database
  - `style_profiles/` - Generated JSON style profiles
  - `assets/` - Background clips, fonts, music (not populated in current stack)
  - `logs/` - Pipeline logs

**Twitter/X Cookies:**
- Storage: `data/x.com_cookies.txt` (Netscape format)
- Not committed to git (`.gitignore`)
- Manually exported from browser

**YouTube Cookies:**
- Storage: Path specified by `YOUTUBE_COOKIES_PATH` (default: `data/youtube_cookies.txt`)
- Not committed to git (`.gitignore`)
- Manually exported from browser

**twscrape Account Database:**
- Storage: `data/twscrape_accounts.db`
- Purpose: Store X.com bot account credentials (deprecated in favor of Playwright cookies)
- Implementation: `formats/tweets/scraper.py`

## Caching

**Not explicitly implemented** - All API responses are processed and stored to SQLite immediately.

## Authentication & Identity

**Auth Methods:**
- API Key authentication (Anthropic, YouTube, ElevenLabs)
- Browser cookie authentication (YouTube transcripts, X.com scraping)
- Proxy credentials (Webshare for YouTube transcript fallback)

**No user authentication** - This is a CLI-only pipeline with no user management.

## Monitoring & Observability

**Error Tracking:** Not detected - No Sentry, Rollbar, or similar service

**Logs:**
- Destination: Console + rotating file at `logs/pipeline.log`
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Level: INFO
- Every external API call is logged with attempt number and backoff timing
- Pipeline steps are logged with progress indicators (e.g., "[1/4] Fetching...")

**Metrics:**
- Video count per channel
- Transcript fetch success rate
- Performance scores stored in `videos.performance_score`
- Quality check pass/fail ratios (logged during generation)

## CI/CD & Deployment

**Hosting:** Not applicable - CLI tool, no web service

**CI Pipeline:** Not detected

**Deployment:** Manual execution via `python main.py [command]`

## Environment Configuration

**Required env vars:**
```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
YOUTUBE_API_KEY=...
```

**Optional env vars:**
```
YOUTUBE_COOKIES_PATH=data/youtube_cookies.txt
WEBSHARE_PROXY_USERNAME=...
WEBSHARE_PROXY_PASSWORD=...
TWITTER_COOKIES_PATH=data/x.com_cookies.txt
```

**Secrets location:**
- `.env` file (not committed, loaded by `python-dotenv`)
- Cookie files in `data/` (not committed, manually exported from browser)
- twscrape account DB in `data/` (not committed)

## Webhooks & Callbacks

**Incoming:** None detected

**Outgoing:** None detected - No upload automation yet (future feature)

## Video/Image Downloads

**YouTube Video Downloads:**
- Tool: `yt-dlp`
- Purpose: Download videos for visual frame analysis
- Implementation: `analysis/visual.py`
- Temporary storage: System temp directory
- Cleanup: Automatic deletion after processing

**Frame Extraction:**
- Tool: FFmpeg subprocess
- Purpose: Extract evenly-spaced frames from videos
- Count: 9 frames per video
- Implementation: `analysis/visual.py`

**Image Downloads in Rendering:**
- Tweet profile images: Fetched by Playwright from X.com CDN directly in HTML
- YouTube thumbnails: Fetched via `urllib.request` for analysis
- Implementation: `formats/tweets/renderer.py`, `analysis/visual.py`

---

*Integration audit: 2026-03-11*
