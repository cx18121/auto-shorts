---
phase: quick-260318-lld
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - formats/tweets/scraper.py
autonomous: true
requirements: [fix-profile-hang]
must_haves:
  truths:
    - "Scraper navigates to account profile pages without hanging"
    - "Tweets are extracted from profile pages when cookies are valid"
    - "Failed/blocked profile pages log a warning and return empty list instead of hanging"
  artifacts:
    - path: "formats/tweets/scraper.py"
      provides: "Anti-detection browser launch + resilient profile page navigation"
      contains: "AutomationControlled"
  key_links:
    - from: "formats/tweets/scraper.py::_scrape_async"
      to: "pw.chromium.launch"
      via: "stealth browser args"
      pattern: "AutomationControlled"
---

<objective>
Fix the Twitter scraper hanging when navigating to X.com account profile pages (e.g. x.com/WhatIfAlt).

The scraper hangs at `await page.wait_for_selector('[data-testid="tweet"]', timeout=20_000)` on profile pages. The previous fix (quick task 10) addressed /home URL hanging with commit-based navigation, but profile pages still use `domcontentloaded` and X.com likely detects headless Chromium, serving a degraded page where tweet cards never render.

Purpose: Unblock tweet scraping from curated account profiles — the primary content source for the pipeline.
Output: Updated scraper.py that bypasses headless detection and uses resilient navigation for all page types.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@formats/tweets/scraper.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add stealth/anti-detection to Playwright browser launch</name>
  <files>formats/tweets/scraper.py</files>
  <action>
Modify `_scrape_async()` in formats/tweets/scraper.py to launch Chromium with anti-detection measures:

1. **Browser launch args** — add these chromium args to `pw.chromium.launch()`:
   ```python
   browser = await pw.chromium.launch(
       headless=True,
       args=[
           "--disable-blink-features=AutomationControlled",
           "--disable-features=IsolateOrigins,site-per-process",
           "--disable-infobars",
           "--no-first-run",
       ],
   )
   ```

2. **Remove automation signals from context** — after creating the browser context, run JavaScript to delete `navigator.webdriver`:
   ```python
   await ctx.add_init_script("""
       Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
   """)
   ```
   Place this BEFORE `await ctx.add_cookies(cookies)`.

3. **Add locale and timezone to context** — extend the `browser.new_context()` call:
   ```python
   ctx = await browser.new_context(
       user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
       viewport={"width": 1280, "height": 900},
       locale="en-US",
       timezone_id="America/New_York",
   )
   ```
   Update the Chrome version in user_agent from 122 to 131 (more current, less suspicious).
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "import ast; ast.parse(open('formats/tweets/scraper.py').read()); print('OK')"</automated>
  </verify>
  <done>Browser launches with anti-detection args, navigator.webdriver removed, user agent updated to Chrome 131</done>
</task>

<task type="auto">
  <name>Task 2: Make profile page navigation resilient like home feed</name>
  <files>formats/tweets/scraper.py</files>
  <action>
Modify `_scrape_page_playwright()` to use resilient navigation for ALL URLs (not just /home):

1. **Use commit-based navigation for all URLs** — change the `nav_wait` logic so ALL X.com pages use `"commit"` instead of only `/home`:
   ```python
   await page.goto(url, wait_until="commit", timeout=30_000)
   ```
   Remove the conditional `nav_wait = "commit" if "/home" in url else "domcontentloaded"` — always use commit.

2. **Always wait for DOMContentLoaded separately** with its own timeout (same pattern as the /home fix):
   ```python
   try:
       await page.wait_for_load_state("domcontentloaded", timeout=15_000)
   except Exception:
       logger.debug("DOMContentLoaded timeout for %s — continuing anyway", label or url)
   ```
   Remove the `if nav_wait == "commit":` guard — always run this block after goto.

3. **Add a pre-tweet-selector wait** — before waiting for `[data-testid="tweet"]`, add a short delay and wait for the main timeline container first:
   ```python
   await page.wait_for_timeout(2_000)  # let JS hydrate
   ```

4. **Add a fallback selector strategy** — if `[data-testid="tweet"]` times out, try waiting for `article` elements as a fallback before giving up:
   ```python
   try:
       await page.wait_for_selector('[data-testid="tweet"]', timeout=15_000)
   except Exception:
       logger.debug("Primary tweet selector timeout for %s, trying article fallback", label or url)
       try:
           await page.wait_for_selector('article', timeout=10_000)
       except Exception as e2:
           logger.warning("Failed to load %s: no tweets or articles found", label or url)
           return []
   ```
   Replace the existing single `wait_for_selector` + broad except block.

5. **Use `[data-testid="tweet"]` for card collection but also try `article` as fallback** in the scroll loop:
   ```python
   cards = await page.query_selector_all('[data-testid="tweet"]')
   if not cards:
       cards = await page.query_selector_all('article[data-testid="tweet"]')
   ```
   (This is a minor resilience improvement — the primary selector should work once anti-detection is in place.)
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python -c "import ast; ast.parse(open('formats/tweets/scraper.py').read()); print('OK')"</automated>
  </verify>
  <done>All X.com URLs use commit-based navigation with separate DOMContentLoaded wait, fallback selector strategy prevents hanging, 2s hydration delay added before tweet selector wait</done>
</task>

</tasks>

<verification>
1. `python -c "import ast; ast.parse(open('formats/tweets/scraper.py').read())"` passes
2. Manual test: `python -c "from formats.tweets.scraper import scrape_top_tweets; tweets = scrape_top_tweets(n=3, min_likes=100, accounts=['WhatIfAlt'], include_home=False); print(f'Got {len(tweets)} tweets')"` completes without hanging (may return 0 if cookies expired, but must not hang)
</verification>

<success_criteria>
- Scraper does not hang on profile page navigation (returns results or empty list within ~60s per account)
- Anti-detection args present in browser launch
- navigator.webdriver removed via init script
- All URLs use commit-based navigation (not just /home)
- Fallback selector strategy prevents indefinite waits
</success_criteria>

<output>
After completion, create `.planning/quick/260318-lld-fix-twitter-scraper-hanging-on-account-p/260318-lld-SUMMARY.md`
</output>
