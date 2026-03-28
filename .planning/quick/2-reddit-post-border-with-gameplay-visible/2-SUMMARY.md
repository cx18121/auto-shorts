# Quick Task 2: Post Border, Zoom Out, Font Change, --no-audio

**Completed:** 2026-03-12
**Commit:** 98fdecc

## Changes Made

### assembler.py
- Added `_POST_W = 940` — Reddit post narrower than 1080px canvas (70px gameplay border each side)
- Overlay centered at x=70, y=40 instead of full-width
- Gameplay uses `force_original_aspect_ratio=decrease` + `pad` — zoomed out (fit, not crop)

### reddit_renderer.py
- `RENDER_WIDTH` changed from 1080 to 940 to match `_POST_W`
- Removed all padding logic — short posts no longer get #1a1a1b padding
- Changed image mode to RGBA for transparency support

### overlay.py
- Font changed from "Nunito ExtraBold" to "Komika Axis"

### main.py
- Added `--no-audio` flag to `generate` subcommand
- `_generate_silent_audio()` helper: generates 10s silent MP3 + dummy timestamps via FFmpeg
- `no_audio` threaded through: `cmd_generate` → `_generate_storytelling` / `_generate_storytelling_from_backlog` → `_run_storytelling_pipeline`

## Files Modified
- `formats/storytelling/assembler.py`
- `formats/storytelling/reddit_renderer.py`
- `pipeline/overlay.py`
- `main.py`
