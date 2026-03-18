---
phase: quick-260318-n9g
plan: 01
subsystem: video-assembly
tags: [bugfix, ffmpeg, tts, tweets, storytelling]
dependency_graph:
  requires: []
  provides: [full-narration-playback, tweet-speaker-attribution]
  affects: [formats/storytelling/assembler.py, formats/tweets/assembler.py, main.py]
tech_stack:
  added: []
  patterns: [ffmpeg-duration-buffer]
key_files:
  created: []
  modified:
    - formats/storytelling/assembler.py
    - formats/tweets/assembler.py
    - main.py
decisions:
  - "+0.5s buffer applied to adjusted_duration (not -shortest) — keeps deterministic clip length while preventing clipping"
  - "says: wording lowercase with colon, space before tweet text — matches natural speech cadence"
metrics:
  duration: "5min"
  completed: "2026-03-18T20:54:47Z"
  tasks_completed: 2
  files_modified: 3
---

# Quick Task 260318-n9g: Fix Tweet Videos Cutting Off at End and Add @username Says Intro — Summary

**One-liner:** Added +0.5s FFmpeg duration buffer to all 4 adjusted_duration sites and prepended "@username says:" to tweet TTS scripts.

## What Was Built

Two targeted fixes to the video assembly pipeline:

1. **Duration buffer** — `adjusted_duration = duration / AUDIO_SPEED` was fractionally too short after speed division, causing FFmpeg's `-t` to clip the final word of narration. Added `+ 0.5` to all four computation sites (3 in storytelling assembler, 1 in tweet assembler).

2. **Speaker attribution** — Tweet TTS narrations now begin with "@username says: " before the tweet text, giving viewers immediate context on who is speaking.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add +0.5s buffer to adjusted_duration in both assemblers | 41023b6 | formats/storytelling/assembler.py, formats/tweets/assembler.py |
| 2 | Prepend @username says: to tweet TTS text | 890cd65 | main.py |

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- formats/storytelling/assembler.py: 3 buffer locations confirmed (`grep -n '+ 0.5'`)
- formats/tweets/assembler.py: 1 buffer location confirmed
- main.py: 2 `says:` patterns confirmed at lines 594 and 643
- Both commits verified in git log
