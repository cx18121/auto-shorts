# Phase 4: Upload + Scheduler - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

The pipeline wakes up twice a day per channel, pulls the best available content from the backlog, generates a video, uploads it to YouTube Shorts and Instagram Reels, and logs the result — zero human intervention required. This phase delivers: upload module (YouTube + Instagram), run-cycle orchestration, CLI setup commands for OAuth, upload record tracking, and cron-based scheduling. No new content generation logic — that's already built (Phases 2-3).

</domain>

<decisions>
## Implementation Decisions

### Scheduling mechanism
- **System cron** — crontab entries call `python main.py --channel X run-cycle`. OS handles timing, no daemon needed
- Posting runs 2x/day per channel (e.g. `0 9,21 * * *`); scraping runs on a **separate cron job** (e.g. once daily)
- Schedule configuration: Claude's discretion (channels.yaml config with `install-cron` command, or documented example crontab entries)
- Each channel has an `enabled: true/false` field in channels.yaml — `run-cycle` checks this and skips disabled channels
- Works locally now, works on a VPS later with zero changes

### Upload metadata
- **Titles**: Claude generates a YouTube-optimized title for every video (both storytelling and tweets) as part of the upload metadata step
- **Hashtags**: Base hashtags from a per-channel `hashtags` list in channels.yaml + Claude adds 2-3 content-specific hashtags per video
- **Descriptions**: Claude's discretion (template-based or generated per video)
- **Same metadata** used for both YouTube and Instagram — no platform-specific variants

### Credential & auth flow
- **YouTube OAuth 2.0**: A `python main.py --channel X setup-youtube` CLI command opens a browser, completes the OAuth consent flow, and saves the refresh token. Run once per channel
- **YouTube token storage**: JSON file per channel at `data/channels/{slug}/youtube_token.json` (gitignored). google-auth library handles auto-refresh of access tokens
- **Instagram Graph API**: A `python main.py --channel X setup-instagram` CLI command walks through getting a long-lived token. Similar flow to YouTube setup
- **Instagram token storage**: Same pattern — JSON file at `data/channels/{slug}/instagram_token.json`
- **Auth errors at runtime**: Skip the platform (or channel), log the error, continue with the rest. Don't block other channels

### Run orchestration
- **One video per run** — each `run-cycle` produces and uploads exactly one video. 2 runs/day = 2 videos/day per channel
- **Content selection**: Highest scored approved item from the backlog is picked first
- **Empty backlog handling**: If no approved items exist, automatically trigger a scrape to refill, then continue the cycle
- **Flow**: pick from backlog → generate video → generate upload metadata (title/description/hashtags via Claude) → upload to YouTube → upload to Instagram → mark backlog item as used → log upload record
- **Upload records**: Stored in DB (platform, video ID, timestamp, title, status) and queryable via CLI (Claude's discretion on whether new command or extension of backlog-status)

### Claude's Discretion
- Whether schedule times are configured in channels.yaml with an `install-cron` helper or just documented as example crontab entries
- Description generation approach (template vs per-video)
- Upload history CLI design (new `upload-history` command vs extending `backlog-status`)
- Instagram token acquisition UX details
- YouTube client ID/secret sourcing (from channels.yaml fields that already exist, or from .env)

</decisions>

<specifics>
## Specific Ideas

- The existing `_generate_storytelling_from_backlog()` and `_run_storytelling_pipeline()` / `_run_tweet_pipeline()` functions in main.py are the building blocks — `run-cycle` orchestrates them with upload on top
- The `youtube_client_id` and `youtube_client_secret` fields already exist in channels.yaml from Phase 1 — they're ready to be used
- `data/channels/{slug}/` directories already exist (created by config.py at startup) — token files go there naturally
- The requirement says "single scheduler process manages all channels" (MULTI-02) — with cron, `--channel all` in a single crontab entry satisfies this, or individual per-channel entries both work

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `main.py:_generate_storytelling_from_backlog()`: Already pulls from backlog, generates video, marks used — just needs upload step added
- `main.py:_run_storytelling_pipeline()` / `_run_tweet_pipeline()`: Video generation pipelines ready to use
- `pipeline/backlog.py`: `get_approved_stories()`, `get_approved_tweets()`, `mark_story_used()`, `mark_used()` — backlog CRUD ready
- `config.py:ChannelConfig`: Already has `youtube_client_id`, `youtube_client_secret`, `instagram_access_token` fields
- `data/channels/{slug}/` directories: Already created at startup by `load_channels()` — token files go here

### Established Patterns
- Functions over classes, type hints on all functions
- 3 retries + exponential backoff on all external API calls
- Failed items log and continue — never block the pipeline
- `--channel` always required; `--channel all` runs sequentially
- Logging via `logging.getLogger(__name__)` with INFO/WARNING/ERROR levels

### Integration Points
- `main.py`: New `run-cycle`, `setup-youtube`, `setup-instagram` subcommands added to argparse
- `channels.yaml`: New fields: `enabled`, `hashtags` list; existing `youtube_client_id`/`youtube_client_secret`/`instagram_access_token` used
- `data/pipeline.db`: New `uploads` table for tracking upload records
- `pipeline/upload.py`: New module for YouTube and Instagram upload logic
- `cmd_scrape()`: Called by run-cycle as fallback when backlog is empty

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-upload-scheduler*
*Context gathered: 2026-03-12*
