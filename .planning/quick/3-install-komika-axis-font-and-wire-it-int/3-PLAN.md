---
phase: quick-3
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - assets/fonts/KomikaAxis.ttf
  - formats/storytelling/assembler.py
  - pipeline/overlay.py
autonomous: true
requirements: [QUICK-3]
must_haves:
  truths:
    - "FFmpeg finds and renders Komika Axis font in subtitles"
    - "Subtitles appear in lower portion of the video frame"
  artifacts:
    - path: "assets/fonts/KomikaAxis.ttf"
      provides: "Komika Axis font file"
    - path: "formats/storytelling/assembler.py"
      provides: "fontsdir parameter on all ass filter invocations"
    - path: "pipeline/overlay.py"
      provides: "Lowered MarginV in ASS style definition"
  key_links:
    - from: "formats/storytelling/assembler.py"
      to: "assets/fonts/"
      via: "fontsdir parameter in FFmpeg ass filter"
      pattern: "fontsdir="
---

<objective>
Install the Komika Axis font file into assets/fonts/, wire FFmpeg's ass filter to use fontsdir so it can find the font, and lower the subtitle position by increasing MarginV in the ASS style.

Purpose: Subtitles currently fall back to a default font because FFmpeg cannot find Komika Axis. Subtitles also sit at vertical center — they should be lower.
Output: Font file installed, assembler updated, overlay MarginV adjusted.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@pipeline/overlay.py
@formats/storytelling/assembler.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Install Komika Axis font and wire fontsdir in assembler</name>
  <files>assets/fonts/KomikaAxis.ttf, formats/storytelling/assembler.py</files>
  <action>
1. Download Komika Axis font into assets/fonts/. The font is freely available. Use wget or curl to fetch the TTF file. Name it `KomikaAxis.ttf` (no spaces — matches the "Komika Axis" fontname in the ASS style when FFmpeg scans the directory). If the download source provides a ZIP, extract the TTF and clean up.

   Fallback sources (try in order):
   - https://dl.dafont.com/dl/?f=komika_axis — downloads a ZIP containing the TTF
   - Search for another free source if the above fails

2. In `formats/storytelling/assembler.py`, resolve the fonts directory path and pass it to the ass filter in both places:

   a. Near the top of the file (after the imports), add a module-level constant:
      ```python
      _FONTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "assets" / "fonts")
      ```

   b. In `_build_ffmpeg_cmd` (line ~114), change the vf line from:
      ```python
      vf = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass_escaped}"
      ```
      to:
      ```python
      fonts_escaped = _escape_filter_path(_FONTS_DIR)
      vf = f"crop=ih*9/16:ih,scale=1080:1920,ass={ass_escaped}:fontsdir={fonts_escaped}"
      ```

   c. In `_build_split_ffmpeg_cmd` (line ~315), change:
      ```python
      fc_parts.append(f"[comp]ass={ass_escaped}[out]")
      ```
      to:
      ```python
      fonts_escaped = _escape_filter_path(_FONTS_DIR)
      fc_parts.append(f"[comp]ass={ass_escaped}:fontsdir={fonts_escaped}[out]")
      ```
  </action>
  <verify>
    <automated>python3 -c "from pathlib import Path; p = Path('assets/fonts/KomikaAxis.ttf'); assert p.exists() and p.stat().st_size > 10000, f'Font missing or too small: {p}'; print('Font OK:', p.stat().st_size, 'bytes')" && python3 -c "import formats.storytelling.assembler as a; assert 'fontsdir' in str(a._build_ffmpeg_cmd.__code__.co_consts) or True; print('Module imports OK')" && grep -c 'fontsdir' formats/storytelling/assembler.py | xargs -I{} test {} -ge 2 && echo "fontsdir appears in both functions"</automated>
  </verify>
  <done>KomikaAxis.ttf exists in assets/fonts/ (file size > 10KB). Both _build_ffmpeg_cmd and _build_split_ffmpeg_cmd include fontsdir= pointing to assets/fonts/.</done>
</task>

<task type="auto">
  <name>Task 2: Lower subtitle vertical position</name>
  <files>pipeline/overlay.py</files>
  <action>
In pipeline/overlay.py line 176, the ASS style currently has `MarginV=0` with `Alignment=5` (center).

Change the style to lower subtitles into the bottom third of the screen:
- Change Alignment from 5 to 2 (bottom-center in ASS numpad alignment)
- Set MarginV to 150 (pixels from bottom edge on the 1920-high canvas — places text comfortably above the very bottom)

On line 176, change:
```python
f"5,40,40,0,1\n"    # Alignment=5 (centre), MarginL/R=40, MarginV=0, Encoding=1
```
to:
```python
f"2,40,40,150,1\n"  # Alignment=2 (bottom-centre), MarginL/R=40, MarginV=150, Encoding=1
```

This places subtitles at the bottom of the frame with 150px margin, which is the standard position for short-form video subtitles (visible but not covering critical content).
  </action>
  <verify>
    <automated>python3 -c "import pipeline.overlay as o; style = o._ASS_STYLES; assert ',2,40,40,150,1' in style, f'Expected bottom-centre alignment with MarginV=150, got: {style.split(chr(10))[2]}'; print('Style OK: Alignment=2, MarginV=150')"</automated>
  </verify>
  <done>ASS style uses Alignment=2 (bottom-centre) and MarginV=150. Subtitles render in the lower portion of the 1080x1920 canvas.</done>
</task>

</tasks>

<verification>
Generate an ASS file and inspect the style line:
```bash
python3 -c "
import pipeline.overlay as o
style = o._ASS_STYLES
print(style)
assert 'Komika Axis' in style
assert ',2,40,40,150,1' in style
print('ASS style verified')
"
```

Confirm fontsdir wiring:
```bash
grep 'fontsdir' formats/storytelling/assembler.py
```
Should show two occurrences (one in each build function).

Confirm font file:
```bash
ls -la assets/fonts/KomikaAxis.ttf
```
</verification>

<success_criteria>
- KomikaAxis.ttf present in assets/fonts/ (valid TTF, >10KB)
- Both FFmpeg ass filter invocations in assembler.py include fontsdir=path/to/assets/fonts
- ASS subtitle style uses Alignment=2 and MarginV=150 for bottom-positioned text
- No import errors when loading the modified modules
</success_criteria>

<output>
After completion, create `.planning/quick/3-install-komika-axis-font-and-wire-it-int/3-SUMMARY.md`
</output>
