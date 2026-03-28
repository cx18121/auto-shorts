---
phase: quick-fix
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - formats/storytelling/assembler.py
  - formats/storytelling/reddit_renderer.py
  - pipeline/overlay.py
  - main.py
autonomous: true
---

<objective>
1. Reddit post overlay with gameplay border visible around it (narrower post, ~940px)
2. Remove post padding — never pad, let gameplay show around short posts
3. Zoom out gameplay (fit instead of crop-to-fill)
4. Change subtitle font to Komika Axis
5. Add --no-audio flag to skip TTS for testing

</objective>

<tasks>

<task type="auto">
  <name>Task 1: Narrow post overlay, zoom out gameplay, remove padding, font change, --no-audio</name>
  <files>formats/storytelling/assembler.py, formats/storytelling/reddit_renderer.py, pipeline/overlay.py, main.py</files>
  <action>
  All changes in one atomic task:

  **assembler.py:**
  - Add _POST_W = 940 constant (narrower than 1080 canvas)
  - Change gameplay scale to use force_original_aspect_ratio=decrease + pad for zoom-out
  - Change post scale to 940 wide, overlay at x=(1080-940)/2=70

  **reddit_renderer.py:**
  - Remove padding logic entirely — never pad short posts
  - Change RENDER_WIDTH to 940 to match new _POST_W

  **overlay.py:**
  - Change font from "Nunito ExtraBold" to "Komika Axis"

  **main.py:**
  - Add --no-audio flag to generate subparser
  - When --no-audio: skip TTS, generate silent audio + dummy timestamps, assemble video with fixed 10s duration
  </action>
</task>

</tasks>
