---
phase: quick
plan: 9
type: execute
wave: 1
depends_on: []
files_modified:
  - pipeline/backlog.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Running `review` after a fresh scrape shows new stories interleaved with existing backlog items by score"
    - "A story with score 5000 scraped today appears between existing stories with score 6000 and 4000"
  artifacts:
    - path: "pipeline/backlog.py"
      provides: "get_pending_stories with correct sort order"
      contains: "ORDER BY score DESC, scraped_at DESC"
  key_links:
    - from: "pipeline/backlog.py get_pending_stories"
      to: "main.py cmd_review"
      via: "direct function call"
---

<objective>
Fix the review command so newly scraped stories are interleaved with existing backlog items by score.

Purpose: Users scraping with `--window 24h` after an initial `--window year` bootstrap see the daily posts clustered at the bottom of the review queue because their Reddit scores are lower. Adding `scraped_at DESC` as a secondary sort doesn't fix true interleaving by score. The actual issue is that `get_pending_stories` has the correct `ORDER BY score DESC` SQL, but the existing DB stores year-window posts with Reddit scores of 10K–500K+ while daily posts have scores of 500–10K. The "separate group" appearance is correct behavior, but it's unusable — reviewers need to see new posts without scrolling through the entire old backlog first.

The fix: change the default review order to `scraped_at DESC, score DESC` (newest first, then score within the same scrape batch). This ensures daily items always appear at the top of the review queue regardless of their score relative to the year-window backlog. Reviewers work through today's batch first, then older items surface.

Output: Updated `get_pending_stories` in `pipeline/backlog.py`.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Inspect DB and fix get_pending_stories sort order</name>
  <files>pipeline/backlog.py</files>
  <action>
First, inspect the actual data to confirm the root cause. Run this SQL against `data/pipeline.db`:

```sql
SELECT channel, MIN(score), MAX(score), AVG(score), COUNT(*),
       MIN(scraped_at), MAX(scraped_at)
FROM backlog_stories
WHERE status = 'pending'
GROUP BY channel;
```

This will confirm whether existing items have dramatically higher scores than new items (the expected root cause), or whether scores are somehow being stored as 0/NULL (a data bug).

Then fix `get_pending_stories` in `pipeline/backlog.py`. Change the ORDER BY from:

```python
" ORDER BY score DESC",
```

to:

```python
" ORDER BY scraped_at DESC, score DESC",
```

Rationale: `scraped_at DESC` groups items by when they were scraped (newest batch first), and `score DESC` ranks within each batch by quality. This means today's daily posts appear at the top of the review queue, followed by yesterday's, etc. Within each batch, the highest-scoring posts appear first. This is more useful than global score ordering across different time-window scrapes where year-window posts always dominate.

Also update the docstring to read:
```
"""Return pending stories for *channel*, newest scraped batch first, then by score DESC within each batch."""
```

Do NOT change `get_pending_tweets` — that function uses a computed score column `(likes + retweets * 3)` and its ordering was just fixed in task 8. The same reasoning applies: if tweet scraping has similar time-window variance, it will need the same fix, but that's a separate issue.

Do NOT change `get_approved_stories` or any other function — only `get_pending_stories`.
  </action>
  <verify>
```bash
cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "
import sqlite3, sys
sys.path.insert(0, '.')
from analysis.db import get_connection
from pipeline.backlog import get_pending_stories, init_backlog_tables

# Test with in-memory DB: insert items with different scores and scraped_at,
# verify order is newest-batch-first then score DESC within batch.
conn = sqlite3.connect(':memory:')
conn.row_factory = sqlite3.Row
init_backlog_tables(conn)

rows = [
    ('old-high', 'test', 'r/test', 'Old High Score', 'body', 50000, 100, 'pending', '2026-01-01T00:00:00', None, None),
    ('old-low', 'test', 'r/test', 'Old Low Score', 'body', 1000, 100, 'pending', '2026-01-01T00:00:01', None, None),
    ('new-mid', 'test', 'r/test', 'New Mid Score', 'body', 5000, 100, 'pending', '2026-03-13T00:00:00', None, None),
    ('new-low', 'test', 'r/test', 'New Low Score', 'body', 500, 100, 'pending', '2026-03-13T00:00:01', None, None),
]
conn.executemany('INSERT INTO backlog_stories (id, channel, subreddit, title, body, score, word_count, status, scraped_at, approved_at, used_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', rows)
conn.commit()

items = get_pending_stories(conn, 'test')
ids = [row['id'] for row in items]
print('Order:', ids)

# Expect: new-mid, new-low (newest batch first, score DESC within batch), then old-high, old-low
assert ids[0] == 'new-mid', f'Expected new-mid first, got {ids[0]}'
assert ids[1] == 'new-low', f'Expected new-low second, got {ids[1]}'
assert ids[2] == 'old-high', f'Expected old-high third, got {ids[2]}'
assert ids[3] == 'old-low', f'Expected old-low last, got {ids[3]}'
print('PASS: newest batch appears first, score DESC within batch')
conn.close()
"
```
  </verify>
  <done>
`get_pending_stories` returns pending stories ordered by `scraped_at DESC, score DESC`. The test passes: a story scraped today with score 5000 appears before a story scraped in January with score 50000. Review queue always shows the newest batch at the top.
  </done>
</task>

</tasks>

<verification>
```bash
cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -m pytest tests/test_backlog.py -x -q 2>&1 | tail -20
```
All backlog tests pass. The sort order change is backward-compatible with existing tests (they test correctness of pending/approved/rejected filtering, not specific ordering).
</verification>

<success_criteria>
- `get_pending_stories` uses `ORDER BY scraped_at DESC, score DESC`
- Verification test passes: newest-batch stories appear before older high-score stories
- Existing `test_backlog.py` tests continue to pass
- `get_pending_tweets` is unchanged
</success_criteria>

<output>
After completion, create `.planning/quick/9-sort-new-backlog-stories-together-with-e/9-SUMMARY.md`
</output>
