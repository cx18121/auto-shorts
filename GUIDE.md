# Auto-Shorts Pipeline — User Guide

This pipeline automatically makes YouTube Shorts and Instagram Reels from Reddit posts and tweets.

Every command starts with:
```
python main.py --channel SLUG <command>
```

Use `--channel all` to run across all channels.

---

## Quick Start

1. Copy `channels.yaml.example` to `channels.yaml` and fill in your API keys
2. Create `.env` with your API keys (see Setup below)
3. `pip install -r requirements.txt && playwright install chromium`
4. Put gameplay clips in `assets/backgrounds/`
5. Scrape some content: `python main.py --channel my-channel scrape --format reddit --window month`
6. Review it: `python main.py --channel my-channel review`
7. Make a video: `python main.py --channel my-channel generate --format storytelling --from-backlog`

---

## Setup

### .env File

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
  style_profile: ""
```

---

## Commands

### Scrape — Fill the backlog

```bash
python main.py --channel my-channel scrape --format reddit
python main.py --channel my-channel scrape --format tweets
python main.py --channel my-channel scrape --format reddit --window month   # grab a month of posts
python main.py --channel my-channel scrape --format reddit --review         # scrape then review immediately
```

### Review — Approve or reject pending items

```bash
python main.py --channel my-channel review
```

Type `y` to approve, `n` to reject, `s` to skip. After 25 manual reviews, new items are auto-approved.

### Backlog Status — See what's in the queue

```bash
python main.py --channel my-channel backlog-status
python main.py --channel all backlog-status
```

### Generate — Make videos

```bash
# From approved backlog items (most common)
python main.py --channel my-channel generate --format storytelling --from-backlog
python main.py --channel my-channel generate --format storytelling --from-backlog --count 3
python main.py --channel my-channel generate --format storytelling --from-backlog --pick       # choose which story
python main.py --channel my-channel generate --format storytelling --from-backlog --no-audio   # test layout without TTS
python main.py --channel my-channel generate --format storytelling --from-backlog --keep-backlog  # don't mark as used

# From a style profile (AI-generated)
python main.py --channel my-channel generate --format storytelling --profile style_profiles/x.json

# Tweet videos
python main.py --channel my-channel generate --format tweets --scrape --count 3
python main.py --channel my-channel generate --format tweets --profile style_profiles/x.json
```

### Run Cycle — Full automated posting

Pulls from backlog, generates a video, uploads to YouTube + Instagram, marks item as used.

```bash
python main.py --channel my-channel run-cycle

# Schedule a YouTube publish time (uploads as private, goes public at the given time)
python main.py --channel my-channel run-cycle --publish-at 2026-03-13T09:00:00Z
```

What happens:
1. Picks the top approved backlog item
2. If backlog is empty, scrapes automatically
3. Generates the video (TTS + render + assemble)
4. Generates title + hashtags via Claude
5. Uploads to YouTube and Instagram (skips whichever isn't configured)
6. Marks the item as used

Note: `--publish-at` skips Instagram (not supported by their API).

### Upload History

```bash
python main.py --channel my-channel upload-history
```

### Analyze — Study existing channels

```bash
python main.py --channel my-channel analyze --channels "https://youtube.com/@SomeChannel"
python main.py --channel my-channel analyze --channels "URL1" "URL2" --visual
```

Generates a style profile JSON that guides AI content generation.

### Platform Setup

```bash
# YouTube (opens browser for OAuth)
python main.py --channel my-channel setup-youtube

# Instagram (exchange short-lived token for long-lived)
python main.py --channel my-channel setup-instagram
python main.py --channel my-channel setup-instagram --token "YOUR_TOKEN"

# Twitter/X (for tweet scraping)
python main.py --channel my-channel setup-twitter --username X --password X --email X
```

---

## Automate with Cron

```cron
# Scrape daily at 04:00 UTC
0 4 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel my-channel scrape --format reddit >> logs/cron-scrape.log 2>&1

# Post at 09:00 and 21:00 UTC
0 9 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel my-channel run-cycle >> logs/cron-run.log 2>&1
0 21 * * * cd /path/to/auto-shorts && .venv/bin/python3 main.py --channel my-channel run-cycle >> logs/cron-run.log 2>&1
```

Create `logs/` first: `mkdir -p logs`

Set `enabled: false` in `channels.yaml` to pause a channel without removing cron entries.

---

## Video Settings

Both formats output 1080×1920 MP4 at CRF 18.

| Setting | Value |
|---------|-------|
| Narration speed | 1.5× (atempo) |
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
| Style profiles | `style_profiles/` |
| Background clips | `assets/backgrounds/` |
| Background music | `assets/music/` |
| Channel tokens | `data/channels/{slug}/` |
| Logs | `logs/pipeline.log` |
| Channel config | `channels.yaml` |
