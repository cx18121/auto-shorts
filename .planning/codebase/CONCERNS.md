# Codebase Concerns

**Analysis Date:** 2026-03-11

## Tech Debt

**External API Key Exposure Risk:**
- Issue: Multiple API keys (ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, YOUTUBE_API_KEY) loaded into memory via `config.py` without encryption. If a process crashes or logs are captured, secrets could be exposed.
- Files: `config.py`, `pipeline/tts.py`, `formats/tweets/generator.py`, `formats/storytelling/generator.py`, `analysis/fetcher.py`
- Impact: Security breach if credentials are logged, dumped in error messages, or process memory is inspected
- Fix approach: Use Python `keyring` library or environment-only secrets, never print API keys in logs, implement masked logging for sensitive values

**Playwright Browser Resource Leaks:**
- Issue: `formats/tweets/renderer.py` line 161-177 creates a Playwright browser instance but error paths don't guarantee `browser.close()` is called. If rendering fails, browser process remains open.
- Files: `formats/tweets/renderer.py` (_render_html function)
- Impact: Memory leak, accumulated zombie browser processes, system slowdown on batch operations
- Fix approach: Wrap browser lifecycle in try/finally or use context manager pattern

**FFmpeg Error Handling Incomplete:**
- Issue: Both `formats/storytelling/assembler.py` and `formats/tweets/assembler.py` capture FFmpeg stderr but only log last 20 lines. Complex encoding errors may be truncated, making debugging difficult.
- Files: `formats/storytelling/assembler.py` line 191, `formats/tweets/assembler.py` line 122
- Impact: Silent failures in video encoding with insufficient error context. Failed videos still logged as success if FFmpeg exit code isn't checked properly.
- Fix approach: Log full stderr to file, increase tail limit, or stream stderr during execution

**YouTube Transcript Retry Logic Silently Fails:**
- Issue: `analysis/transcripts.py` _fetch_one() function catches all exceptions broadly and returns None. SSL errors, connection drops, and quota errors treated identically — no distinction made.
- Files: `analysis/transcripts.py` lines 103-128
- Impact: Identical retry behavior for transient errors (network blip) vs. permanent errors (disabled captions). Wastes time retrying impossible fetches.
- Fix approach: Categorize exceptions; only retry transient types (ConnectionError, Timeout); fail fast on permanent errors (NoTranscriptFound, TranscriptsDisabled)

**Database Connection Not Closed:**
- Issue: `analysis/db.py` get_connection() returns a connection but relies on context manager cleanup. Many call sites use bare `with get_connection() as conn:` which is safe, but function signature doesn't enforce it.
- Files: `analysis/db.py`, `analysis/transcripts.py` line 64, `analysis/fetcher.py` line 232
- Impact: Potential resource exhaustion if code path doesn't use context manager (high count of open connections)
- Fix approach: Add type hint `ContextManager[sqlite3.Connection]`, document requirement, add assertions in tests

**Timestamp Millisecond Precision Loss:**
- Issue: `pipeline/tts.py` _characters_to_words() converts character-level timestamps from floats to int milliseconds via rounding (line 138-139). Float rounding errors accumulate across words.
- Files: `pipeline/tts.py` lines 138-139, 154-155
- Impact: Word-level subtitle timing gradually drifts from actual audio as words accumulate; noticeable misalignment over 30+ second videos
- Fix approach: Use Decimal for intermediate calculations or preserve float milliseconds throughout, round only at final output

**Quality Check Retry Limit Hardcoded:**
- Issue: MAX_QUALITY_RETRIES set to 3 in `main.py` line 24 but can't be configured via CLI. If content generation is slow, this causes failures that could be solved with more retries.
- Files: `main.py` line 24, 369
- Impact: Rejected content on slow API days despite content being valid; unpredictable generation rates
- Fix approach: Make retry count a CLI flag (--max-retries), default to 3

## Known Bugs

**Tweet Text Newline Rendering Issue:**
- Symptoms: Newlines in AI-generated tweets appear as literal `\n` in rendered screenshots, not as line breaks
- Files: `formats/tweets/renderer.py` line 143
- Trigger: Call generate_tweet() from generator.py which can produce multi-line text; render_tweet() will display incorrectly
- Workaround: HTML template CSS uses `white-space: pre-wrap` but line 143 is redundant: `text.replace("\n", "\n")` does nothing

**ElevenLabs Timestamp Alignment Field Inconsistency:**
- Symptoms: Word timestamps missing or empty when using ElevenLabs v2 model
- Files: `pipeline/tts.py` lines 57, 124-126
- Trigger: ElevenLabs API response contains `normalized_alignment` instead of `alignment` in some cases
- Workaround: Code handles both via fallback on line 57: `alignment.get("alignment") or alignment.get("normalized_alignment", {})`
- Root cause: ElevenLabs SDK version mismatch; API docs don't specify field name consistency

**Playwright Page Viewport Not Square:**
- Symptoms: Tweet rendered HTML scaled to 600x900 viewport (16:9 aspect) but canvas is 1080x1920 (9:16). Resulting tweet screenshot distorted/stretched
- Files: `formats/tweets/renderer.py` lines 162-164
- Trigger: Every tweet render. The composition step scales but introduces aspect ratio mismatch
- Impact: Visual quality degradation, rendered tweets appear squashed

**Profile Image Fallback Color Determinism:**
- Symptoms: Avatar colors different each run even for same username if image URL unavailable
- Files: `formats/tweets/renderer.py` line 96 — avatar palette index calculated as `sum(ord(c) for c in username) % len(AVATAR_PALETTE)`
- Trigger: When profile_image_url is None or fails to download
- Impact: Inconsistent video output for same tweet content; non-deterministic
- Workaround: Currently deterministic per username, but if username changes, color changes too

## Security Considerations

**Twitter/X Cookie Storage Unencrypted:**
- Risk: `data/x.com_cookies.txt` contains authentication cookies in plain Netscape format on disk. If attacker gains file access, can impersonate authenticated account.
- Files: `config.py` line 28, `formats/tweets/scraper.py` line 22
- Current mitigation: Relies on file system permissions (root-only); not version controlled (in .gitignore); local-only
- Recommendations: Encrypt at rest using cryptography library; use OAuth if available; rotate credentials regularly; warn user on first setup

**YouTube Cookie Authorization Not Validated:**
- Risk: `analysis/transcripts.py` loads cookies but never validates they're fresh/valid. Expired cookies silently fail, falling back to proxy/direct with no warning.
- Files: `analysis/transcripts.py` lines 76-86
- Current mitigation: Retry logic eventually falls back; logs indicate which method used
- Recommendations: Validate cookie freshness before use; check for auth errors explicitly; alert user to refresh cookies if expired

**Claude API Key in Logs:**
- Risk: If Claude API call fails, exception might include headers or full request which contain `xi-api-key`
- Files: `pipeline/tts.py`, `formats/tweets/generator.py`, `formats/storytelling/generator.py`
- Current mitigation: Uses requests library which generally doesn't log headers; structured logging only captures formatted messages
- Recommendations: Explicitly strip API key from any logged exceptions; use string truncation for request/response logging

**Playwright Browser Launch with Default Permissions:**
- Risk: Browsers launched with `headless=True` but no sandbox/security flags. Malicious webpage content could potentially break out (low risk in practice since only visiting X.com, but principle matters).
- Files: `formats/tweets/renderer.py` line 161
- Current mitigation: Only used for rendering internal HTML templates and loading image URLs
- Recommendations: Add `--disable-dev-shm-usage` flag for Docker environments; consider sandboxing

**Twscrape Account Credentials Stored in Database:**
- Risk: `formats/tweets/scraper.py` setup_account() stores credentials in SQLite database (`data/twscrape_accounts.db`) — likely plaintext or minimally obfuscated
- Files: `formats/tweets/scraper.py`, `data/twscrape_accounts.db`
- Current mitigation: Local file only, gitignored
- Recommendations: Don't store passwords; use session tokens instead; encrypt database with SQLCipher

## Performance Bottlenecks

**YouTube Video Download Blocking on Visual Analysis:**
- Problem: `analysis/visual.py` downloads full videos via yt-dlp (up to 720p) sequentially. A single stalled download blocks entire channel analysis for 120+ seconds (line 119 timeout).
- Files: `analysis/visual.py` lines 102-129
- Cause: Sequential downloads; no parallelization; long timeout
- Improvement path: Implement async/concurrent download with asyncio or ThreadPoolExecutor; reduce timeout to 30s; pre-check video availability

**Frame Extraction Copies All Frames to Disk:**
- Problem: `analysis/visual.py` extracts 9 frames per video × 20 videos = 180 JPEG files created on disk, then loaded into memory for Claude vision. Unnecessary I/O.
- Files: `analysis/visual.py` lines 145-175
- Cause: Writes to disk instead of piping FFmpeg output to memory
- Improvement path: Use FFmpeg pipe output with PIL to load frames directly into memory; delete temp files as soon as analysis complete

**Playwright Page Waits with Hard Timeouts:**
- Problem: `formats/tweets/scraper.py` line 267 waits 30 seconds for page load, line 268 waits 20 seconds for tweet selector. If page slow, both waits stack.
- Files: `formats/tweets/scraper.py` lines 267-268
- Cause: Sequential waits; no early exit if content loads faster
- Improvement path: Use `page.wait_for_load_state("domcontentloaded", timeout=10)` then `page.wait_for_selector(..., timeout=5)` with conditional logic

**ElevenLabs API Called for Every Tweet/Story:**
- Problem: Each video generation calls ElevenLabs TTS API independently. No caching of identical text.
- Files: `main.py` calls `generate_tts()` for every tweet/story; `pipeline/tts.py` makes fresh API call every time
- Cause: No deduplication or in-memory cache
- Improvement path: Hash tweet text; check SQLite cache before calling API; reuse MP3 + timestamps for duplicate text

**Quality Check Calls Anthropic API for Every Generated Item:**
- Problem: Every story/tweet generated calls Claude Sonnet for quality check (high model cost). No early pass-through for obviously good content.
- Files: `formats/storytelling/quality.py`, `formats/tweets/quality.py`
- Cause: Always calls API even when content clearly passes
- Improvement path: Implement fast heuristic check first (length, character count, profanity filter); only call Claude if heuristic uncertain

**Subtitle ASS File Generated Before Duration Known:**
- Problem: `main.py` line 224 generates ASS subtitles based on timestamps JSON, but final video duration might not match TTS duration due to FFmpeg rounding.
- Files: `main.py` lines 220-224, `pipeline/overlay.py`
- Cause: Timing assumptions between modules
- Improvement path: Finalize video duration first, then regenerate subtitles if needed

## Fragile Areas

**Analysis Profiler JSON Generation Fragile:**
- Files: `analysis/profiler.py`
- Why fragile: Relies on Claude JSON parsing (lines 232-235) which can fail if model returns markdown-wrapped code. Falls back to `{"error": "invalid JSON"}` which then breaks downstream analysis expecting specific schema. No schema validation.
- Safe modification: Add JSON schema validation with `jsonschema` library; document expected keys; add unit tests for edge cases (empty channel, no transcripts)
- Test coverage: No unit tests for edge cases; only success path tested

**Tweet Renderer Playwright Timing Assumptions:**
- Files: `formats/tweets/renderer.py` lines 162-168
- Why fragile: Hard-coded page sizes (600×900 viewport with 3x scale) and 500ms wait assume network fast enough to load image URLs. If image URLs slow, screenshot captures incomplete page.
- Safe modification: Measure actual render time with `page.wait_for_load_state("networkidle")` instead of fixed wait; validate container rendered before screenshot
- Test coverage: No tests for slow image URLs; no timeout handling

**FFmpeg Filter Escaping Edge Cases:**
- Files: `formats/storytelling/assembler.py` _escape_filter_path() lines 130-140
- Why fragile: Handles colons and quotes but not commas. If subtitle path contains comma, filter string breaks. Platform-specific (Windows needs different escaping).
- Safe modification: Use FFmpeg's `-f srt` with direct file passing instead of -vf filter; validate path doesn't contain special chars; unit test various path formats
- Test coverage: No tests for edge case paths

**Twscrape Authentication Brittle:**
- Files: `formats/tweets/scraper.py` setup_account() call to twscrape library
- Why fragile: Delegates authentication entirely to external library which can fail if X.com changes selectors or behavior. No fallback if authentication fails mid-scrape.
- Safe modification: Add explicit auth validation after setup; implement session refresh; catch and handle X.com rate limits gracefully
- Test coverage: No integration tests; relies on manual account setup

## Scaling Limits

**SQLite Database Not Optimized for Concurrent Access:**
- Current capacity: Single database file at `data/pipeline.db` with WAL mode. Concurrent writes serialized; reads block on writes.
- Limit: ~100-200 simultaneous queries before noticeable slowdown; batch operations like upserting 1000 videos lock for seconds
- Impact: If multiple analysis processes run in parallel, contention for database lock causes delays
- Scaling path: Migrate to PostgreSQL for concurrent access; or use connection pooling; implement batch operation coalescing

**Playwright Browser Resource Exhaustion:**
- Current capacity: Single browser instance per scrape operation. Typical memory: 100-200MB per browser.
- Limit: Running 10+ concurrent tweet scrapes opens 10+ browser instances = 1-2GB RAM, browser crashes on memory limits
- Impact: Batch operations with --count 20+ may OOM
- Scaling path: Implement browser pool (reuse 3-5 browsers); close idle browsers; add memory monitoring

**ElevenLabs API Rate Limits Not Handled:**
- Current capacity: ElevenLabs allows ~50 requests/minute per account
- Limit: Generating 100 videos with TTS calls = 100 API requests. With 3 retries, can hit 200+ calls. Rate limit errors return 429 status.
- Impact: Batch generation stalls if rate limit hit mid-process; no recovery except manual restart
- Scaling path: Implement token bucket rate limiter in `pipeline/tts.py`; queue requests with exponential backoff; cache TTS output

**YouTube API Quota (10k units/day):**
- Current capacity: fetch_channel() uses ~100 units (playlist pagination + video details). 20 channels = 2000 units. Visual analysis adds frame extraction (local, no API cost).
- Limit: 10 concurrent analyses exhaust quota quickly; no queuing
- Impact: Quota errors cause analysis to fail mid-process
- Scaling path: Track API usage in database; implement quota checking before calls; batch operations across days

## Dependencies at Risk

**yt-dlp Version Fragility:**
- Risk: YouTube shorts format changes frequently. yt-dlp tracks these but sometimes falls behind (weeks of lag). Version pinning prevents automatic fixes.
- Impact: Visual analysis may fail to download videos if format changes
- Migration plan: Update requirements.txt monthly; set up CI to test video downloads; implement fallback to youtube-dl if yt-dlp fails

**Playwright Version Incompatibility:**
- Risk: X.com updates DOM selectors (data-testid values). Playwright API changes between versions.
- Impact: Tweet scraper breaks on X.com DOM changes or Playwright updates. Selectors hard-coded (lines 111, 136-138 in scraper.py)
- Migration plan: Implement selector abstraction layer; version pin Playwright conservatively; add visual regression tests

**twscrape Maintenance:**
- Risk: External library with limited maintainers. X.com API scraping is cat-and-mouse game.
- Impact: If library falls behind, scraping fails. No alternative fallback.
- Migration plan: Evaluate official X API v2 (requires approval); implement backup scraper using raw Playwright; monitor GitHub for issues

**anthropic SDK Version Dependency:**
- Risk: SDK API changes between versions (backward incompatible). Model names (claude-haiku-4-5-20251001) may sunset.
- Impact: Code breaks if SDK updated or models deprecated
- Migration plan: Pin SDK version; implement compatibility layer for model selection; monitor Anthropic deprecation calendar

## Missing Critical Features

**No Graceful Shutdown on Interrupt:**
- Problem: CLI doesn't handle SIGINT (Ctrl+C) cleanly. Kills processes mid-operation leaving partial temp files, open database connections, unclosed browser processes.
- Blocks: Can't safely interrupt analysis/generation; cleanup requires manual intervention
- Fix approach: Implement signal handlers; track open resources; ensure finally blocks execute on interrupt

**No Resume/Checkpoint for Long Operations:**
- Problem: Analyzing 50 videos takes 2+ hours. If it fails at video 45, entire process restarts from video 1.
- Blocks: Can't iterate on analysis workflow; wastes API quota and time
- Fix approach: Save progress to database; implement --resume flag; skip already-analyzed videos

**No Output Validation Before Upload:**
- Problem: Code generates videos but doesn't validate they're playable before upload. Could upload broken MP4s.
- Blocks: Upload automation can't be built reliably
- Fix approach: Implement video validation (FFprobe check, playback test, duration check); warn if quality metrics below threshold

**No Batch Metadata Export:**
- Problem: After generating 10 videos, no easy way to export titles/descriptions/tags for bulk upload. Must manually create them.
- Blocks: Upload workflow incomplete
- Fix approach: Export generated content to CSV/JSON; include metadata in output folder; implement template system for titles

## Test Coverage Gaps

**No Tests for API Retry Logic:**
- What's not tested: exponential backoff, max attempts, specific error codes (429, 403)
- Files: `analysis/fetcher.py` _api_call(), `pipeline/tts.py` _call_with_retry(), `analysis/transcripts.py` _fetch_one()
- Risk: Silent failures if retry logic breaks; rate limits not handled correctly
- Priority: High — affects reliability in production

**No Tests for FFmpeg Command Building:**
- What's not tested: filter escaping edge cases, command syntax correctness, various input formats
- Files: `formats/storytelling/assembler.py` _build_ffmpeg_cmd(), `formats/tweets/assembler.py` _build_cmd()
- Risk: Commands may be invalid for certain input paths; silent failures if FFmpeg rejects args
- Priority: High — video generation is core feature

**No Integration Tests for Database Schema:**
- What's not tested: concurrent writes, transaction isolation, schema migrations (if schema changes)
- Files: `analysis/db.py`
- Risk: Data corruption on concurrent access; schema changes break in production
- Priority: Medium — single-process usage currently, but fragile

**No E2E Tests for Scraper DOM Selectors:**
- What's not tested: actual X.com navigation, selector correctness, X.com DOM structure changes
- Files: `formats/tweets/scraper.py` (all data-testid selectors)
- Risk: Selectors break silently when X.com updates DOM; not detected until runtime
- Priority: Critical — scraper is fragile to external changes

**No Tests for Claude JSON Parsing Edge Cases:**
- What's not tested: malformed JSON, missing keys, non-string values, markdown wrapping (```json ... ```)
- Files: `formats/storytelling/generator.py` _parse_json(), `formats/tweets/generator.py` (JSON parsing)
- Risk: Generation fails unpredictably; retry loop exhausted for non-retryable errors
- Priority: High — happens frequently in production

**No Stress Tests for Batch Operations:**
- What's not tested: generating 100+ videos, memory usage over time, resource cleanup
- Files: `main.py` generate command with --count 50+
- Risk: OOM errors, resource leaks surface only at scale; not caught in development
- Priority: Medium — low frequency but high impact

---

*Concerns audit: 2026-03-11*
