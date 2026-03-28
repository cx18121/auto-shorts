---
phase: quick-260315-tsy
plan: "01"
subsystem: video-assembly
tags: [ffmpeg, audio-speed, background-music, storytelling, tweets]
dependency_graph:
  requires: []
  provides: [1.3x-playback-speed, background-music-mixing, full-screen-only-layout]
  affects: [formats/storytelling/assembler.py, formats/tweets/assembler.py, main.py]
tech_stack:
  added: []
  patterns: [filter_complex-with-amix, stream_loop-for-music]
key_files:
  created: []
  modified:
    - formats/storytelling/assembler.py
    - formats/tweets/assembler.py
    - main.py
decisions:
  - music-path-none-falls-back-to-af: When no music files exist, fall back to simple -af (or -vf/-af) approach; filter_complex only used when music present
  - adjusted-duration-for-tweets: tweets assembler computes adjusted_duration = duration / AUDIO_SPEED so video length matches sped-up audio
  - assemble-split-video-kept: assemble_split_video stays in assembler.py for potential future use; only the call sites in main.py are removed
metrics:
  duration: "~5 minutes"
  completed: "2026-03-16T02:07:16Z"
  tasks_completed: 3
  files_modified: 3
---

# Phase quick-260315-tsy Plan 01: Speed Up Videos, Remove Reddit Post Overlay, Add Background Music Summary

**One-liner:** Bumped both assemblers to 1.3x playback speed, wired in assets/music/ mixing via filter_complex, and removed the split-screen Reddit-post overlay code path from main.py.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Increase speed and add music to storytelling assembler | a3c1099 | formats/storytelling/assembler.py |
| 2 | Increase speed and add music to tweets assembler | 2575d5d | formats/tweets/assembler.py |
| 3 | Remove split-screen from all call sites in main.py | 91cc54a | main.py |

## What Was Built

### Task 1 — Storytelling assembler
- `AUDIO_SPEED` bumped from 1.15 to 1.3
- Added `import random` and `_pick_music_file()` helper that globs `assets/music/` for `*.mp3`, `*.wav`, `*.m4a` files and returns a random choice or `None`
- `_build_ffmpeg_cmd` gains optional `music_path: Path | None = None`; when a file is provided, uses `-filter_complex` with `amix=inputs=2:duration=first` at `volume=0.08` for music; falls back to `-vf`/`-af` otherwise
- `assemble_video` calls `_pick_music_file()` and passes result; logs a warning when no music is found

### Task 2 — Tweets assembler
- Added `AUDIO_SPEED = 1.3` and `_AUDIO_VOLUME = "1.5"` constants
- Added `_pick_music_file()` (same logic as storytelling)
- `assemble_tweet_video` now computes `adjusted_duration = duration_seconds / AUDIO_SPEED` and uses that for both the `-t` trim and `total_frames`
- `_build_cmd` gains optional `music_path`; with music uses `filter_complex` combining zoompan video filter with amix audio; without music uses `-vf zoompan` + `-af atempo+volume`

### Task 3 — main.py call sites
- Removed `post_meta={...}` from all three `_run_storytelling_pipeline` call sites (lines ~302, ~422, ~1104)
- Removed `post_meta: dict | None = None` parameter from `_run_storytelling_pipeline` signature
- Removed dead `from formats.storytelling.assembler import assemble_split_video` import
- Removed entire `if post_meta:` branch (Reddit post render + split-screen assembly)
- Cleaned up `else:` keyword — full-screen path is now the unconditional body
- `assemble_split_video` function itself stays in assembler.py for potential future use

## Decisions Made

- **music-path-none falls back to -af**: When assets/music/ is empty, the assemblers log a warning and use the simpler `-vf`/`-af` flag pair instead of filter_complex. This avoids adding complexity when no music is configured.
- **adjusted_duration for tweets**: The tweets assembler must shrink the output video duration when audio is sped up. `adjusted_duration = duration_seconds / AUDIO_SPEED` was computed in `assemble_tweet_video` and passed through to `_build_cmd` to ensure the zoom animation and `-t` trim match the sped-up audio length.
- **assemble_split_video kept**: The function was not deleted from assembler.py. Only the call sites in main.py were removed. This preserves the option to re-enable split-screen later without re-implementing it.

## Deviations from Plan

None — plan executed exactly as written.

## Test Results

- Pre-existing failures unrelated to these changes: `test_config_channels` (importlib reload issue), `test_run_cycle` (missing `/tmp/output/final.txt`), `test_reddit_scraper`, `test_story_generator`
- All 3 automated verify commands passed
- 104 tests passing, failures confirmed pre-existing via stash check

## Self-Check: PASSED

- `formats/storytelling/assembler.py`: modified, `AUDIO_SPEED=1.3`, `_pick_music_file` importable
- `formats/tweets/assembler.py`: modified, `AUDIO_SPEED=1.3`, `_pick_music_file` importable
- `main.py`: parses OK, zero `post_meta` matches
- Commits: a3c1099, 2575d5d, 91cc54a all present in git log
