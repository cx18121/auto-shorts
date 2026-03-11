# Technology Stack

**Analysis Date:** 2026-03-11

## Languages

**Primary:**
- Python 3.x - All core pipeline code, CLI, analysis, generation, and video assembly

**Supporting:**
- HTML/CSS/JavaScript - Tweet screenshot template (`formats/tweets/tweet_template.html`)
- SQL - SQLite schema definitions in `analysis/db.py`

## Runtime

**Environment:**
- Python 3.x (implicit from requirements.txt)

**Package Manager:**
- pip (from requirements.txt)
- Lockfile: Not detected

## Frameworks

**Core:**
- Anthropic Claude API (`anthropic` package) - AI-powered content generation and analysis
  - Claude Haiku 4.5 for story and tweet generation (temperature 0.85)
  - Claude Sonnet 4-6 for quality checks and visual analysis (temperature 0.3)

**External APIs:**
- Google API Client (`google-api-python-client`) - YouTube Data API v3 access
- ElevenLabs TTS (`elevenlabs` package implied via direct HTTP usage) - Text-to-speech with word-level timestamps
- Playwright (`playwright`) - Browser automation for X.com tweet scraping and HTML rendering
- twscrape - X.com/Twitter account management and tweet fetching

**Testing:**
- Not detected in requirements

**Build/Dev:**
- FFmpeg (subprocess-based) - Video encoding and composition
- yt-dlp - YouTube video downloading and frame extraction
- youtube-transcript-api - YouTube transcript fetching with proxy/cookie support

## Key Dependencies

**Critical:**
- `anthropic` - Claude API client for all generative AI tasks (story/tweet generation, quality scoring, visual analysis)
- `google-api-python-client` - YouTube Data API v3 for channel/video metadata, statistics, transcripts
- `youtube-transcript-api` - Fetches video transcripts with auth priority: cookies > Webshare proxy > direct
- `playwright` - Headless Chromium for tweet screenshot rendering and X.com scraping
- `twscrape` - X.com bot account handling and tweet scraping (filters replies, retweets, media)
- `requests` - HTTP client for ElevenLabs TTS API, image fetching
- `yt-dlp` - Download YouTube videos for visual analysis
- `Pillow (PIL)` - Image manipulation (canvas composition for tweet screenshots)

**Infrastructure:**
- `python-dotenv` - Load environment variables from `.env` file
- `SQLite3` (built-in) - Single database at `data/pipeline.db` for all pipeline state

## Configuration

**Environment:**
- Loaded from `.env` file via `python-dotenv` in `config.py`
- No config file format (JSON, YAML, TOML) detected

**Required Environment Variables:**
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude models
- `ELEVENLABS_API_KEY` - ElevenLabs API key for TTS
- `ELEVENLABS_VOICE_ID` - Voice identifier for TTS generation
- `YOUTUBE_API_KEY` - YouTube Data API v3 key

**Optional Environment Variables:**
- `YOUTUBE_COOKIES_PATH` - Path to Netscape-format YouTube cookies (higher priority than proxy)
- `WEBSHARE_PROXY_USERNAME` - Username for Webshare proxy (fallback if no cookies)
- `WEBSHARE_PROXY_PASSWORD` - Password for Webshare proxy
- `TWITTER_COOKIES_PATH` - Path to X.com cookies for Playwright (default: `data/x.com_cookies.txt`)

**Build:**
- No build configuration files detected
- Direct execution via Python CLI: `python main.py`

## Database

**SQLite:**
- Location: `data/pipeline.db`
- Schema: `analysis/db.py` defines all tables
- Tables:
  - `channels` - YouTube channel metadata and subscriber count
  - `videos` - Video metadata, statistics, transcripts, performance scores, analysis JSON blobs
  - `style_profiles` - Generated style profiles JSON storage
- WAL mode enabled for concurrent access

## Platform Requirements

**Development:**
- Python 3.x
- FFmpeg installed and in PATH
- Playwright browsers (downloaded automatically on first use)
- Chromium browser for Playwright (auto-installed)

**Runtime Dependencies:**
- ElevenLabs account with API key and voice ID configured
- YouTube Data API v3 credentials (API key)
- Anthropic API account with Claude access
- X.com (Twitter) account with login credentials (for tweet scraping)
- YouTube cookies file OR Webshare proxy account (for transcript fetching behind IP ban protection)

**Production:**
- Any platform supporting Python 3.x and FFmpeg
- No web framework or server component (CLI-only)

## Video & Audio Processing

**Video Assembly:**
- FFmpeg subprocess calls only (no MoviePy)
- Codec: H.264 (libx264)
- Preset: fast
- CRF: 23 (constant rate factor)
- Output: MP4 format
- Resolution: 1080×1920 (vertical shorts format)

**Audio Processing:**
- Format: MP3
- Codec: AAC for final video
- Bitrate: 192k
- Source: ElevenLabs TTS via HTTP API
- Features: Word-level timestamp extraction in JSON

## Rendering & Display

**Tweet Screenshot:**
- HTML template + Playwright rendering (not Pillow/Pillow-based)
- Canvas size: 1080×1920 pixels
- Dark mode colors:
  - Background: `#000` (black)
  - Text: `#E7E9EA` (light gray)
  - Secondary: `#71767B` (medium gray)
  - Borders: `#2F3336` (dark gray)
  - Links: `#1D9BF0` (Twitter blue)
- Font: Inter
- Device scale: 3x for high-quality rendering

## Logging

**Framework:** Python built-in `logging`

**Configuration:**
- Defined in `config.py`
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Output: Console + rotating file (`logs/pipeline.log`)
- Level: INFO

---

*Stack analysis: 2026-03-11*
