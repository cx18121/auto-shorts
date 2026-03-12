---
phase: 04-upload-scheduler
plan: 02
subsystem: config
tags: [oauth, youtube, instagram, cli, channels, config]

# Dependency graph
requires:
  - phase: 01-niche-config-multi-channel-foundation
    provides: ChannelConfig dataclass and channels.yaml schema that this extends
provides:
  - ChannelConfig with enabled, hashtags, and instagram_user_id fields
  - setup-youtube CLI command for YouTube OAuth 2.0 token flow
  - setup-instagram CLI command for Instagram long-lived token exchange
  - pipeline/upload.py with setup_youtube_oauth() helper
affects:
  - 04-upload-scheduler plan 01 (upload.py upload functions need these tokens)
  - 04-upload-scheduler plan 03 (run-cycle uses enabled flag to skip channels)

# Tech tracking
tech-stack:
  added: [requests (used in upload.py OAuth exchange), webbrowser (opens OAuth URL)]
  patterns:
    - OAuth desktop flow with authorization code exchange (YouTube)
    - Instagram short-lived to long-lived token exchange via Graph API
    - Token files stored per-channel at data/channels/{slug}/*.json
    - Lazy imports inside CLI command functions (avoids channels.yaml import-time failure)

key-files:
  created:
    - pipeline/upload.py
  modified:
    - config.py
    - channels.yaml.example
    - main.py
    - tests/test_config_channels.py

key-decisions:
  - "pipeline/upload.py created to house setup_youtube_oauth() — plan referenced it but file did not exist (Rule 3 auto-fix)"
  - "Instagram token exchange uses channel_cfg.instagram_access_token field as app_secret placeholder; prompts user if empty"
  - "setup-instagram --token arg is optional: CLI prompts with instructions if omitted"

patterns-established:
  - "Token paths: data/channels/{slug}/youtube_token.json and instagram_token.json"
  - "OAuth setup commands follow: validate creds → check existing token → run flow → save → print compliance notes"

requirements-completed: [SCHED-05, MULTI-02]

# Metrics
duration: 7min
completed: 2026-03-12
---

# Phase 04 Plan 02: Channel Config Extensions and OAuth Setup Summary

**ChannelConfig extended with enabled/hashtags/instagram_user_id fields; setup-youtube and setup-instagram CLI commands added with full OAuth flows saving tokens per-channel**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-12T19:20:00Z
- **Completed:** 2026-03-12T19:26:03Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added `enabled` (bool, default True), `hashtags` (list, default []), and `instagram_user_id` (str, default "") to ChannelConfig dataclass
- Updated channels.yaml.example for all three niches with niche-specific hashtags
- Added `setup-youtube` CLI subcommand: runs OAuth 2.0 desktop flow, saves token to data/channels/{slug}/youtube_token.json, prints API compliance audit warning
- Added `setup-instagram` CLI subcommand: exchanges short-lived token for long-lived via Instagram Graph API, fetches numeric user ID, saves to instagram_token.json
- Created pipeline/upload.py with setup_youtube_oauth() using authorization code flow with 3-retry exponential backoff
- Added 4 new passing tests (12 total, all pass)

## Task Commits

1. **Task 1: Add enabled, hashtags, instagram_user_id to ChannelConfig** - `1411453` (feat)
2. **Task 2: Add setup-youtube and setup-instagram CLI subcommands** - `80432cd` (feat)

## Files Created/Modified

- `config.py` - Added enabled, hashtags, instagram_user_id fields to ChannelConfig dataclass
- `channels.yaml.example` - Added all three new fields with niche-specific hashtags to each channel block
- `main.py` - Added setup-youtube and setup-instagram subparsers, cmd_setup_youtube(), cmd_setup_instagram(), wired into _dispatch_command()
- `tests/test_config_channels.py` - Added 4 new tests for defaults and field loading
- `pipeline/upload.py` (created) - setup_youtube_oauth() with OAuth 2.0 authorization code flow

## Decisions Made

- Created pipeline/upload.py to house setup_youtube_oauth() — plan referenced it as the import target but the file did not exist (Rule 3 blocking issue, auto-fixed)
- Instagram cmd uses channel_cfg.instagram_access_token as app_secret placeholder; if empty, prompts user — keeps the flow functional without requiring a dedicated app_secret field on ChannelConfig
- setup-instagram prompts for short-lived token interactively if --token not provided, with step-by-step instructions printed to terminal

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created missing pipeline/upload.py**
- **Found during:** Task 2 (setup-youtube CLI command)
- **Issue:** Plan specified `cmd_setup_youtube` imports `setup_youtube_oauth` from `pipeline.upload`, but pipeline/upload.py did not exist
- **Fix:** Created pipeline/upload.py with setup_youtube_oauth() implementing the full OAuth 2.0 authorization code desktop flow
- **Files modified:** pipeline/upload.py (created)
- **Verification:** `python3 main.py --help` shows both new commands; tests all pass
- **Committed in:** 80432cd (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (blocking — missing referenced file)
**Impact on plan:** Required for the import to work. No scope creep — upload.py currently only contains the OAuth setup helper.

## Issues Encountered

None — plan executed smoothly once upload.py was created.

## User Setup Required

External services (YouTube and Instagram) require manual credential configuration before the setup commands can be used:

**YouTube:**
- Create an OAuth 2.0 Client ID (Desktop app type) in Google Cloud Console → APIs & Services → Credentials
- Enable YouTube Data API v3 in Google Cloud Console → APIs & Services → Library
- Add youtube_client_id and youtube_client_secret to channels.yaml for the target channel
- Complete YouTube API compliance audit (uploads locked to private until audited): https://support.google.com/youtube/contact/yt_api_form

**Instagram:**
- Ensure Instagram account is Business or Creator type (Settings → Account → Switch to Professional Account)
- Connect Instagram Business account to a Facebook Page (Facebook Page Settings → Instagram)
- Create a Meta App with instagram_content_publish permission (developers.facebook.com → My Apps)
- Use `python main.py --channel {slug} setup-instagram` to exchange and save the token

## Next Phase Readiness

- ChannelConfig fields (enabled, hashtags, instagram_user_id) are ready for use by Plan 01 (uploader) and Plan 03 (run-cycle orchestrator)
- Token paths are established: data/channels/{slug}/youtube_token.json and instagram_token.json
- upload.py is scaffolded and ready for upload function implementation in Plan 01

---
*Phase: 04-upload-scheduler*
*Completed: 2026-03-12*
