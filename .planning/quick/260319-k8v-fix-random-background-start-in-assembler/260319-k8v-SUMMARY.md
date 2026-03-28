---
phase: quick-260319-k8v
plan: "01"
subsystem: formats/storytelling
tags: [bugfix, ffmpeg, assembler, background-video]
dependency_graph:
  requires: []
  provides: [random-background-start-full-screen, random-background-start-split-screen]
  affects: [formats/storytelling/assembler.py]
tech_stack:
  added: []
  patterns: [random-bg-seek-before-stream-loop]
key_files:
  modified:
    - formats/storytelling/assembler.py
decisions:
  - "Short background clips (shorter than video duration) now get a random start via random.uniform(0, bg_duration) — the stream_loop wraps correctly regardless of start offset"
metrics:
  duration: "5 minutes"
  completed_date: "2026-03-19"
---

# Quick Task 260319-k8v: Fix Random Background Start in Assembler Summary

**One-liner:** Fixed three bugs so every storytelling video (full-screen and split-screen) seeks to a random point in the background clip before playback, eliminating the always-starts-at-0:00 repetitiveness.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix all three random-background-start bugs in assembler.py | 42e5d3a | formats/storytelling/assembler.py |

## What Was Built

Three bugs fixed in `formats/storytelling/assembler.py`:

**Bug A — Missing `import json`:** `_probe_video_duration` calls `json.loads()` but `json` was never imported. Every call raised a `NameError`, was caught by the `except` clause, and silently returned `0.0`. This meant `_random_bg_start` always returned `0.0` regardless of clip duration. Fixed by adding `import json` to the top of the file.

**Bug B — Short clips always started at 0:** When `bg_duration <= required_duration`, the function returned `0.0` unconditionally. Because the clip is `stream_loop`-ed, any start offset is safe — the video wraps seamlessly. Fixed by replacing the early return with `random.uniform(0, bg_duration)` so even short/looped clips get a random start.

**Bug C — Split-screen layout never randomized start:** `assemble_split_video` built the FFmpeg command without computing a background start offset, and `_build_split_ffmpeg_cmd` had no `-ss` flag. Fixed by computing `adjusted_duration` and calling `_random_bg_start` in `assemble_split_video`, adding a `bg_start: float = 0.0` parameter to `_build_split_ffmpeg_cmd`, and inserting `"-ss", str(bg_start)` before `-stream_loop` in the returned command list.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- [x] `formats/storytelling/assembler.py` exists and was modified
- [x] Commit 42e5d3a exists
- [x] All four automated AST/string verification checks pass
