---
phase: quick-6
plan: 1
subsystem: upload / cli
tags: [upload, youtube, scheduling, cli, run-cycle]
dependency_graph:
  requires: [pipeline/upload.py, main.py]
  provides: [--publish-at CLI flag, scheduled YouTube upload support]
  affects: [run-cycle workflow, upload_to_youtube behavior]
tech_stack:
  added: []
  patterns: [optional kwarg threading through CLI -> command -> upload function]
key_files:
  created: []
  modified:
    - pipeline/upload.py
    - main.py
decisions:
  - publish_at wired as explicit kwarg at each layer (not via config) — keeps function signatures clear and testable
  - Instagram always skipped when publish_at set — no scheduled Instagram equivalent in Graph API
  - ig_status assigned "skipped" explicitly in publish_at branch to avoid undefined-variable risk
metrics:
  duration: "~3 min"
  completed: "2026-03-12"
  tasks_completed: 2
  files_modified: 2
---

# Quick Task 6: Add Scheduled Publish Time to run-cycle Summary

**One-liner:** ISO 8601 --publish-at flag for run-cycle that uploads YouTube as private/scheduled and skips Instagram.

## What Was Built

Added `--publish-at` CLI argument to the `run-cycle` command enabling cron-based scheduled publishing. When provided, YouTube videos are uploaded as private with `publishAt` set; Instagram upload is skipped with a log warning.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add publish_at parameter to upload_to_youtube | 8e5c963 | pipeline/upload.py |
| 2 | Add --publish-at CLI arg and wire through cmd_run_cycle | 0d788cb | main.py |

## Changes Made

### pipeline/upload.py

- `upload_to_youtube` accepts new optional `publish_at: str | None = None` parameter
- When `publish_at` is provided: sets `"privacyStatus": "private"` and `"publishAt": publish_at` in the status block
- When `publish_at` is None (default): keeps `"privacyStatus": "public"` — no behavioral change
- Logs `"upload_to_youtube: scheduling publish at %s"` when scheduling is active
- Docstring updated to document the parameter

### main.py

- `run-cycle` subparser assigned to `p_run` variable (was anonymous before) to enable argument addition
- `--publish-at PUBLISH_AT` argument added to run-cycle with full help text
- `cmd_run_cycle` signature: `publish_at: str | None = None` parameter added
- `upload_to_youtube(...)` call: `publish_at=publish_at` kwarg passed through
- Instagram block: `if publish_at:` guard added before existing `elif not channel_cfg.instagram_user_id` check — logs warning and sets `ig_status = "skipped"`
- `cmd_run_cycle` docstring updated to document the parameter and its effect on Instagram

## Verification

```
python3 main.py --channel hypothetical-scenarios run-cycle --help
# Output shows: --publish-at PUBLISH_AT  ISO 8601 datetime to schedule YouTube publish...

python3 -c "from pipeline.upload import upload_to_youtube; import inspect; sig = inspect.signature(upload_to_youtube); assert sig.parameters['publish_at'].default is None; print('OK')"
# Output: OK
```

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check

- [x] pipeline/upload.py modified — publish_at parameter present
- [x] main.py modified — --publish-at in CLI, wired through
- [x] Commit 8e5c963 exists
- [x] Commit 0d788cb exists

## Self-Check: PASSED
