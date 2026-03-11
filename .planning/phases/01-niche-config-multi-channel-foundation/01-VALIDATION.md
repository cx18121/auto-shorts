---
phase: 1
slug: niche-config-multi-channel-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None — standalone `python3 tests/test_X.py` scripts (project convention) |
| **Config file** | none |
| **Quick run command** | `python3 tests/test_config_channels.py` |
| **Full suite command** | `python3 tests/test_tts.py && python3 tests/test_assembler.py && python3 tests/test_config_channels.py && python3 tests/test_cli_channel_flag.py` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 tests/test_config_channels.py`
- **After every plan wave:** Run full suite command above
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | NICHE-01 | unit | `python3 tests/test_config_channels.py` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | MULTI-03 | smoke | `python3 tests/test_cli_channel_flag.py` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | NICHE-01 | unit | `python3 tests/test_config_channels.py` | ✅ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | NICHE-02 | unit | `python3 tests/test_config_channels.py` | ✅ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | NICHE-03 | unit | `python3 tests/test_config_channels.py` | ✅ W0 | ⬜ pending |
| 1-01-06 | 01 | 1 | MULTI-01 | unit | `python3 tests/test_config_channels.py` | ✅ W0 | ⬜ pending |
| 1-01-07 | 01 | 1 | MULTI-03 | smoke | `python3 tests/test_cli_channel_flag.py` | ✅ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_config_channels.py` — stubs for NICHE-01, NICHE-02, NICHE-03, MULTI-01, MULTI-03 (config loading)
- [ ] `tests/test_cli_channel_flag.py` — smoke test for MULTI-03 (argparse routing with --channel flag)
- [ ] `channels.yaml.example` — required before any test can load channels

*No framework install needed — existing project pattern uses standalone scripts.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No data bleeds across channels at runtime | MULTI-01 | Requires full pipeline run with two channels to verify isolation | Run `python main.py --channel hypothetical-scenarios generate --format storytelling` then `python main.py --channel relationships generate --format storytelling`; confirm output dirs and DB partitions stay separate |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
