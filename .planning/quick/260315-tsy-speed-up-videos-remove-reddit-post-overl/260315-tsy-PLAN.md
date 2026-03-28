---
phase: quick-260315-tsy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - formats/storytelling/assembler.py
  - formats/tweets/assembler.py
  - main.py
autonomous: true
requirements:
  - speed-up-videos
  - remove-reddit-post-overlay
  - add-background-music

must_haves:
  truths:
    - "Both assemblers produce videos at ~1.3x playback speed"
    - "Storytelling videos are full-screen gameplay with subtitles — no Reddit post image"
    - "Background music plays at low volume under narration in both assemblers (or logs a warning and skips if no music files present)"
  artifacts:
    - path: "formats/storytelling/assembler.py"
      provides: "AUDIO_SPEED=1.3, music mixing in _build_ffmpeg_cmd"
    - path: "formats/tweets/assembler.py"
      provides: "atempo=1.3 in audio filter, adjusted duration, music mixing in _build_cmd"
    - path: "main.py"
      provides: "post_meta removed from all three _run_storytelling_pipeline call sites"
  key_links:
    - from: "main.py _run_storytelling_pipeline"
      to: "assemble_video"
      via: "post_meta=None always (no split-screen path taken)"
    - from: "_build_ffmpeg_cmd / _build_cmd"
      to: "assets/music/ random file"
      via: "amix filter with volume=0.08 on music stream"
---

<objective>
Speed up videos, remove Reddit post overlay, and add background music to both assemblers.

Purpose: Faster narration is more engaging for Shorts. Full-screen gameplay without the Reddit post overlay simplifies the layout. Background music adds production polish.
Output: Updated assembler.py (storytelling), assembler.py (tweets), main.py with no split-screen calls.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Increase speed and add music to storytelling assembler</name>
  <files>formats/storytelling/assembler.py</files>
  <action>
Make two changes to formats/storytelling/assembler.py:

**1. Increase AUDIO_SPEED from 1.15 to 1.3** (line 31):
```python
AUDIO_SPEED  = 1.3           # 30% faster playback
```

**2. Add background music mixing to `_build_ffmpeg_cmd`.**

Add a helper `_pick_music_file()` at module level (below the constants) that:
- Globs `assets/music/` (relative to the project root, i.e. `Path(__file__).resolve().parent.parent.parent / "assets" / "music"`) for `*.mp3`, `*.wav`, `*.m4a` files
- Returns a random one if any exist, else returns `None`
- Uses `import random` (add to imports at top)

Modify `_build_ffmpeg_cmd` to accept an optional `music_path: Path | None = None` parameter and wire it up:

When `music_path` is not None, add a third input (`-i str(music_path)`) and replace the simple `-af` with a `-filter_complex` that:
- Streams the music looped (use `-stream_loop -1` on its input flag position, see below)
- Mixes narration and music: `[1:a]atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}[narr];[2:a]volume=0.08[mus];[narr][mus]amix=inputs=2:duration=first[aout]`
- Maps `[aout]` as the audio output

When `music_path` is None, keep the existing `-af` approach unchanged.

Update `assemble_video` to call `_pick_music_file()` and pass it to `_build_ffmpeg_cmd`.

FFmpeg input ordering when music is present:
```
-stream_loop -1 -i str(bg)        # input 0: background video (looped)
-i str(audio)                     # input 1: narration
-stream_loop -1 -i str(music)     # input 2: music (looped)
```
Note: `-stream_loop -1` must appear immediately before the `-i` it applies to. The existing command already has `-stream_loop -1 -i str(bg)` — add `-stream_loop -1` before the music `-i` in the same list.

The `-filter_complex` replaces both `-vf` and `-af`. The video filter chain stays the same (`crop=ih*9/16:ih,scale=1080:1920,ass=...`). Build it as:
```
vf_chain = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass_escaped}:fontsdir={fonts_escaped}"
fc = f"[0:v]{vf_chain}[vout];[1:a]atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}[narr];[2:a]volume=0.08[mus];[narr][mus]amix=inputs=2:duration=first[aout]"
```
Then use `-filter_complex fc`, `-map [vout]`, `-map [aout]` (remove the old `-vf`, `-af`, `-map 0:v`, `-map 1:a`).

When no music file is found, log a warning: `logger.warning("No music files in assets/music/ — skipping background music")` and fall back to the non-music command path.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "from formats.storytelling.assembler import AUDIO_SPEED, _pick_music_file, _build_ffmpeg_cmd; assert AUDIO_SPEED == 1.3, f'Expected 1.3, got {AUDIO_SPEED}'; print('AUDIO_SPEED OK:', AUDIO_SPEED); print('music picker OK:', _pick_music_file())"</automated>
  </verify>
  <done>AUDIO_SPEED is 1.3. _pick_music_file() is importable and returns a Path or None. _build_ffmpeg_cmd accepts music_path parameter.</done>
</task>

<task type="auto">
  <name>Task 2: Increase speed and add music to tweets assembler</name>
  <files>formats/tweets/assembler.py</files>
  <action>
Make three changes to formats/tweets/assembler.py:

**1. Add AUDIO_SPEED constant** near the top with the other constants:
```python
AUDIO_SPEED  = 1.3           # 30% faster playback
_AUDIO_VOLUME = "1.5"        # 50% volume boost
```

**2. Adjust duration for speed** in `assemble_tweet_video`: the audio is sped up by atempo, so the video duration must shrink by the same factor. After probing duration, compute:
```python
adjusted_duration = duration_seconds / AUDIO_SPEED
total_frames = int(adjusted_duration * _FPS)
```
Pass `adjusted_duration` as the trim duration and use it for `total_frames` in `_build_cmd`. Update the logger to log the adjusted duration.

**3. Add background music mixing to `_build_cmd`.**

Add `_pick_music_file()` (same logic as storytelling assembler — glob `assets/music/`, return random or None). Add `import random` if not present.

Modify `_build_cmd` to accept optional `music_path: Path | None = None`.

When `music_path` is provided, build a `-filter_complex` that combines the zoompan video filter with audio mixing:
```
fc = f"[0:v]{zoompan}[vout];[1:a]atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}[narr];[2:a]volume=0.08[mus];[narr][mus]amix=inputs=2:duration=first[aout]"
```
FFmpeg input ordering:
```
-loop 1 -i str(img)               # input 0: static image
-i str(audio)                     # input 1: narration
-stream_loop -1 -i str(music)     # input 2: music (looped)
```
Use `-filter_complex fc`, `-map [vout]`, `-map [aout]` and remove `-vf`, `-map 0:v`, `-map 1:a`.

When no music file, fall back to existing approach but add `-af f"atempo={AUDIO_SPEED},volume={_AUDIO_VOLUME}"` (replacing the current command which has no audio filter at all).

Update `assemble_tweet_video` to call `_pick_music_file()` and pass it to `_build_cmd`.

When no music file is found, log: `logger.warning("No music files in assets/music/ — skipping background music")`.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "from formats.tweets.assembler import AUDIO_SPEED, _pick_music_file, _build_cmd; assert AUDIO_SPEED == 1.3, f'Expected 1.3, got {AUDIO_SPEED}'; print('AUDIO_SPEED OK:', AUDIO_SPEED); print('music picker OK:', _pick_music_file())"</automated>
  </verify>
  <done>AUDIO_SPEED is 1.3. _pick_music_file() is importable. _build_cmd accepts music_path parameter. No audio filter was missing before — now atempo+volume applied regardless of music presence.</done>
</task>

<task type="auto">
  <name>Task 3: Remove split-screen from all call sites in main.py</name>
  <files>main.py</files>
  <action>
In main.py, `_run_storytelling_pipeline` is called with `post_meta=...` at three locations. Remove the `post_meta` argument from all three calls so they always use the full-screen path.

The three call sites are around lines 302, 422, and 1104. For each, remove the `post_meta={...}` keyword argument block entirely. After this change all three calls look like:
```python
video_path = _run_storytelling_pipeline(
    story["story_text"], background,
    no_audio=no_audio,   # (only present on the calls that have it)
)
```

Also remove the now-dead `from formats.storytelling.assembler import assemble_split_video` import inside `_run_storytelling_pipeline` (line 502) and the entire `if post_meta:` branch (lines 518-545), leaving only the `else` block (the full-screen path) as the unconditional body. Clean up the `else:` keyword so it's just the straight-line code.

Do NOT remove the `assemble_split_video` function from assembler.py — it can stay for potential future use.

The `_run_storytelling_pipeline` signature should lose the `post_meta` parameter entirely after this change. The docstring should be updated to drop the "If post_meta is provided, uses split-screen layout" sentence.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "import ast, sys; ast.parse(open('main.py').read()); print('main.py parses OK')" && grep -c "post_meta" main.py | xargs -I{} sh -c 'if [ {} -eq 0 ]; then echo "post_meta fully removed OK"; else echo "FAIL: post_meta still present {} times"; exit 1; fi'</automated>
  </verify>
  <done>main.py parses without error. grep for "post_meta" returns 0 matches. _run_storytelling_pipeline no longer has a split-screen code path.</done>
</task>

</tasks>

<verification>
Run all three automated verify commands. Then do a quick import check:
```bash
cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "
from formats.storytelling.assembler import AUDIO_SPEED as SA
from formats.tweets.assembler import AUDIO_SPEED as TA
assert SA == 1.3 and TA == 1.3
print('Both assemblers: AUDIO_SPEED =', SA)
import ast; ast.parse(open('main.py').read())
print('main.py valid')
"
```
</verification>

<success_criteria>
- AUDIO_SPEED = 1.3 in both assemblers
- Background music mixed at volume=0.08 when music files present; graceful skip (warning log) when assets/music/ is empty
- No `post_meta` references remain in main.py
- main.py parses without syntax errors
- All existing tests still pass: `python -m pytest tests/ -x -q`
</success_criteria>

<output>
After completion, create `.planning/quick/260315-tsy-speed-up-videos-remove-reddit-post-overl/260315-tsy-SUMMARY.md`
</output>
