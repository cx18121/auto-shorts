---
phase: 2
slug: content-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (stdlib `unittest` compatible) |
| **Config file** | none — Wave 0 installs pytest |
| **Quick run command** | `python -m pytest tests/test_backlog.py tests/test_quality_filter.py -x` |
| **Full suite command** | `python -m pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_backlog.py tests/test_quality_filter.py -x`
- **After every plan wave:** Run `python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | BACKLOG-01 | unit (in-memory SQLite) | `python -m pytest tests/test_backlog.py::test_tables_created -x` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 0 | BACKLOG-02 | unit | `python -m pytest tests/test_backlog.py::test_status_transitions -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 0 | BACKLOG-03 | unit | `python -m pytest tests/test_backlog.py::test_get_approved_only -x` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 0 | REDDIT-03 | unit (in-memory SQLite) | `python -m pytest tests/test_backlog.py::test_insert_story -x` | ❌ W0 | ⬜ pending |
| 2-01-05 | 01 | 0 | QUALITY-03 | unit | `python -m pytest tests/test_backlog.py::test_rejected_not_in_approved -x` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 0 | REDDIT-01 | unit (mock PRAW) | `python -m pytest tests/test_reddit_scraper.py::test_scrape_returns_posts -x` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 0 | REDDIT-04 | unit | `python -m pytest tests/test_reddit_scraper.py::test_per_subreddit_failure_isolation -x` | ❌ W0 | ⬜ pending |
| 2-03-01 | 03 | 0 | REDDIT-02 | unit | `python -m pytest tests/test_quality_filter.py::test_story_upvote_filter -x` | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 0 | QUALITY-01 | unit | `python -m pytest tests/test_quality_filter.py::test_story_word_count_bounds -x` | ❌ W0 | ⬜ pending |
| 2-03-03 | 03 | 0 | QUALITY-02 | unit | `python -m pytest tests/test_quality_filter.py::test_tweet_likes_filter -x` | ❌ W0 | ⬜ pending |
| 2-04-01 | 04 | 0 | BACKLOG-04 | integration (subprocess) | `python -m pytest tests/test_cli_review.py::test_review_approve -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_backlog.py` — stubs for BACKLOG-01, BACKLOG-02, BACKLOG-03, REDDIT-03, QUALITY-03
- [ ] `tests/test_reddit_scraper.py` — stubs for REDDIT-01, REDDIT-04 (uses `unittest.mock.patch` for PRAW)
- [ ] `tests/test_quality_filter.py` — stubs for REDDIT-02, QUALITY-01, QUALITY-02
- [ ] `tests/test_cli_review.py` — stubs for BACKLOG-04 (subprocess, mock stdin)
- [ ] `pytest` added to `requirements.txt` — if not already present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `python main.py scrape --channel relationships` end-to-end | REDDIT-01 | Requires real Reddit API credentials + live network | Run command, verify rows appear in `data/pipeline.db` backlog_stories table |
| `python main.py review --channel relationships` interactive flow | BACKLOG-04 | Requires terminal stdin interaction | Run command, verify pending items shown, approve one, confirm status updates to "approved" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
