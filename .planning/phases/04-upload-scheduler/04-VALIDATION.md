---
phase: 4
slug: upload-scheduler
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (>=7.0, already in requirements.txt) |
| **Config file** | none — tests use `sys.path.insert` |
| **Quick run command** | `pytest tests/test_upload.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_upload.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | UPLOAD-01 | unit (mock API) | `pytest tests/test_upload.py::TestYouTubeUpload -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | UPLOAD-02 | unit (mock requests) | `pytest tests/test_upload.py::TestInstagramUpload -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | UPLOAD-03 | unit (mock Anthropic) | `pytest tests/test_upload.py::TestMetadataGeneration -x` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | UPLOAD-04 | unit (mock HttpError) | `pytest tests/test_upload.py::TestRetryBehavior -x` | ❌ W0 | ⬜ pending |
| 04-01-05 | 01 | 1 | UPLOAD-05 | unit (in-memory SQLite) | `pytest tests/test_upload.py::TestUploadLogging -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 2 | SCHED-01 | unit | `pytest tests/test_run_cycle.py::TestDisabledChannel -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | SCHED-02 | integration | `pytest tests/test_run_cycle.py::TestRunCycleFlow -x` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 2 | SCHED-03 | unit | `pytest tests/test_run_cycle.py::TestEmptyBacklogFallback -x` | ❌ W0 | ⬜ pending |
| 04-02-04 | 02 | 2 | SCHED-04 | manual-only | Document cron entry in CLAUDE.md | N/A | ⬜ pending |
| 04-02-05 | 02 | 2 | SCHED-05 | unit | `pytest tests/test_run_cycle.py::TestChannelEnabled -x` | ❌ W0 | ⬜ pending |
| 04-02-06 | 02 | 2 | MULTI-02 | integration | `pytest tests/test_run_cycle.py::TestAllChannels -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_upload.py` — stubs for UPLOAD-01 through UPLOAD-05
- [ ] `tests/test_run_cycle.py` — stubs for SCHED-01 through SCHED-03, SCHED-05, MULTI-02
- [ ] `tests/conftest.py` — shared fixtures (in-memory DB, mock channel_cfg, mock APIs)

*Existing infrastructure covers pytest — no new framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cron executes run-cycle at scheduled times | SCHED-04 | OS-level scheduling; no way to unit test cron timing | 1. Install crontab entry 2. Wait for scheduled time 3. Verify log output in logs/cron.log |
| YouTube video appears on channel | UPLOAD-01 | Requires real YouTube API credentials + compliance audit | 1. Run `setup-youtube` 2. Run `run-cycle` 3. Check YouTube Studio |
| Instagram Reel appears on profile | UPLOAD-02 | Requires real IG Business account + public video URL | 1. Run `setup-instagram` 2. Run `run-cycle` with public URL configured 3. Check Instagram profile |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
