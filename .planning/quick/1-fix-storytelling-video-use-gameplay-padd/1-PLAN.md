---
phase: quick-fix
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - formats/storytelling/assembler.py
  - main.py
autonomous: true
requirements: [FIX-SPLIT-01, FIX-SPLIT-02, FIX-SPLIT-03]
must_haves:
  truths:
    - "Split-screen video shows gameplay filling the entire 1080x1920 canvas as background"
    - "Reddit post image is overlaid on the upper portion over the gameplay, not in a separate black region"
    - "ASS subtitles are burned into the split-screen video output"
    - "More gameplay is visible (less aggressive bottom crop)"
  artifacts:
    - path: "formats/storytelling/assembler.py"
      provides: "Rewritten _build_split_ffmpeg_cmd with overlay layout and subtitle support"
      contains: "overlay"
    - path: "formats/storytelling/assembler.py"
      provides: "Updated assemble_split_video accepting subtitles_path"
      contains: "subtitles_path"
    - path: "main.py"
      provides: "Caller passes subtitles_path to assemble_split_video"
      contains: "subtitles_path"
  key_links:
    - from: "main.py"
      to: "formats/storytelling/assembler.py"
      via: "assemble_split_video call with subtitles_path kwarg"
      pattern: "assemble_split_video.*subtitles_path"
    - from: "formats/storytelling/assembler.py"
      to: "FFmpeg filter graph"
      via: "overlay filter instead of vstack, plus ass= subtitle burn"
      pattern: "overlay|ass="
---

<objective>
Fix the split-screen storytelling video layout so gameplay fills the entire 1080x1920 canvas as background, with the Reddit post overlaid on top, subtitles burned in, and less aggressive gameplay cropping.

Purpose: Current split-screen has ugly dark/black areas from the Reddit post background taking up the top 1060px, subtitles are completely missing, and gameplay is over-cropped to only 860px.
Output: Updated assembler.py with overlay-based layout and subtitle support, updated main.py caller.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@formats/storytelling/assembler.py
@main.py (lines 417-469 — _run_storytelling_pipeline function)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite split-screen FFmpeg filter to use gameplay as full background with Reddit overlay and subtitles</name>
  <files>formats/storytelling/assembler.py</files>
  <action>
Rewrite `_build_split_ffmpeg_cmd` and update `assemble_split_video` with the following changes:

1. **Add `subtitles_path` parameter** to `assemble_split_video` (as `str | None = None`). Add file-existence check for it when provided. Pass it through to `_build_split_ffmpeg_cmd`.

2. **Add `subs` parameter** to `_build_split_ffmpeg_cmd` (as `Path | None = None`).

3. **Rewrite the filter graph** in `_build_split_ffmpeg_cmd`. The new layout:
   - **Gameplay as full background**: Scale and center-crop gameplay to fill entire 1080x1920 canvas. Use: `[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bg];`
   - **Reddit post overlay on top portion**: Scale post image to 1080 wide, then crop a scrolling window of height `_POST_H` (use 960 — roughly half the screen, leaving more gameplay visible). Overlay it at position `(0, 40)` (slight top padding) on the background: `[bg][post]overlay=0:40[comp];`
   - **Burn ASS subtitles**: If `subs` is provided, append `ass={escaped_path}` filter to the composited output. If not provided, skip the subtitle filter.
   - The scroll expression stays the same concept: `max(0,(in_h-{_POST_H}))*t/{duration}` but uses the new `_POST_H` value.

4. **Remove old constants** `_TOP_H = 1060` and `_BOT_H = 860`. Replace with `_POST_H = 960` (the height of the Reddit post overlay region). Keep `_CANVAS_W = 1080` and `_CANVAS_H = 1920`.

5. **Update docstrings** on both functions to reflect the new overlay-based layout.

6. **Update the module docstring** at top to describe the new layout: "Split-screen: full gameplay background + scrolling Reddit post overlaid on upper portion + burned-in ASS subtitles"

The final filter graph string should look approximately like:
```
[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bg];
[1:v]scale=1080:-1,crop=1080:{_POST_H}:0:'{scroll_y}'[post];
[bg][post]overlay=0:40[comp];
[comp]ass={escaped_path}[out]
```
When no subtitles: skip the ass= line and use `[comp]` as final output (rename to `[out]` or map directly).

The return command list stays the same structure: `-filter_complex`, `-map [out]`, `-map 2:a` (audio is input 2).
  </action>
  <verify>
    <automated>python -c "from formats.storytelling.assembler import assemble_split_video; import inspect; sig = inspect.signature(assemble_split_video); assert 'subtitles_path' in sig.parameters, 'missing subtitles_path param'; print('OK: signature has subtitles_path')"</automated>
  </verify>
  <done>
    - assemble_split_video accepts subtitles_path parameter
    - _build_split_ffmpeg_cmd uses overlay filter (not vstack) with gameplay filling 1080x1920
    - Reddit post overlay is 960px tall (not 1060px), leaving more gameplay visible
    - ASS subtitles are burned in when subtitles_path is provided
    - Old _TOP_H/_BOT_H constants replaced with _POST_H
  </done>
</task>

<task type="auto">
  <name>Task 2: Update caller in main.py to generate and pass subtitles to split-screen assembler</name>
  <files>main.py</files>
  <action>
In `_run_storytelling_pipeline` (around line 433), update the `if post_meta:` branch to:

1. **Generate ASS subtitles** before calling `assemble_split_video`. Add subtitle generation step between TTS and assembly:
   ```python
   logger.info("[2/4] Rendering Reddit post...")
   post_img = render_reddit_post(...)

   logger.info("[3/4] Subtitles...")
   subs = generate_ass(tts["timestamps_path"], str(workdir / "subtitles.ass"))

   logger.info("[4/4] Assembling split-screen...")
   out = assemble_split_video(
       background_path=background,
       audio_path=tts["audio_path"],
       post_image_path=post_img,
       subtitles_path=subs,
       output_path=str(workdir / "final.mp4"),
       duration_seconds=tts["duration_seconds"],
   )
   ```

2. Update the step numbering in log messages from `[1/3]`, `[2/3]`, `[3/3]` to `[1/4]`, `[2/4]`, `[3/4]`, `[4/4]` for the split-screen branch.

3. Ensure `generate_ass` is already imported at the call site. It is used in the `else` branch (line 456) so it should already be in scope — verify the import exists (it comes from `pipeline.overlay`). The import `from pipeline.overlay import generate_ass` should already be present earlier in the function or at top of the file — check and add if missing.
  </action>
  <verify>
    <automated>python -c "
from unittest.mock import patch, MagicMock
import main
# Verify the function signature and code path references subtitles
import inspect
src = inspect.getsource(main._run_storytelling_pipeline)
assert 'subtitles_path' in src, 'caller does not pass subtitles_path'
assert 'generate_ass' in src, 'caller does not generate subtitles in split path'
print('OK: main.py passes subtitles to split-screen assembler')
"</automated>
  </verify>
  <done>
    - Split-screen branch in _run_storytelling_pipeline generates ASS subtitles via generate_ass
    - subtitles_path is passed to assemble_split_video
    - Log messages reflect correct step count (4 steps)
  </done>
</task>

</tasks>

<verification>
1. `python -c "from formats.storytelling.assembler import assemble_split_video, _build_split_ffmpeg_cmd"` imports without error
2. The filter graph in _build_split_ffmpeg_cmd contains "overlay" (not "vstack")
3. assemble_split_video signature includes subtitles_path parameter
4. main.py split-screen branch generates subtitles and passes them to assembler
</verification>

<success_criteria>
- Gameplay fills entire 1080x1920 as background (no black/dark areas)
- Reddit post is overlaid on upper portion (~960px) over gameplay
- ASS subtitles are burned into split-screen videos
- Callers updated to pass subtitle paths
- No regressions to the original full-screen assemble_video path
</success_criteria>

<output>
After completion, create `.planning/quick/1-fix-storytelling-video-use-gameplay-padd/1-SUMMARY.md`
</output>
