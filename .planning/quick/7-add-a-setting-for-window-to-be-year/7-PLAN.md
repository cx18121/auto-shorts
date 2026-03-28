---
phase: quick-7
plan: 7
type: execute
wave: 1
depends_on: []
files_modified:
  - main.py
  - pipeline/reddit_scraper.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Running scrape --window year succeeds without CLI error"
    - "Reddit scraper fetches top posts from the past year"
  artifacts:
    - path: "main.py"
      provides: "year added to --window choices"
    - path: "pipeline/reddit_scraper.py"
      provides: "year mapped to Reddit time_filter 'year'"
  key_links:
    - from: "main.py --window year"
      to: "pipeline/reddit_scraper.py WINDOW_MAP"
      via: "cmd_scrape passes window string to scrape_and_store_reddit"
      pattern: "WINDOW_MAP.*year"
---

<objective>
Add "year" as a valid value for the --window argument on the scrape command.

Purpose: Allows scraping Reddit top posts over the past year, useful for deep backlog bootstrapping beyond the existing "month" window.
Output: CLI accepts --window year; reddit scraper maps it to Reddit's "year" time_filter.
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
  <name>Task 1: Add "year" to CLI choices and WINDOW_MAP</name>
  <files>main.py, pipeline/reddit_scraper.py</files>
  <action>
Two changes:

1. In main.py around line 93, update the --window argument:
   - Change: `choices=["24h", "month"]`
   - To: `choices=["24h", "month", "year"]`
   - Update the help string to mention year: `"Time window: '24h' for daily (default), 'month' for bootstrap fill, 'year' for deep backlog"`

2. In pipeline/reddit_scraper.py WINDOW_MAP (lines 29-32), add the year entry:
   ```python
   WINDOW_MAP: dict[str, str] = {
       "24h": "day",
       "month": "month",
       "year": "year",
   }
   ```
   Reddit's public JSON /top endpoint accepts t=year as a valid time filter parameter — no other changes needed.

   Also update the docstring for scrape_and_store_reddit's `window` param (around line 176) to include "year" in the accepted values list.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python main.py --channel hypothetical-scenarios scrape --help | grep -A2 "window"</automated>
  </verify>
  <done>"year" appears in --window choices in the help output; WINDOW_MAP contains "year": "year"</done>
</task>

</tasks>

<verification>
python main.py --channel hypothetical-scenarios scrape --help shows year as a valid window choice.
python -c "from pipeline.reddit_scraper import WINDOW_MAP; assert WINDOW_MAP['year'] == 'year'" exits 0.
</verification>

<success_criteria>
- --window year is accepted by the CLI without error
- WINDOW_MAP maps "year" -> "year" so Reddit's top endpoint receives t=year
- Help text documents the year option
</success_criteria>

<output>
After completion, create `.planning/quick/7-add-a-setting-for-window-to-be-year/7-SUMMARY.md`
</output>
