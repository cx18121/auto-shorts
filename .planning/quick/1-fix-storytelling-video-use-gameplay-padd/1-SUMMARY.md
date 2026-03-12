# Quick Task 1: Fix Split-Screen Video Layout + Audio/Subtitle Improvements

**Completed:** 2026-03-12
**Commit:** 6d4c9aa

## Changes Made

### assembler.py
- Rewrote split-screen layout: gameplay fills entire 1080x1920 canvas as background
- Reddit post overlaid on upper 960px using `overlay` filter (replaced `vstack`)
- Added `subtitles_path` parameter to `assemble_split_video` — ASS subtitles burned in
- Added audio speed (1.15x via `atempo`) and volume (1.5x) boost to both assembly modes
- Replaced `_TOP_H`/`_BOT_H` constants with `_POST_H = 960`

### overlay.py
- Subtitles now display in ALL CAPS
- Font size increased from 88pt to 120pt
- Punctuation stripped from subtitle display text
- Added `speed_factor` parameter to `generate_ass` — scales timestamps for sped-up audio
- Sentences still break correctly (hard break on `.!?` preserved)

### main.py
- Split-screen branch now generates ASS subtitles via `generate_ass` before assembly
- Passes `speed_factor=AUDIO_SPEED` and `subtitles_path` to assembler
- Step numbering updated to [1/4] through [4/4]

### reddit_renderer.py
- Updated to use `_POST_H` instead of removed `_TOP_H` constant

## Files Modified
- `formats/storytelling/assembler.py`
- `pipeline/overlay.py`
- `main.py`
- `formats/storytelling/reddit_renderer.py`
