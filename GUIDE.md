# Auto-Shorts Pipeline — User Guide

## Overview

This pipeline generates YouTube Shorts and Instagram Reels automatically. It supports two video formats:

- **Storytelling** — Reddit posts narrated via TTS over gameplay footage with a Reddit post screenshot and subtitles
- **Tweets** — Real or AI-generated tweets rendered as X dark mode screenshots with TTS narration and zoom animation

Every command requires `--channel SLUG` (or `--channel all` to run across all channels).

```
python main.py --channel SLUG <command> [options]
```

---

## Setup

### 1. Environment Variables

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
YOUTUBE_API_KEY=...

# Reddit scraping (create a script app at https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...

# Optional: YouTube transcript cookies (bypasses IP bans)
YOUTUBE_COOKIES_PATH=data/youtube_cookies.txt

# Optional: proxy fallback for transcripts
WEBSHARE_PROXY_USERNAME=...
WEBSHARE_PROXY_PASSWORD=...

# Optional: X.com cookies for tweet scraping
TWITTER_COOKIES_PATH=data/x.com_cookies.txt

# Required for Instagram uploads
INSTAGRAM_PUBLIC_BASE_URL=https://your-public-server.com/videos
```

### 2. Channel Configuration

Copy the example and edit it:

```bash
cp channels.yaml.example channels.yaml
```

Each channel entry looks like this:

```yaml
hypothetical-scenarios:
  name: "Hypothetical Scenarios"
  format: storytelling          # or "tweets"
  voice_id: "YOUR_ELEVENLABS_VOICE_ID"
  subreddits:
    - hypothetical
    - AskReddit
    - WouldYouRather
  twitter_accounts:
    - WhatIfAlt
    - HypotheticalQ
  youtube_client_id: ""         # from Google Cloud Console
  youtube_client_secret: ""     # from Google Cloud Console
  instagram_access_token: ""
  enabled: true                 # set false to pause without removing cron
  hashtags:
    - shorts
    - storytime
  instagram_user_id: ""         # filled by setup-instagram
  quality:
    min_upvotes: 1000
    min_words: 400
    max_words: 1200
    min_likes: 1000
  style_profile: ""             # optional path to a style profile JSON
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Add Background Gameplay

Place `.mp4` clips in `assets/backgrounds/`. The pipeline picks the first one it finds.

---

## Commands

### `analyze` — Analyze YouTube Channels

Study existing YouTube channels to generate a style profile that guides AI content generation.

```bash
# Basic analysis
python main.py --channel my-channel analyze --channels "https://youtube.com/@SomeChannel"

# Analyze multiple channels at once
python main.py --channel my-channel analyze --channels "URL1" "URL2" "URL3"

# Include visual/thumbnail analysis (slower, uses Claude vision)
python main.py --channel my-channel analyze --channels "URL1" --visual

# Limit number of videos fetched
python main.py --channel my-channel analyze --channels "URL1" --max-videos 25
```

**What it does:** Fetches videos, downloads transcripts, ranks performance, optionally analyzes thumbnails/frames, and builds a style profile JSON saved to `style_profiles/`.

---

### `scrape` — Fill the Content Backlog

Scrape Reddit posts or tweets into the backlog database for later use.

```bash
# Scrape Reddit posts from the channel's configured subreddits (last 24 hours)
python main.py --channel hypothetical-scenarios scrape --format reddit

# Scrape tweets from the channel's configured Twitter accounts
python main.py --channel finance-hustle scrape --format tweets

# Bootstrap: scrape the last month of content
python main.py --channel hypothetical-scenarios scrape --format reddit --window month
```

**What it does:** Pulls posts/tweets, filters by the channel's quality thresholds (min_upvotes, min_words, etc.), and inserts them into the SQLite backlog with status `pending`. Duplicates are skipped.

---

### `review` — Approve or Reject Backlog Items

Interactively review pending items one at a time.

```bash
python main.py --channel hypothetical-scenarios review
```

For each item you'll see the content and can type:
- `y` — approve (moves to `approved` status, eligible for video generation)
- `n` — reject (permanently excluded)
- `s` — skip (stays `pending` for later)

**Probation system:** The first 25 manual reviews per channel must be done by hand. After that, new scraped items are auto-approved.

---

### `backlog-status` — Check Backlog Counts

See how many items are pending, approved, used, and rejected.

```bash
python main.py --channel hypothetical-scenarios backlog-status

# Check all channels at once
python main.py --channel all backlog-status
```

---

### `generate` — Produce Videos

#### Storytelling Videos from Backlog (most common)

```bash
# Generate 1 video from the next approved backlog story
python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog

# Generate 3 videos
python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog --count 3

# Interactively pick which approved story to use
python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog --pick

# Test video layout without spending TTS credits
python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog --no-audio

# Don't mark backlog items as used (for testing)
python main.py --channel hypothetical-scenarios generate --format storytelling --from-backlog --keep-backlog
```

#### Storytelling Videos from Style Profile (AI-generated stories)

```bash
python main.py --channel my-channel generate --format storytelling --profile style_profiles/some_profile.json --count 3
```

#### Tweet Videos (AI-generated from style profile)

```bash
python main.py --channel finance-hustle generate --format tweets --profile style_profiles/some_profile.json

# Thread-style tweets
python main.py --channel finance-hustle generate --format tweets --profile style_profiles/some_profile.json --thread
```

#### Tweet Videos from Real Scraped Tweets

```bash
python main.py --channel finance-hustle generate --format tweets --scrape --count 3
python main.py --channel finance-hustle generate --format tweets --scrape --min-likes 1000
```

**Pipeline steps (storytelling):**
1. TTS via ElevenLabs (with word-level timestamps)
2. Reddit post screenshot rendered via Playwright
3. ASS subtitle file generated from timestamps
4. FFmpeg assembles: gameplay background + post image + audio + subtitles

---

### `setup-twitter` — Add a Twitter Account for Scraping

One-time setup to add X/Twitter credentials for tweet scraping via twscrape.

```bash
python main.py --channel finance-hustle setup-twitter \
  --username myaccount \
  --password mypassword \
  --email myemail@example.com

# With browser cookies (skips login)
python main.py --channel finance-hustle setup-twitter \
  --username myaccount \
  --password mypassword \
  --email myemail@example.com \
  --cookies "ct0=abc123; auth_token=xyz789"
```

---

### `setup-youtube` — YouTube OAuth Setup

Authorize the pipeline to upload videos to YouTube for a specific channel.

```bash
python main.py --channel hypothetical-scenarios setup-youtube
```

**Prerequisites:**
- Create an OAuth 2.0 Client ID (Desktop app) in Google Cloud Console
- Add `youtube_client_id` and `youtube_client_secret` to `channels.yaml`

Opens a browser for Google OAuth. Token is saved to `data/channels/{slug}/youtube_token.json`.

---

### `setup-instagram` — Instagram Token Setup

Exchange a short-lived Instagram token for a long-lived one.

```bash
# Interactive (prompts for token)
python main.py --channel hypothetical-scenarios setup-instagram

# Pass token directly
python main.py --channel hypothetical-scenarios setup-instagram --token "YOUR_SHORT_LIVED_TOKEN"
```

**Prerequisites:**
- Instagram Business or Creator account connected to a Facebook Page
- Generate a short-lived token at https://developers.facebook.com/tools/explorer/
- Grant `instagram_content_publish` and `instagram_basic` permissions

Token saved to `data/channels/{slug}/instagram_token.json`.

---

### `run-cycle` — Full Automated Posting Cycle

The main automation command. Pulls from backlog, generates a video, uploads to YouTube + Instagram, and marks the item as used.

```bash
python main.py --channel hypothetical-scenarios run-cycle
```

**What it does:**
1. Checks if channel is enabled
2. Picks the top approved item from the backlog
3. If backlog is empty, runs a scrape fallback automatically
4. Generates the video (TTS + render + assemble)
5. Generates upload metadata (title + hashtags) via Claude Haiku
6. Uploads to YouTube (if token exists)
7. Uploads to Instagram (if token + user_id exist)
8. Marks the backlog item as `used`
9. Logs the upload record

---

### `upload-history` — View Upload Log

```bash
python main.py --channel hypothetical-scenarios upload-history
python main.py --channel hypothetical-scenarios upload-history --limit 50
```

---

## Cron Scheduling

Automate everything with cron. Example schedule:

```cron
# Daily scraping at 04:00 UTC
0 4 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel hypothetical-scenarios scrape --format reddit --window 24h >> logs/cron-scrape.log 2>&1

# Post at 09:00 and 21:00 UTC
0 9 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel hypothetical-scenarios run-cycle >> logs/cron-run.log 2>&1
0 21 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel hypothetical-scenarios run-cycle >> logs/cron-run.log 2>&1
```

Create the logs directory first: `mkdir -p logs`

Set `enabled: false` in `channels.yaml` to pause a channel without removing cron entries.

---

## Typical Workflow

1. **Configure** — Set up `channels.yaml` with your niches, voice IDs, and subreddits
2. **Scrape** — `scrape --format reddit --window month` to bootstrap the backlog
3. **Review** — `review` to approve/reject the first 25 posts (probation period)
4. **Generate** — `generate --format storytelling --from-backlog` to produce test videos
5. **Set up uploads** — `setup-youtube` and `setup-instagram` for each channel
6. **Automate** — Add `run-cycle` to cron for hands-off posting

---

## File Locations

| What | Where |
|------|-------|
| Generated videos | `output/{timestamp}/final.mp4` |
| Database | `data/pipeline.db` |
| Style profiles | `style_profiles/` |
| Background clips | `assets/backgrounds/` |
| Per-channel tokens | `data/channels/{slug}/` |
| Logs | `logs/pipeline.log` |
| Channel config | `channels.yaml` |
