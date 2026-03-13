---
phase: quick-8
plan: 8
type: execute
wave: 1
depends_on: []
files_modified:
  - pipeline/backlog.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "Pending tweets presented in review command are ordered highest-score first (likes + retweets*3)"
    - "Pending stories remain ordered by score DESC (no regression)"
  artifacts:
    - path: "pipeline/backlog.py"
      provides: "get_pending_tweets ordered by computed score DESC"
      contains: "likes + retweets * 3"
  key_links:
    - from: "pipeline/backlog.py:get_pending_tweets"
      to: "main.py:cmd_review"
      via: "items list fed into review loop"
      pattern: "get_pending_tweets"
---

<objective>
Sort backlog tweet items by computed score (likes + retweets*3) descending when the review command fetches pending items.

Purpose: Reviewers should see the highest-quality tweets first, using the same scoring formula already used at scrape time.
Output: get_pending_tweets updated to ORDER BY (likes + retweets * 3) DESC.
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
  <name>Task 1: Sort pending tweets by computed score in get_pending_tweets</name>
  <files>pipeline/backlog.py</files>
  <action>
    In get_pending_tweets (line 336), change the ORDER BY clause from `ORDER BY likes DESC` to `ORDER BY (likes + retweets * 3) DESC`.

    The formula `likes + retweets * 3` is the established tweet scoring formula in this codebase (confirmed in tests/test_tweet_scraper_store.py line 52). No schema change needed — this is a computed expression in SQL.

    Do not change get_pending_stories — it already orders by `score DESC` correctly.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "
import sqlite3, sys
from pipeline.backlog import init_backlog_tables, get_pending_tweets
conn = sqlite3.connect(':memory:')
conn.row_factory = sqlite3.Row
init_backlog_tables(conn)
# Insert two tweets: low likes/high retweets should rank above high likes/low retweets
conn.execute(\"INSERT INTO backlog_tweets VALUES ('a','ch','u1','text a',100,50,'pending','2024-01-01',NULL,NULL)\")
conn.execute(\"INSERT INTO backlog_tweets VALUES ('b','ch','u2','text b',200,5,'pending','2024-01-01',NULL,NULL)\")
conn.commit()
items = get_pending_tweets(conn, 'ch')
# tweet a: 100 + 50*3 = 250, tweet b: 200 + 5*3 = 215 — a should be first
assert items[0]['tweet_id'] == 'a', f'Expected tweet a first (score 250), got {items[0][\"tweet_id\"]}'
print('PASS: tweets sorted by likes + retweets*3 DESC')
conn.close()
"
    </automated>
  </verify>
  <done>get_pending_tweets returns rows ordered by (likes + retweets * 3) DESC; the inline test asserts a tweet with 100 likes + 50 retweets ranks above one with 200 likes + 5 retweets.</done>
</task>

</tasks>

<verification>
Run the automated assertion in the verify block. Confirms the scoring formula is applied correctly and ordering is descending by computed score.
</verification>

<success_criteria>
- get_pending_tweets uses ORDER BY (likes + retweets * 3) DESC
- Inline test passes without errors
- get_pending_stories unchanged (no regression)
</success_criteria>

<output>
After completion, create `.planning/quick/8-sort-backlog-by-score-in-review-command/8-SUMMARY.md`
</output>
