---
phase: quick
plan: 5
type: execute
wave: 1
depends_on: []
files_modified:
  - formats/storytelling/reddit_template.html
  - formats/storytelling/reddit_renderer.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Reddit post screenshot has transparent corners outside the rounded border"
    - "Post container retains its #1a1a1b background inside the border"
  artifacts:
    - path: "formats/storytelling/reddit_template.html"
      provides: "Transparent body background for rounded corner rendering"
      contains: "background: transparent"
    - path: "formats/storytelling/reddit_renderer.py"
      provides: "Playwright screenshot with omit_background for transparency"
      contains: "omit_background"
  key_links:
    - from: "formats/storytelling/reddit_renderer.py"
      to: "formats/storytelling/reddit_template.html"
      via: "Playwright renders template HTML"
      pattern: "reddit_template\\.html"
---

<objective>
Make the Reddit post screenshot corners truly rounded by rendering with a transparent background outside the post container's border-radius.

Purpose: Currently the body background (#1a1a1b) fills the rounded corners of .post-container, making them appear as black rectangles when composited over gameplay footage.
Output: Post screenshots with transparent corners that let gameplay show through.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@formats/storytelling/reddit_template.html
@formats/storytelling/reddit_renderer.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Enable transparent background in template and renderer</name>
  <files>formats/storytelling/reddit_template.html, formats/storytelling/reddit_renderer.py</files>
  <action>
Two changes needed:

1. In `formats/storytelling/reddit_template.html` line 12: Change `background: #1a1a1b;` to `background: transparent;` on the `body` rule. The `.post-container` already has its own `background: #1a1a1b` so the post interior stays dark.

2. In `formats/storytelling/reddit_renderer.py` line 139: Add `omit_background=True` to the `container.screenshot()` call so it becomes:
   ```python
   container.screenshot(path=str(tmp_png), omit_background=True)
   ```
   Without this flag, Playwright fills the screenshot background with white regardless of CSS. The `omit_background=True` parameter tells Playwright to preserve transparency in the PNG output.

Do NOT change line 141 (the fallback `page.screenshot`) -- that path only fires if the container selector fails, and full-page screenshots don't need transparency.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "
from formats.storytelling.reddit_renderer import render_reddit_post
from PIL import Image
import os, tempfile
out = os.path.join(tempfile.mkdtemp(), 'test_post.png')
render_reddit_post('Test body text.', 'Test Title', 'test', 42, out)
img = Image.open(out).convert('RGBA')
# Check top-left corner pixel (0,0) is transparent (outside rounded border)
r, g, b, a = img.getpixel((0, 0))
assert a == 0, f'Corner pixel should be transparent but alpha={a}'
print('PASS: corners are transparent')
"</automated>
  </verify>
  <done>Top-left corner pixel of rendered post PNG has alpha=0 (transparent). Post interior remains dark (#1a1a1b).</done>
</task>

</tasks>

<verification>
Render a test post and confirm corner pixels are transparent while interior pixels are opaque.
</verification>

<success_criteria>
- Reddit post screenshots have transparent corners outside the border-radius
- Post content area retains its dark background
- Gameplay footage shows through the rounded corners when composited
</success_criteria>

<output>
After completion, create `.planning/quick/5-make-borders-rounded-for-reddit-post-by-/5-SUMMARY.md`
</output>
