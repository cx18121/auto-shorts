---
phase: quick-260318-mk2
plan: 01
subsystem: config
tags: [config, validation, channels, tweets-format]
dependency_graph:
  requires: []
  provides: [format-conditional subreddits validation]
  affects: [config.py, channels.yaml loading]
tech_stack:
  added: []
  patterns: [conditional dataclass validation in __post_init__]
key_files:
  created: []
  modified:
    - config.py
decisions:
  - subreddits validation gated on format==storytelling; tweets-format channels never use Reddit and need no subreddits
metrics:
  duration: "2min"
  completed: "2026-03-18"
---

# Phase quick-260318-mk2 Plan 01: Fix config.py Validation to Allow Empty Subreddits for Tweets Format Summary

**One-liner:** Format-conditional subreddits validation in ChannelConfig — storytelling requires non-empty subreddits, tweets format does not.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Make subreddits validation conditional on storytelling format | 88c00ca | config.py |

## What Was Built

Changed `ChannelConfig.__post_init__` in `config.py` to check `self.format == "storytelling"` before enforcing a non-empty subreddits list. Previously the check was unconditional, blocking any tweets-format channel (such as `viral-tweets`) that has no subreddits configured.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

- [x] config.py modified at line 111 with format-conditional guard
- [x] Commit 88c00ca exists and contains the change
- [x] Verification passed: tweets channel with empty subreddits loads OK; storytelling channel with empty subreddits raises ValueError

## Self-Check: PASSED
