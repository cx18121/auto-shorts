---
phase: quick-10
plan: 10
type: execute
wave: 1
depends_on: []
files_modified:
  - formats/tweets/scraper.py
autonomous: true
requirements: [QUICK-10]
must_haves:
  truths:
    - "Scraping x.com/home either succeeds within timeout or fails fast with a clear log message"
    - "Stale/invalid cookies produce an immediate logged warning, not a silent hang"
    - "Account profile scraping continues even if home feed scrape fails"
  artifacts:
    - path: "formats/tweets/scraper.py"
      provides: "Fixed scraper with hang-resistant home feed navigation"
  key_links:
    - from: "_scrape_page_playwright"
      to: "page.goto / page.wait_for_selector"
      via: "timeout + login-wall detection"
      pattern: "wait_for_selector.*tweet.*timeout"
---

<objective>
Fix the tweet scraper hanging when navigating to https://x.com/home.

Purpose: The scraper logs "Navigating to https://x.com/home" then never completes. The root cause is that x.com/home — when cookies are stale or when X redirects to a login/interstitial page — fires `domcontentloaded` immediately but `[data-testid="tweet"]` never appears. The `wait_for_selector` call then blocks for 20 seconds before the exception is raised, but if something in the page JavaScript keeps the network active, Playwright may not unblock at all.

Output: A patched `_scrape_page_playwright` that detects login walls and cookie problems immediately, skips the home feed cleanly on failure, and never hangs indefinitely.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@formats/tweets/scraper.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add login-wall detection and hang-resistant navigation to _scrape_page_playwright</name>
  <files>formats/tweets/scraper.py</files>
  <action>
Modify `_scrape_page_playwright` to prevent indefinite hangs on x.com/home:

1. After `page.goto(url, wait_until="domcontentloaded", timeout=30_000)` succeeds, check the current URL. If it contains `/i/flow/`, `/login`, or `/i/nojs_router` — X has redirected to a login wall. Log a warning "Cookie authentication failed — redirected to {page.url}. Re-export data/x.com_cookies.txt." and return [].

2. Change `page.wait_for_selector('[data-testid="tweet"]', timeout=20_000)` to also accept a "login required" selector as an early-exit signal. Use `page.wait_for_selector` wrapped in a try/except that on timeout logs "No tweets found on {label} within timeout — skipping" and returns []. This is already present but the issue is Playwright itself hanging before the timeout fires when the page keeps network activity alive.

3. Add `wait_until="commit"` as the goto strategy for the home feed specifically (url contains "/home"). `"commit"` resolves as soon as the navigation is committed (before DOMContentLoaded), which prevents Playwright from waiting on long-running XHR/websocket activity that x.com/home keeps open indefinitely. After goto with "commit", add an explicit `page.wait_for_load_state("domcontentloaded", timeout=15_000)` in a try/except — on timeout, log and return [].

Concrete changes:

In `_scrape_page_playwright`, replace the existing try/except navigation block:

```python
    logger.info("Navigating to %s", url)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_selector('[data-testid="tweet"]', timeout=20_000)
    except Exception as e:
        logger.warning("Failed to load %s: %s", label or url, e)
        return []
```

With:

```python
    logger.info("Navigating to %s", url)
    try:
        # Use "commit" for x.com/home — the page keeps websockets open indefinitely
        # which prevents "domcontentloaded" from ever resolving in some cookie states.
        nav_wait = "commit" if "/home" in url else "domcontentloaded"
        await page.goto(url, wait_until=nav_wait, timeout=30_000)

        # After navigation commit, wait for DOMContentLoaded separately with its own timeout
        if nav_wait == "commit":
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:
                logger.debug("DOMContentLoaded timeout for %s — continuing anyway", label or url)

        # Detect login wall redirect
        current_url = page.url
        if any(marker in current_url for marker in ("/i/flow/", "/login", "/i/nojs_router")):
            logger.warning(
                "Cookie authentication failed — redirected to %s. "
                "Re-export data/x.com_cookies.txt from your browser while logged in to X.com.",
                current_url,
            )
            return []

        await page.wait_for_selector('[data-testid="tweet"]', timeout=20_000)
    except Exception as e:
        logger.warning("Failed to load %s: %s", label or url, e)
        return []
```

No other changes needed. The existing error handling in `_scrape_async` already catches exceptions from `_scrape_home_playwright` and continues to account scraping.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "import ast, sys; ast.parse(open('formats/tweets/scraper.py').read()); print('syntax OK')"</automated>
  </verify>
  <done>
    - `formats/tweets/scraper.py` parses without syntax errors
    - `_scrape_page_playwright` uses `wait_until="commit"` for /home URLs
    - Login wall redirect check is present (checks for /i/flow/, /login, /i/nojs_router)
    - Separate `wait_for_load_state("domcontentloaded", timeout=15_000)` call exists for home feed
    - Running `python main.py generate --format tweets --scrape --count 1` either returns scraped tweets or exits cleanly within ~60 seconds with logged warnings (no indefinite hang)
  </done>
</task>

</tasks>

<verification>
After applying the fix, test with stale/missing cookies to confirm fast failure:

```bash
# Rename cookie file temporarily to simulate stale/missing cookies
mv data/x.com_cookies.txt data/x.com_cookies.txt.bak
python main.py generate --format tweets --scrape --count 1
# Should fail fast with FileNotFoundError (cookie file missing), not hang

mv data/x.com_cookies.txt.bak data/x.com_cookies.txt
# With real cookies, run and observe: should not hang on x.com/home
python -c "
from formats.tweets.scraper import scrape_top_tweets
tweets = scrape_top_tweets(n=2, min_likes=100, include_home=False)
print('Account-only scrape OK:', len(tweets), 'tweets')
"
```
</verification>

<success_criteria>
- Navigating to x.com/home no longer hangs indefinitely
- Login wall redirects produce an immediate warning log and clean return
- Account profile scraping works independently of home feed success
- Python syntax check passes on the modified file
</success_criteria>

<output>
After completion, create `.planning/quick/10-fix-twitter-scraper-getting-stuck-after-/10-SUMMARY.md`
</output>
