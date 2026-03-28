---
phase: quick
plan: 5
subsystem: formats/storytelling
tags: [reddit-renderer, playwright, transparency, rounded-corners]
dependency_graph:
  requires: []
  provides: [transparent-png-reddit-post]
  affects: [formats/storytelling/assembler.py]
tech_stack:
  added: []
  patterns: [playwright-omit-background, css-transparent-body]
key_files:
  created: []
  modified:
    - formats/storytelling/reddit_template.html
    - formats/storytelling/reddit_renderer.py
decisions:
  - "body background set to transparent so border-radius clips corners; .post-container retains #1a1a1b"
  - "omit_background=True on container.screenshot() preserves PNG alpha channel"
metrics:
  duration: "3 minutes"
  completed_date: "2026-03-12"
  tasks_completed: 1
  files_modified: 2
---

# Phase quick Plan 5: Make Reddit Post Borders Rounded Summary

## One-liner

Reddit post PNG now uses transparent body background + Playwright `omit_background=True` so corner pixels outside `border-radius: 12px` are alpha=0, letting gameplay footage show through.

## What Was Built

Two minimal changes enable transparent corners:

1. `reddit_template.html` body rule: `background: #1a1a1b` changed to `background: transparent`. The `.post-container` div retains its own `background: #1a1a1b`, so the post interior stays dark. Only the space outside the rounded border becomes transparent.

2. `reddit_renderer.py` `_render_html()`: `container.screenshot(path=str(tmp_png))` gained `omit_background=True`. Without this flag, Playwright fills screenshots with white regardless of CSS transparency.

## Verification

Automated check passed: top-left corner pixel of the rendered PNG has `alpha=0`. Interior pixels remain opaque dark.

## Deviations from Plan

None - plan executed exactly as written.

## Tasks

| # | Task | Status | Commit |
|---|------|--------|--------|
| 1 | Enable transparent background in template and renderer | Done | 8d29429 |

## Self-Check: PASSED

- `formats/storytelling/reddit_template.html` — modified, contains `background: transparent`
- `formats/storytelling/reddit_renderer.py` — modified, contains `omit_background=True`
- Commit `8d29429` — confirmed in git log
