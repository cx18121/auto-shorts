---
phase: 04-upload-scheduler
plan: 01
subsystem: upload
tags: [youtube, instagram, oauth, upload, metadata, sqlite, retry]

# Dependency graph
requires:
  - phase: 04-upload-scheduler plan 02
    provides: ChannelConfig with OAuth fields, setup_youtube_oauth scaffold
provides:
  - upload_to_youtube() with OAuth credential refresh and resumable upload
  - upload_to_instagram() with container→poll→publish flow
  - refresh_instagram_token_if_needed() for long-lived token management
  - generate_upload_metadata() via Claude Haiku for title + hashtags
  - init_upload_table() and log_upload() for SQLite tracking
  - get_upload_history() for upload record queries
affects:
  - 04-upload-scheduler plan 03 (run-cycle orchestrator calls all upload functions)

# Tech tracking
tech-stack:
  added: [google-auth-oauthlib, google-auth-httplib2, google-api-python-client]
  patterns:
    - YouTube resumable upload with exponential backoff on 5xx (MAX_RETRIES=10)
    - Instagram Graph API v18.0 container→poll→publish pattern
    - Claude Haiku for AI-generated metadata (temp 0.85, max_tokens 256)
    - SQLite uploads table for cross-platform upload tracking

key-files:
  created:
    - pipeline/upload.py
  modified:
    - tests/test_upload.py
    - requirements.txt

key-decisions:
  - "Instagram token refresh threshold set to 7 days before expiry"
  - "YouTube retry uses random jitter: random.random() * 2^retry for backoff"
  - "Metadata fallback: on Claude failure, uses first 80 chars of content as title"

patterns-established:
  - "Upload logging: channel + platform + video_id + title + status + error_msg + uploaded_at"
  - "All external API calls wrapped in try/except with logging"

requirements-completed: [UPLOAD-01, UPLOAD-02, UPLOAD-03, UPLOAD-04, UPLOAD-05]

# Metrics
duration: ~10min
completed: 2026-03-12
---

# Phase 04 Plan 01: Upload Module Summary

**Built pipeline/upload.py with YouTube OAuth upload, Instagram Reels upload, Claude Haiku metadata generation, SQLite upload logging, and retry logic — all 31 tests passing**

## Performance

- **Completed:** 2026-03-12
- **Tasks:** 1 (single comprehensive task)
- **Files modified:** 3

## Accomplishments

- `init_upload_table(conn)` — Creates uploads DDL in SQLite
- `log_upload(conn, ...)` — Inserts upload record with UTC timestamp
- `get_upload_history(conn, channel)` — Returns recent uploads filtered by channel
- `setup_youtube_oauth(channel_cfg, token_path)` — OAuth 2.0 desktop flow with compliance warning
- `upload_to_youtube(video_path, title, description, tags, token_path, client_id, client_secret)` — Loads/refreshes creds, resumable upload via `videos().insert()`
- `_resumable_upload(insert_request)` — Retry loop with exponential backoff on 500/502/503/504
- `upload_to_instagram(video_url, caption, ig_user_id, access_token)` — Container create → poll status → publish, raises on ERROR/timeout
- `refresh_instagram_token_if_needed(token_path)` — Refreshes long-lived token within 7 days of expiry
- `generate_upload_metadata(content_text, niche_hashtags, format_type)` — Claude Haiku → title + deduplicated hashtags

## Task Commits

1. **Task 1: Upload module implementation** - `9fbc9de` (feat)

## Files Created/Modified

- `pipeline/upload.py` — All 9 upload functions (521 lines)
- `tests/test_upload.py` — 31 tests across 7 test classes, all passing
- `requirements.txt` — Added google-auth-oauthlib, google-auth-httplib2

## Issues Encountered

- Test import failure: `config.py` module-level `load_channels()` raises SystemExit when channels.yaml missing — fixed by mocking config module before import in tests

---
*Phase: 04-upload-scheduler*
*Completed: 2026-03-12*
