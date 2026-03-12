# Roadmap: Auto Shorts Pipeline

## Overview

The existing codebase already assembles videos (storytelling and tweet formats) and analyzes channels. The remaining work is the automation layer: niche-specific configuration, a content backlog system fed by Reddit scraping and AI generation, and a scheduler that uploads videos twice a day without human intervention.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Niche Config + Multi-Channel Foundation** - Define per-channel config, isolate backlogs and credentials, wire multi-channel CLI targeting (completed 2026-03-12)
- [ ] **Phase 2: Content Pipeline** - Reddit scraper, backlog DB, quality scoring — content flows in and waits to be consumed
- [ ] **Phase 3: AI Story Generation** - Claude generates scripts from Reddit posts when backlog is thin; guided by style profiles
- [ ] **Phase 4: Upload + Scheduler** - Automated twice-daily posting to YouTube Shorts and Instagram Reels across all three channels

## Phase Details

### Phase 1: Niche Config + Multi-Channel Foundation
**Goal**: Each of the three niche channels has a complete, isolated configuration that drives what gets scraped, which voice narrates, and which upload accounts receive the videos
**Depends on**: Nothing (first phase)
**Requirements**: NICHE-01, NICHE-02, NICHE-03, MULTI-01, MULTI-02, MULTI-03
**Success Criteria** (what must be TRUE):
  1. Running `python main.py --channel hypothetical-scenarios` targets only that channel's subreddits, Twitter accounts, voice, and upload credentials
  2. All three niches (hypothetical-scenarios, relationships, finance-hustle) are configured out of the box with correct subreddits and Twitter accounts
  3. Each niche channel has its own isolated backlog partition and upload credential store — no data bleeds across channels
  4. CLI accepts a `--channel` flag (or "all") and routes all downstream operations through that channel's config
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — channels.yaml.example + test scaffolds (RED state TDD contracts)
- [ ] 01-02-PLAN.md — config.py extended with ChannelConfig dataclass and load_channels/get_channel
- [ ] 01-03-PLAN.md — main.py wired with --channel global flag and _dispatch_command routing

### Phase 2: Content Pipeline
**Goal**: Reddit posts and tweets are automatically scraped, scored, and stored in a per-channel backlog that the scheduler can pull from — fully decoupled from video generation
**Depends on**: Phase 1
**Requirements**: REDDIT-01, REDDIT-02, REDDIT-03, REDDIT-04, BACKLOG-01, BACKLOG-02, BACKLOG-03, BACKLOG-04, QUALITY-01, QUALITY-02, QUALITY-03
**Success Criteria** (what must be TRUE):
  1. Running the scrape job populates the backlog DB with scored Reddit posts from the correct subreddits for each niche
  2. Items below quality thresholds (engagement, length, content) are rejected before entering the backlog — never appear as approved items
  3. Backlog items flow through pending → approved → used states; the scheduler only sees approved items
  4. Running `python main.py --channel relationships review` shows pending items and accepts approve/reject input
  5. A scrape job failing for one niche logs the error and continues — other niches are unaffected
**Plans**: 6 plans

Plans:
- [ ] 02-01-PLAN.md — DB schema (backlog_stories, backlog_tweets, niche_state) + ChannelConfig quality field + channels.yaml.example quality sections + RED test stubs
- [ ] 02-02-PLAN.md — pipeline/backlog.py CRUD + status transitions + probation logic
- [ ] 02-03-PLAN.md — pipeline/quality_filter.py threshold-based story and tweet scoring
- [ ] 02-04-PLAN.md — formats/storytelling/scraper.py PRAW Reddit scraper wired to quality filter + backlog
- [ ] 02-05-PLAN.md — formats/tweets/scraper.py browser leak fix + scrape_and_store_tweets()
- [ ] 02-06-PLAN.md — main.py scrape/review/backlog-status subcommands + human-verify checkpoint

### Phase 3: AI Story Generation
**Goal**: Claude can generate a narration-ready story script from a Reddit post title and body, matching the niche tone and style profile, so the backlog can be topped up when real posts are scarce
**Depends on**: Phase 2
**Requirements**: GEN-01, GEN-02, GEN-03
**Success Criteria** (what must be TRUE):
  1. Given a Reddit post title and body, Claude Haiku produces a script with no markdown, natural speech phrasing, and an estimated duration between 30 and 90 seconds
  2. Generated scripts use the niche tone (hypothetical scenarios sound contemplative, relationships sound empathetic, finance sounds punchy)
  3. If a style profile exists for the channel, the generated script reflects its hook structure and narrative patterns
**Plans**: TBD

### Phase 4: Upload + Scheduler
**Goal**: The pipeline wakes up twice a day per channel, pulls the best available content from the backlog, generates a video, uploads it to YouTube Shorts and Instagram Reels, and logs the result — zero human intervention required
**Depends on**: Phase 2, Phase 3
**Requirements**: UPLOAD-01, UPLOAD-02, UPLOAD-03, UPLOAD-04, UPLOAD-05, SCHED-01, SCHED-02, SCHED-03, SCHED-04, SCHED-05, MULTI-02
**Success Criteria** (what must be TRUE):
  1. A video generated by the pipeline appears on YouTube Shorts with correct title, description, and hashtags derived from the content and niche
  2. The same video (or a second video) uploads to Instagram Reels for the same channel in the same automated run
  3. Upload failures are retried with exponential backoff; after exhausting retries the failure is logged and the scheduler continues to the next channel
  4. The scheduler runs automatically at configured times (e.g. 09:00 and 21:00) using cron or APScheduler without any manual trigger
  5. Each channel's schedule is independently configurable; pausing one channel does not affect the others
  6. Upload records (platform, video ID, timestamp) are stored in the DB and queryable via CLI
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Niche Config + Multi-Channel Foundation | 3/3 | Complete   | 2026-03-12 |
| 2. Content Pipeline | 3/6 | In Progress|  |
| 3. AI Story Generation | 0/TBD | Not started | - |
| 4. Upload + Scheduler | 0/TBD | Not started | - |
