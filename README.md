# auto-shorts

Automated pipeline that generates YouTube Shorts and Instagram Reels from Reddit posts and tweets.

Two formats:
- **Storytelling** — Reddit stories narrated via TTS over background gameplay with word-level subtitle overlays
- **Tweet Screenshots** — Real scraped tweets rendered as X dark mode screenshots with TTS narration

Every command starts with:
```
python main.py --channel SLUG <command>
```

Use `--channel all` to run across all channels.

---

## Quick Start

1. Copy `channels.yaml.example` to `channels.yaml` and fill in your channel config
2. Create `.env` with your API keys (see [Setup](#setup) below)
3. `pip install -r requirements.txt && playwright install chromium`
4. Put gameplay clips in `assets/backgrounds/`
5. Scrape some content: `python main.py --channel my-channel scrape --format reddit --window month`
6. Review it: `python main.py --channel my-channel review`
7. Make a video: `python main.py --channel my-channel generate --format storytelling --from-backlog`

---

## Setup

### .env

```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
YOUTUBE_API_KEY=...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...

# Optional
YOUTUBE_COOKIES_PATH=data/youtube_cookies.txt
TWITTER_COOKIES_PATH=data/x.com_cookies.txt
INSTAGRAM_PUBLIC_BASE_URL=https://your-server.com/videos
```

### channels.yaml

Each channel defines what content to scrape, which voice to use, and where to upload:

```yaml
hypothetical-scenarios:
  name: "Hypothetical Scenarios"
  format: storytelling       # or "tweets"
  voice_id: "YOUR_VOICE_ID"
  subreddits: [hypothetical, AskReddit]
  twitter_accounts: [WhatIfAlt]
  youtube_client_id: ""
  youtube_client_secret: ""
  instagram_access_token: ""
  instagram_user_id: ""
  enabled: true
  hashtags: [shorts, storytime]
  quality:
    min_upvotes: 1000
    min_words: 400
    max_words: 1200
    min_likes: 1000
```

---

## Commands

### `scrape` — Fill the backlog

```
python main.py --channel SLUG scrape --format FORMAT [options]
```

| Option | Description |
|--------|-------------|
| `--format reddit\|tweets` | Content source |
| `--window 24h\|week\|month\|year` | How far back to look (default: 24h) |
| `--review` | Open review prompt immediately after scraping |

### `review` — Approve or reject pending items

```
python main.py --channel SLUG review [--ai]
```

| Option | Description |
|--------|-------------|
| `--ai` | Auto-review with Claude instead of manual prompts |

Keys: `y` approve · `n` reject · `s` skip. After 25 manual approvals, new items are auto-approved.

### `backlog-status` — See what's in the queue

```
python main.py --channel SLUG backlog-status
```

### `generate` — Make videos

```
python main.py --channel SLUG generate --format FORMAT [options]
```

| Option | Description |
|--------|-------------|
| `--format storytelling\|tweets` | Video format |
| `--from-backlog` | Pull from approved backlog items |
| `--scrape` | Scrape fresh content instead of using backlog (tweets only) |
| `--count N` | Number of videos to generate (default: 1) |
| `--pick` | Interactively choose which backlog story to use |
| `--background` | Pick a single background clip for the whole batch |
| `--multi-bg` | Pick multiple clips; outputs one video per clip |
| `--no-audio` | Skip TTS — useful for testing layout |
| `--keep-backlog` | Don't mark items as used after generating |
| `--min-likes N` | Minimum likes filter when scraping tweets |

### `run-cycle` — Full automated posting

Picks top backlog item → generates video → uploads to YouTube + Instagram → marks as used.

```
python main.py --channel SLUG run-cycle [--publish-at TIME]
```

| Option | Description |
|--------|-------------|
| `--publish-at DATETIME` | Upload as private, publish at this UTC time (YouTube only) |

If the backlog is empty, scrapes automatically before generating.

### `upload-history` — Audit recent uploads

```
python main.py --channel SLUG upload-history
```

### `analyze` — Study existing channels

```
python main.py --channel SLUG analyze --channels URL [URL ...] [--visual]
```

Generates a style profile JSON that guides AI content generation.

### `setup-youtube` / `setup-instagram` / `setup-twitter`

```
python main.py --channel SLUG setup-youtube
python main.py --channel SLUG setup-instagram [--token TOKEN]
python main.py --channel SLUG setup-twitter --username X --password X --email X
```

---

## Automate with Cron

```cron
# Scrape daily at 04:00 UTC
0 4 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel my-channel scrape --format reddit >> logs/cron-scrape.log 2>&1

# Post at 09:00 and 21:00 UTC
0 9  * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel my-channel run-cycle >> logs/cron-run.log 2>&1
0 21 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel my-channel run-cycle >> logs/cron-run.log 2>&1
```

Create `logs/` first: `mkdir -p logs`

Set `enabled: false` in `channels.yaml` to pause a channel without touching cron.

---

## Video Settings

Both formats output 1080×1920 MP4 at CRF 18.

| Setting | Value |
|---------|-------|
| Narration speed | 1.3× (atempo) |
| Narration volume | 1.5× boost |
| Storytelling audio | Narration + gameplay audio mixed (gameplay at 0.15 volume) |
| Tweet audio | Narration + background music from `assets/music/` (music at 0.08 volume) |
| Background clip | Random start point, stream-looped to cover full duration |

Put background music files (`.mp3`, `.wav`, `.m4a`) in `assets/music/` for tweet videos.

---

## File Locations

| What | Where |
|------|-------|
| Videos | `output/{timestamp}/final.mp4` |
| Upload metadata | `output/{timestamp}/final.txt` |
| Database | `data/pipeline.db` |
| Background clips | `assets/backgrounds/` |
| Background music | `assets/music/` |
| Channel tokens | `data/channels/{slug}/` |
| Logs | `logs/pipeline.log` |
| Channel config | `channels.yaml` |

---

## Project Structure

```
auto-shorts/
├── main.py                 # CLI entry point
├── config.py               # Loads .env, shared constants
├── channels.yaml           # Per-channel config
├── pipeline/
│   ├── db.py               # SQLite connection + schema
│   ├── tts.py              # ElevenLabs TTS + word timestamps
│   ├── overlay.py          # Word timestamps → ASS subtitle file
│   ├── backlog.py          # Backlog DB operations
│   ├── reddit_scraper.py   # PRAW Reddit scraper
│   ├── quality_filter.py   # Story/tweet quality thresholds
│   └── upload.py           # YouTube/Instagram upload
├── formats/
│   ├── storytelling/
│   │   ├── generator.py    # Adapt Reddit post via Claude API
│   │   └── assembler.py    # FFmpeg: background + audio + subs → MP4
│   └── tweets/
│       ├── renderer.py     # HTML + Playwright → X dark mode screenshot
│       ├── assembler.py    # FFmpeg: image + audio + zoom → MP4
│       ├── scraper.py      # Playwright: fetch tweets from X home feed
│       └── tweet_template.html
├── commands/
│   ├── generate.py
│   ├── review.py
│   ├── run_cycle.py
│   ├── scrape.py
│   └── setup.py
├── assets/
│   ├── backgrounds/        # Gameplay clips
│   ├── fonts/
│   └── music/              # Background music for tweet videos
├── output/                 # Generated videos
└── data/
    └── pipeline.db         # SQLite database
```
