# Auto Shorts Pipeline

## What This Is

A fully automated YouTube Shorts and Instagram Reels pipeline that scrapes viral content (Reddit stories + real tweets), generates videos in two formats (narrated storytelling and tweet screenshot compilations), and uploads them to niche-specific channels on a schedule. Three niche channels run in parallel: hypothetical scenarios, relationships, and finance/hustle/startup culture.

## Core Value

A hands-off pipeline that wakes up twice a day, pulls from a pre-vetted content backlog, assembles and uploads videos, and grows multiple niche channels without manual intervention.

## Requirements

### Validated

- ✓ TTS narration with word-level timestamps (ElevenLabs) — existing
- ✓ ASS subtitle/overlay generation — existing
- ✓ Tweet screenshot renderer (HTML + Playwright, X dark mode) — existing
- ✓ Tweet scraper (Playwright + cookie auth, home feed + curated accounts) — existing
- ✓ Tweet video assembler (FFmpeg zoompan) — existing
- ✓ Storytelling video assembler (FFmpeg, background + audio + subs) — existing
- ✓ Channel analysis system (YouTube API → transcripts → style profiles) — existing
- ✓ CLI runner (analyze / generate / setup-twitter commands) — existing
- ✓ SQLite pipeline state database — existing

### Active

- [ ] Reddit scraper — pull top posts from niche subreddits, score by engagement, store in backlog
- [ ] Content backlog system — decouple scraping from posting; maintain queue of quality-checked stories and tweets
- [ ] Niche configuration — per-channel config mapping niche → subreddits + Twitter accounts + voice + style
- [ ] AI content generation — Claude generates stories when Reddit backlog is low (tweets always scraped)
- [ ] Quality scoring — filter stories and tweets against engagement + length + content criteria before backlog
- [ ] Upload automation — YouTube Shorts + Instagram Reels via their respective APIs
- [ ] Scheduler — run pipeline 2x/day per channel, coordinate backlog refill + video generation + upload
- [ ] Multi-channel orchestration — manage 3 niche channels independently with isolated configs and backlogs

### Out of Scope

- TikTok upload — not requested; add later if needed
- Web dashboard — CLI is sufficient for v1
- Background music mixing — not in current scope
- AI-generated tweet text — tweets are always real scraped content
- AI story fallback — backlog system makes this unnecessary for v1
- Analytics tracking — platform native analytics sufficient for now

## Context

Three target niches, each with its own channel(s) on YouTube Shorts + Instagram Reels:

| Niche | Subreddits | Twitter accounts |
|-------|-----------|-----------------|
| Hypothetical scenarios | r/hypotheticalsituation | Philosophy/thought experiment accounts |
| Relationships | r/AITA, r/TrueOffMyChest, r/relationship_advice | Relationship/advice accounts |
| Finance/hustle | r/financialindependence, r/entrepreneur, r/startups | naval, paulg, sama, levelsio, morganhousel |

**Posting cadence:** 2 videos/day per channel (1 storytelling + 1 tweet compilation, or 2 of one format).

**Backlog model:** Scraping runs independently of posting. A rolling backlog of pre-scored content (stories + tweets) ensures posting slots are always filled. Scraping tops up the backlog; the scheduler pulls from it.

**Content pipeline flow:**
1. Scraper jobs run periodically → score content → store in backlog DB
2. Scheduler triggers 2x/day → pulls best available from backlog → generates video → uploads
3. Each niche channel is fully independent with its own backlog and config

## Constraints

- **Tech stack**: Python only. FFmpeg via subprocess (no MoviePy). Playwright for browser automation. SQLite for all state.
- **APIs**: YouTube Data API v3 (upload via OAuth). Instagram Graph API. ElevenLabs TTS. Anthropic (Haiku for generation, Sonnet for quality/analysis).
- **Auth**: YouTube OAuth 2.0 required for upload. Instagram requires Facebook app + Graph API token. Twitter/X cookies file for scraping.
- **Reddit**: Use PRAW or Reddit JSON API (no auth required for public posts). Respect rate limits.
- **No scheduling infrastructure**: Use cron or a simple Python scheduler (APScheduler) — no external services.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reddit scraping over AI stories | Real stories have authentic voice and are already engagement-validated | — Pending |
| Backlog system over on-demand generation | Decouples scraping latency from posting schedule; always have content ready | — Pending |
| Niche-specific channels | Better algorithm performance and audience retention than general content | — Pending |
| Playwright for tweet scraping | twscrape broken (X changed API response format); Playwright + cookies is more robust | ✓ Good |
| No AI story fallback | Backlog keeps queue full; AI fallback adds complexity without clear need | — Pending |

---
*Last updated: 2026-03-11 after initialization*
