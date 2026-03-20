# CLAUDE.md — Automated Shorts Pipeline

## What This Is

Automated pipeline that generates YouTube Shorts and Instagram Reels in two formats:

1. **Storytelling**: Reddit-style stories narrated via TTS over background gameplay with text overlays
2. **Tweet Screenshots**: Real scraped tweets rendered as X dark mode screenshots with TTS narration

The system scrapes a pre-vetted content backlog, assembles videos, and uploads.

## Current State

**Built and working:**

- TTS module (ElevenLabs with word-level timestamps)
- Overlay/subtitle generation (ASS format)
- Video assembly via FFmpeg (storytelling format)
- Tweet screenshot renderer (HTML + Playwright → 1080×1920 PNG matching X dark mode)
- Real tweet scraper via Playwright (cookie-based X.com home feed)
- Tweet video assembler (FFmpeg zoompan)
- Reddit scraper via PRAW
- Content backlog with review workflow
- CLI runner with scrape + review + generate + run-cycle commands
- Upload automation (YouTube + Instagram)

**Building next:**

- Upload automation improvements
- Analytics tracking

## Project Structure

```
shorts-pipeline/
├── CLAUDE.md
├── .env                    # API keys (never commit)
├── main.py                 # CLI entry point
├── config.py               # Loads .env, shared constants
├── requirements.txt
├── pipeline/
│   ├── db.py               # SQLite connection + schema init
│   ├── tts.py              # ElevenLabs TTS + word timestamps
│   ├── overlay.py          # Word timestamps → ASS subtitle file
│   ├── backlog.py          # Backlog DB operations
│   ├── reddit_scraper.py   # PRAW Reddit scraper
│   ├── quality_filter.py   # Story/tweet quality thresholds
│   └── upload.py           # YouTube/Instagram upload
├── formats/
│   ├── storytelling/
│   │   ├── generator.py    # adapt_reddit_post via Claude API
│   │   └── assembler.py    # FFmpeg: background + audio + subs → MP4
│   └── tweets/
│       ├── renderer.py     # HTML + Playwright: renders X dark mode screenshot
│       ├── assembler.py    # FFmpeg: image + audio + zoom → MP4
│       ├── scraper.py      # Playwright: fetch real tweets from X home feed
│       └── tweet_template.html  # X dark mode HTML template (Inter font, real SVG icons)
├── commands/
│   ├── generate.py         # Video generation command
│   ├── review.py           # Backlog review command
│   ├── run_cycle.py        # Full automated posting cycle
│   ├── scrape.py           # Scrape + backlog-status + upload-history commands
│   └── setup.py            # OAuth setup commands
├── assets/
│   ├── backgrounds/        # Background gameplay clips
│   ├── fonts/              # Fonts for tweet renderer
│   └── music/              # Royalty-free music (later)
├── output/                 # Generated videos
└── data/
    ├── pipeline.db         # SQLite
    └── youtube_cookies.txt   # Netscape cookies for transcript fetching (gitignored)
```

## Environment Variables (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
YOUTUBE_API_KEY=...

# Path to Netscape-format X.com cookies for Playwright tweet scraping
TWITTER_COOKIES_PATH=data/x.com_cookies.txt

# Reddit API credentials
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=auto-shorts/1.0
```

## CLI Commands

```bash
# Scrape content into the backlog
python main.py --channel hypothetical-scenarios scrape --format reddit --window 24h
python main.py --channel finance-hustle scrape --format tweets --window 24h

# Review pending backlog items
python main.py --channel hypothetical-scenarios review
python main.py --channel hypothetical-scenarios review --ai   # Claude auto-review

# Generate videos from backlog
python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog --count 3
python main.py --channel finance-hustle generate --format tweets --from-backlog --count 3

# Background selection (storytelling only)
python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog --background
# ^ interactive: pick ONE clip from numbered list; all videos in the batch use it

python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog --multi-bg
# ^ interactive: pick MULTIPLE clips (e.g. "1,3"); TTS+captions generated once,
#   one output video per clip (final_bg1.mp4, final_bg2.mp4, ...) in the same run dir

# Generate tweet videos from real scraped tweets (bypasses backlog)
python main.py --channel finance-hustle generate --format tweets --scrape --count 3
python main.py --channel finance-hustle generate --format tweets --scrape --count 3 --min-likes 1000

# Full automated cycle (generate + upload + mark-used)
python main.py --channel hypothetical-scenarios run-cycle
python main.py --channel hypothetical-scenarios run-cycle --publish-at 2026-03-20T09:00:00Z
```

## Key Technical Rules

**FFmpeg**: Always use subprocess. No MoviePy for now.

**Anthropic API**: Haiku for generation (temp 0.85). Sonnet for quality checks and analysis (temp 0.3). Always request JSON output with explicit schema in system prompt. Always set max_tokens.

**ElevenLabs**: Always request word-level timestamps. Store both audio AND timestamp JSON.

**SQLite**: Single database at `data/pipeline.db`. All pipeline state lives here. Use `pipeline.db.get_connection()` for production connections.

**Tweet Renderer**: HTML template + Playwright (not Pillow). Renders at 600px viewport × 3x device scale → composited onto 1080×1920 black canvas. X "Lights Out" dark mode: `#000` bg, `#E7E9EA` text, `#71767B` secondary, `#2F3336` borders, `#1D9BF0` blue. Profile images loaded via `<img src="URL">` in HTML — Playwright fetches them. `_fmt()` always shows one decimal for K values (e.g. "572.2K").

**Tweet Scraper**: Playwright + cookie-based auth scraping X.com home feed. Filters out replies, retweets, and tweets with media. Text-only tweets only. Cookies at `data/x.com_cookies.txt`.

**Error handling**: Every external API call gets try/except with 3 retries and exponential backoff. Failed items log and continue — never block the pipeline.

**Code style**: Type hints on all functions. Docstrings on public functions. Prefer functions over classes. Every module should be testable standalone. Log every step — silent pipelines are undebuggable.

## What NOT to Build Yet

- Scheduling system
- Web dashboard
- Background music mixing
- Advanced overlay animations

## Cron Scheduling

Use `crontab -e` to add per-channel scheduling. The pipeline runs via `python main.py --channel SLUG run-cycle`.

**Requirements before scheduling:**
- Each channel must have `enabled: true` in channels.yaml.
- YouTube token must exist at `data/channels/SLUG/youtube_token.json` (run `setup-youtube` once per channel).
- Instagram token must exist at `data/channels/SLUG/instagram_token.json` (run `setup-instagram` once per channel).
- `INSTAGRAM_PUBLIC_BASE_URL` must be set in `.env` to a publicly accessible base URL where video files are served.
- The venv must be activated or the absolute Python path used (e.g. `/path/to/.venv/bin/python3`).
- Logs go to `logs/pipeline.log` (gitignored). Cron must `cd` to the project root first.

**Example crontab** (2x/day posting at 09:00 and 21:00, daily scraping at 04:00):

```cron
# Daily scraping at 04:00 UTC — fills the backlog for all channels
0 4 * * * cd /path/to/auto-shorts && /path/to/.venv/bin/python3 main.py --channel hypothetical-scenarios scrape --format reddit --window 24h >> logs/cron-scrape.log 2>&1
0 4 * * * cd /path/to/auto-shorts && /path/to/.venv/bin/python3 main.py --channel finance-hustle scrape --format tweets --window 24h >> logs/cron-scrape.log 2>&1

# Morning post at 09:00 UTC — uploads one video per channel
0 9 * * * cd /path/to/auto-shorts && /path/to/.venv/bin/python3 main.py --channel hypothetical-scenarios run-cycle >> logs/cron-run.log 2>&1
0 9 * * * cd /path/to/auto-shorts && /path/to/.venv/bin/python3 main.py --channel finance-hustle run-cycle >> logs/cron-run.log 2>&1

# Evening post at 21:00 UTC — uploads a second video per channel
0 21 * * * cd /path/to/auto-shorts && /path/to/.venv/bin/python3 main.py --channel hypothetical-scenarios run-cycle >> logs/cron-run.log 2>&1
0 21 * * * cd /path/to/auto-shorts && /path/to/.venv/bin/python3 main.py --channel finance-hustle run-cycle >> logs/cron-run.log 2>&1
```

**Notes:**
- The `enabled` field in channels.yaml gates each run-cycle call — set `enabled: false` to pause a channel without removing cron lines.
- The `logs/` directory is gitignored; create it manually if it does not exist.
- Run `python main.py --channel SLUG upload-history` to audit recent uploads and spot failures.
