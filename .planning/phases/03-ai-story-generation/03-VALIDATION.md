---
phase: 3
slug: ai-story-generation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already installed — auto-discovers tests/) |
| **Config file** | none — pytest auto-discovers tests/ directory |
| **Quick run command** | `pytest tests/test_story_generator.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_story_generator.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | GEN-01 | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_output_schema -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | GEN-01 | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_reddit_jargon_stripped -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 0 | GEN-01 | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_duration_in_range -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 0 | GEN-02 | unit | `pytest tests/test_story_generator.py::TestBuildRedditPrompt::test_niche_tone_hypothetical -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 0 | GEN-02 | unit | `pytest tests/test_story_generator.py::TestBuildRedditPrompt::test_niche_tone_relationships -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 0 | GEN-02 | unit | `pytest tests/test_story_generator.py::TestAdaptRedditPost::test_no_markdown -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 0 | GEN-03 | unit | `pytest tests/test_story_generator.py::TestBuildRedditPrompt::test_profile_overrides_niche -x` | ❌ W0 | ⬜ pending |
| 03-01-08 | 01 | 0 | GEN-03 | unit | `pytest tests/test_config_channels.py::TestChannelConfig::test_style_profile_optional -x` | ❌ W0 | ⬜ pending |
| 03-01-09 | 01 | 0 | GEN-01 | unit | `pytest tests/test_story_generator.py::TestValidate::test_overlay_phrases_are_substrings -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_story_generator.py` — stubs for GEN-01, GEN-02, GEN-03 (new file, mock Anthropic client)
- [ ] `tests/test_config_channels.py` — extend with `test_style_profile_optional` for GEN-03
- [ ] No new framework install needed — pytest already present

*Existing infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Generated script sounds natural when read aloud via ElevenLabs TTS | GEN-02 | Subjective quality — natural speech phrasing cannot be fully automated | Run `adapt_reddit_post()` on 3 sample posts, feed output through TTS, listen for unnatural phrasing |
| Style profile produces noticeably different tone than niche defaults | GEN-03 | Subjective style matching requires human judgment | Generate scripts with and without profile for same post, compare tone |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
