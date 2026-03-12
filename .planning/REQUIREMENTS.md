# Requirements: Auto Shorts Pipeline

**Defined:** 2026-03-11
**Core Value:** A hands-off pipeline that wakes up twice a day, pulls from a pre-vetted content backlog, assembles and uploads videos, and grows multiple niche channels without manual intervention.

## v1 Requirements

### Reddit Scraping

- [x] **REDDIT-01**: Pipeline can scrape top posts from configured subreddits using PRAW or Reddit JSON API
- [ ] **REDDIT-02**: Scraped posts are scored by engagement (upvotes, ratio, comments) and filtered by minimum quality thresholds
- [x] **REDDIT-03**: Scraped posts are stored in the SQLite backlog with metadata (subreddit, score, length, scraped_at)
- [x] **REDDIT-04**: Scraper respects Reddit rate limits and handles failures gracefully

### Content Backlog

- [x] **BACKLOG-01**: SQLite DB maintains separate backlog queues for stories (per niche) and tweets (per niche)
- [x] **BACKLOG-02**: Backlog items have status: pending → approved → used
- [x] **BACKLOG-03**: Scheduler only pulls from approved backlog items — scraping and posting are fully decoupled
- [x] **BACKLOG-04**: CLI command to review and approve/reject pending backlog items

### Niche Configuration

- [x] **NICHE-01**: Each niche is defined in config with: name, subreddits, twitter accounts, voice ID, posting accounts
- [x] **NICHE-02**: Three niches configured out of the box: hypothetical-scenarios, relationships, finance-hustle
- [x] **NICHE-03**: Niche config drives which content is scraped, generated, and which channel it posts to

### AI Content Generation

- [ ] **GEN-01**: Claude (Haiku) can generate storytelling scripts from Reddit post title + body
- [ ] **GEN-02**: Generated scripts match the niche tone and are formatted for TTS (no markdown, natural speech)
- [ ] **GEN-03**: Generation is guided by style profile if one exists for the channel

### Quality Scoring

- [x] **QUALITY-01**: Stories are scored on: length fit (30-90s when narrated), engagement metrics, content appropriateness
- [x] **QUALITY-02**: Tweets are scored on: like count, retweet count, text quality (no links, mentions spam)
- [x] **QUALITY-03**: Items below quality threshold are rejected before entering backlog

### Upload Automation

- [ ] **UPLOAD-01**: Completed videos upload to YouTube Shorts via YouTube Data API v3 (OAuth 2.0)
- [ ] **UPLOAD-02**: Completed videos upload to Instagram Reels via Instagram Graph API
- [ ] **UPLOAD-03**: Upload includes title, description, and hashtags derived from content and niche
- [ ] **UPLOAD-04**: Upload failures are logged and retried with exponential backoff
- [ ] **UPLOAD-05**: Uploaded video records stored in DB with platform, video ID, upload timestamp

### Scheduler

- [ ] **SCHED-01**: Pipeline runs automatically 2x/day per channel at configurable times
- [ ] **SCHED-02**: Each run: pull from backlog → generate video → upload → log result
- [ ] **SCHED-03**: Backlog refill (scraping) runs on a separate cadence (e.g. daily or every 12h)
- [ ] **SCHED-04**: Scheduler uses cron or APScheduler — no external infrastructure required
- [ ] **SCHED-05**: Each channel's schedule is independently configurable

### Multi-Channel Orchestration

- [x] **MULTI-01**: Each niche channel operates with its own isolated backlog, config, and upload credentials
- [x] **MULTI-02**: A single scheduler process manages all channels
- [x] **MULTI-03**: CLI can target a specific channel or run all channels

## v2 Requirements

### Observability

- **OBS-01**: Daily summary report — videos posted, backlog levels, upload success/fail counts
- **OBS-02**: Backlog low-water alert — notify when a niche backlog drops below N items
- **OBS-03**: Per-channel performance dashboard (views, likes from platform APIs)

### Content Quality

- **QUALITY-04**: Vision-based thumbnail analysis to auto-select best frame for YouTube thumbnail
- **QUALITY-05**: A/B title testing — vary titles across uploads, track performance

### Distribution

- **DIST-01**: TikTok upload support
- **DIST-02**: Cross-posting same video to multiple platforms simultaneously

## Out of Scope

| Feature | Reason |
|---------|--------|
| AI story fallback | Backlog system makes this unnecessary — always have content ready |
| TikTok upload | Not requested for v1 |
| Web dashboard | CLI sufficient for v1 |
| Background music mixing | Not in current scope |
| AI-generated tweet text | Tweets are always real scraped content |
| Analytics tracking | Platform native analytics sufficient |
| Reddit OAuth | Public JSON API sufficient for scraping top posts |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NICHE-01 | Phase 1 | Complete |
| NICHE-02 | Phase 1 | Complete |
| NICHE-03 | Phase 1 | Complete |
| MULTI-01 | Phase 1 | Complete |
| MULTI-03 | Phase 1 | Complete |
| REDDIT-01 | Phase 2 | Complete |
| REDDIT-02 | Phase 2 | Pending |
| REDDIT-03 | Phase 2 | Complete |
| REDDIT-04 | Phase 2 | Complete |
| BACKLOG-01 | Phase 2 | Complete |
| BACKLOG-02 | Phase 2 | Complete |
| BACKLOG-03 | Phase 2 | Complete |
| BACKLOG-04 | Phase 2 | Complete |
| QUALITY-01 | Phase 2 | Complete |
| QUALITY-02 | Phase 2 | Complete |
| QUALITY-03 | Phase 2 | Complete |
| GEN-01 | Phase 3 | Pending |
| GEN-02 | Phase 3 | Pending |
| GEN-03 | Phase 3 | Pending |
| UPLOAD-01 | Phase 4 | Pending |
| UPLOAD-02 | Phase 4 | Pending |
| UPLOAD-03 | Phase 4 | Pending |
| UPLOAD-04 | Phase 4 | Pending |
| UPLOAD-05 | Phase 4 | Pending |
| SCHED-01 | Phase 4 | Pending |
| SCHED-02 | Phase 4 | Pending |
| SCHED-03 | Phase 4 | Pending |
| SCHED-04 | Phase 4 | Pending |
| SCHED-05 | Phase 4 | Pending |
| MULTI-02 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 after roadmap creation*
