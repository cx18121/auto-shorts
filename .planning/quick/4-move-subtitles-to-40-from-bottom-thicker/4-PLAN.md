---
phase: quick-4
description: "Move subtitles to 40% from bottom, thicker text border"
plans: 1
---

# Quick Task 4: Move subtitles to 40% from bottom, thicker text border

## Plan 01: Update ASS style values

### Task 1: Adjust MarginV and Outline in overlay.py
- **files:** pipeline/overlay.py
- **action:** Change MarginV from 150 to 768 (40% of 1920px), Outline from 4 to 6
- **verify:** Values updated in _ASS_STYLES string
- **done:** Subtitles positioned at 40% from bottom with thicker border
