---
phase: quick-3
plan: "01"
subsystem: video-assembly
tags: [fonts, subtitles, ffmpeg, ass]
dependency_graph:
  requires: []
  provides: [komika-axis-font, fontsdir-wiring, subtitle-bottom-position]
  affects: [formats/storytelling/assembler.py, pipeline/overlay.py]
tech_stack:
  added: []
  patterns: [fontsdir parameter in FFmpeg ass filter]
key_files:
  created:
    - assets/fonts/KomikaAxis.ttf
  modified:
    - formats/storytelling/assembler.py
    - pipeline/overlay.py
decisions:
  - Font named KomikaAxis.ttf (no spaces) to match FFmpeg font scanning behavior against "Komika Axis" fontname in ASS style
  - _FONTS_DIR constant placed at module level in assembler.py so both builder functions share it without duplication
  - MarginV=150 chosen to give 150px clearance from the bottom edge on the 1920-high canvas
metrics:
  duration: "3 minutes"
  completed_date: "2026-03-13"
  tasks_completed: 2
  files_changed: 3
---

# Phase quick-3 Plan 01: Install Komika Axis Font and Wire fontsdir Summary

**One-liner:** Installed Komika Axis TTF font and wired FFmpeg's `fontsdir` parameter so subtitles render in the correct comic-style font at the bottom of the frame.

## What Was Built

- `assets/fonts/KomikaAxis.ttf` — Komika Axis font file (54 KB) downloaded from dafont.com
- `formats/storytelling/assembler.py` — `_FONTS_DIR` module constant + `fontsdir=` appended to the `ass` filter in both `_build_ffmpeg_cmd` and `_build_split_ffmpeg_cmd`
- `pipeline/overlay.py` — ASS style `Alignment` changed from `5` (centre) to `2` (bottom-centre); `MarginV` changed from `0` to `150`

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Install Komika Axis font and wire fontsdir in assembler | ea1e9dd | assets/fonts/KomikaAxis.ttf, formats/storytelling/assembler.py |
| 2 | Lower subtitle vertical position | ace8c5e | pipeline/overlay.py |

## Verification

All checks passed:

- `KomikaAxis.ttf` present at `assets/fonts/KomikaAxis.ttf`, 53996 bytes (> 10 KB)
- `fontsdir=` appears in both `_build_ffmpeg_cmd` (line 118) and `_build_split_ffmpeg_cmd` (line 320)
- ASS style contains `,2,40,40,150,1` confirming Alignment=2, MarginV=150
- Both modules import without errors

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] `assets/fonts/KomikaAxis.ttf` exists (53996 bytes)
- [x] Commit ea1e9dd exists
- [x] Commit ace8c5e exists
- [x] `fontsdir` appears on lines 118 and 320 of assembler.py
- [x] overlay.py style line contains `,2,40,40,150,1`
