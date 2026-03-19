---
phase: quick
plan: 260319-kwt
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_run_cycle.py
  - tests/test_reddit_scraper.py
  - tests/test_story_generator.py
autonomous: true
must_haves:
  truths:
    - "All 32 previously-failing tests pass"
    - "Full suite `python3 -m pytest tests/ -v` has no regressions"
    - "test_config_channels.py passes both in isolation and in full suite"
  artifacts:
    - path: "tests/test_run_cycle.py"
      provides: "Updated imports pointing to commands/ modules"
    - path: "tests/test_reddit_scraper.py"
      provides: "Test mocking requests.get instead of PRAW"
    - path: "tests/test_story_generator.py"
      provides: "Safe import that patches config before module load"
---

<objective>
Fix 32 failing tests across 4 test files caused by stale imports, wrong mock interfaces, and global state pollution.

Purpose: Restore the test suite to green after the dbdac78 refactor that moved commands to `commands/` and the reddit scraper rewrite from PRAW to requests.
Output: All 32 tests pass, no production code changes.
</objective>

<execution_context>
@/home/cx3429/.claude/get-shit-done/workflows/execute-plan.md
@/home/cx3429/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@commands/run_cycle.py
@commands/scrape.py
@pipeline/reddit_scraper.py
@formats/storytelling/generator.py
@config.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix test_run_cycle.py imports and mock targets</name>
  <files>tests/test_run_cycle.py</files>
  <action>
The test file does `from main import cmd_run_cycle` and `from main import cmd_upload_history`, but after the dbdac78 refactor these functions live in `commands/run_cycle.py` and `commands/scrape.py`. The mock targets also reference `main.xxx` but the functions now live in `commands.run_cycle` and `commands.scrape`.

Changes needed:

1. Replace all `from main import cmd_run_cycle` with `from commands.run_cycle import cmd_run_cycle` (lines 107, 121, 169, 183, 200, 254, 299, 352, 379, 429, 462, 522, 551, 605, 634, 771).

2. Replace all `from main import cmd_upload_history` with `from commands.scrape import cmd_upload_history` (lines 699, 714, 740).

3. Update all `patch("main.xxx")` mock targets to point to the correct modules:
   - `patch("main.cmd_scrape")` -> `patch("commands.run_cycle.cmd_scrape")` (the cmd_run_cycle function imports cmd_scrape from commands.scrape)
   - `patch("main.logger")` -> `patch("commands.run_cycle.logger")` (for tests on cmd_run_cycle)
   - `patch("main._generate_with_quality", ...)` -> `patch("commands.run_cycle._generate_with_quality", ...)` (imported from commands.generate into run_cycle)
   - `patch("main._run_storytelling_pipeline", ...)` -> `patch("commands.run_cycle._run_storytelling_pipeline", ...)`
   - `patch("main._pick_background", ...)` -> `patch("commands.run_cycle._pick_background", ...)`
   - `patch("main._run_tweet_pipeline", ...)` -> `patch("commands.run_cycle._run_tweet_pipeline", ...)`
   - `patch("main.Path")` -> `patch("commands.run_cycle.Path")`
   - `patch("main.config")` -> `patch("commands.run_cycle.config")`
   - `patch("main._dispatch_command")` -> `patch("main._dispatch_command")` (this one stays -- _dispatch_command is still in main.py)

4. Also add `commands.run_cycle` to the sys.modules mock setup at the top of the file so the `config` import inside `commands/run_cycle.py` does not trigger channels.yaml SystemExit. Specifically, pre-mock `commands.scrape` and `commands.generate` with MagicMock in sys.modules.setdefault so that importing commands.run_cycle does not trigger real config loading.

5. For the TestAllChannels and TestSubcommandWiring classes that reference `main._dispatch_command` and `main.config`, these stay as-is since _dispatch_command is still in main.py.

IMPORTANT: The `commands/run_cycle.py` file imports at the top level:
- `import config`
- `from commands.generate import _generate_with_quality, _load_style_profile, _pick_background, _run_storytelling_pipeline, _run_tweet_pipeline, _save_video_metadata`
- `from commands.scrape import cmd_scrape`

So mock targets for functions used inside cmd_run_cycle must use the `commands.run_cycle` namespace (where they are looked up), not `commands.generate`.

Also ensure `sys.modules.setdefault("commands", MagicMock())` and `sys.modules.setdefault("commands.generate", MagicMock())` and `sys.modules.setdefault("commands.scrape", MagicMock())` are added to the module-level mock block to avoid import-time failures.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python3 -m pytest tests/test_run_cycle.py -v --tb=short 2>&1 | tail -30</automated>
  </verify>
  <done>All 18 tests in test_run_cycle.py pass. test_config_channels.py still passes in isolation.</done>
</task>

<task type="auto">
  <name>Task 2: Fix test_reddit_scraper.py mock interface and test_story_generator.py import</name>
  <files>tests/test_reddit_scraper.py, tests/test_story_generator.py</files>
  <action>
**test_reddit_scraper.py (1 failure):**

`test_scrape_returns_posts` mocks a PRAW Reddit object (`mock_reddit.subreddit.return_value.top.return_value`) but `scrape_subreddit_top()` now takes `(subreddit_name, time_filter, limit)` — no reddit object parameter — and uses `requests.get` against `https://www.reddit.com/r/{sub}/top.json`.

Fix `TestScrapeReturnsPosts.test_scrape_returns_posts`:
1. Remove the `mock_reddit` MagicMock creation entirely.
2. Instead, `patch("pipeline.reddit_scraper.requests.get")` to return a mock Response whose `.json()` returns a Reddit JSON structure:
```python
fake_children = [
    {"data": {"id": f"id{i}", "is_self": True, "selftext": "Valid selftext content " * 20, "title": "Test story", "score": 5000, "permalink": f"/r/AITAH/comments/id{i}/test/"}}
    for i in range(3)
]
mock_resp = MagicMock()
mock_resp.json.return_value = {"data": {"children": [{"data": c["data"]} for c in fake_children], "after": None}}
mock_resp.raise_for_status = MagicMock()
mock_get.return_value = mock_resp
```
3. Call `scrape_subreddit_top("AITAH", limit=10)` (no reddit param).
4. Keep the same assertions (len==3, required keys present).

Also fix `TestSelftextFilter.test_selftext_filter_empty` similarly:
1. Mock `requests.get` with posts that have empty/removed/deleted selftext but `is_self=True`.
2. Call `scrape_subreddit_top("AITAH", limit=10)` without reddit param.

The `_make_fake_post` helper can be removed or kept but is no longer used by these tests. Remove it for cleanliness.

For `TestPerSubredditFailureIsolation.test_per_subreddit_failure_isolation`: This test patches `pipeline.reddit_scraper.scrape_subreddit_top` directly and calls `scrape_channel_subreddits(channel_cfg, mock_reddit)`, but the real signature is `scrape_channel_subreddits(channel_cfg, time_filter, limit)` — no reddit param. Fix: call `scrape_channel_subreddits(channel_cfg)` (uses defaults). Update the side_effect to match the new signature `(subreddit_name, time_filter="day", limit=25)` instead of `(reddit, subreddit_name, ...)`.

**test_story_generator.py (1 failure):**

`formats/storytelling/generator.py` does `import config` at the top level, and `config.py` line 150 calls `load_channels()` which raises `SystemExit` when `channels.yaml` is absent.

The test file already imports `from formats.storytelling import generator` in each `setUp`. The fix is to add a module-level config mock BEFORE the generator is first imported:

At the top of the file (after sys.path setup, before any test class):
```python
# Patch config.load_channels before any import of generator.py triggers it
import config as _cfg_mod
if not hasattr(_cfg_mod, '_test_patched'):
    _cfg_mod.CHANNELS = {}
    _cfg_mod.ANTHROPIC_API_KEY = "test-key"
    _cfg_mod._test_patched = True
```

Actually, the simpler and more robust approach: add to sys.modules a mock config BEFORE importing, like test_run_cycle.py does. But test_story_generator.py does direct import inside setUp... The cleanest fix:

Add at the top of test_story_generator.py (after sys.path, before class definitions):
```python
# Pre-create channels.yaml from example so config.load_channels() succeeds
_example = PROJECT_ROOT / "channels.yaml.example"
_channels_yaml = PROJECT_ROOT / "channels.yaml"
if _example.exists() and not _channels_yaml.exists():
    _channels_yaml.write_text(_example.read_text())
```

Wait -- this would fix the import but create a real file. The issue is that config.py is a real module that calls load_channels() at import time. Since test_story_generator.py actually USES the real generator module (testing real functions like _validate, _build_reddit_prompt), we need config to load successfully.

Better approach: Mock config in sys.modules before the first import of generator:
```python
_mock_config = MagicMock()
_mock_config.ANTHROPIC_API_KEY = "test-api-key"
_mock_config.CHANNELS = {}
sys.modules.setdefault("config", _mock_config)
```

But this would conflict with test_config_channels.py which reloads the real config module. The `setdefault` only sets if not already present, so if config was already imported (by another test file in the suite), it won't override.

The ROOT CAUSE of the cross-test pollution (root cause 4) is that test_run_cycle.py does `sys.modules.setdefault("config", _mock_config)` at module level, and when pytest collects test_config_channels.py AFTER test_run_cycle.py, the config module is already the mock. Then `importlib.reload(config)` in test_config_channels tries to reload the mock.

The fix for ALL issues (root causes 3 and 4 together):

In **test_story_generator.py**: Add the same `sys.modules.setdefault("config", _mock_config)` pattern at module level (like test_run_cycle.py does). Also mock `pipeline.claude_utils` to avoid that import chain:
```python
_mock_config = MagicMock()
_mock_config.ANTHROPIC_API_KEY = "test-api-key"
sys.modules.setdefault("config", _mock_config)
sys.modules.setdefault("pipeline.claude_utils", MagicMock())
```

For **test_config_channels.py** (root cause 4, global state pollution): The `setUp` does `importlib.reload(config)` but the config in sys.modules might be a MagicMock from another test file. Fix: In setUp, force-replace sys.modules["config"] with the REAL config module before reload:
```python
def setUp(self):
    self.channels_yaml = PROJECT_ROOT / "channels.yaml"
    self.channels_yaml.write_text(EXAMPLE_YAML)
    # Force real config module (other test files may have injected a Mock)
    if "config" in sys.modules and not hasattr(sys.modules["config"], '__file__'):
        del sys.modules["config"]
    import importlib
    import config
    importlib.reload(config)
    self.config = config
```

Also add tearDown cleanup to restore: after unlinking channels.yaml, also delete config from sys.modules so it doesn't leave stale state:
```python
def tearDown(self):
    if self.channels_yaml.exists():
        self.channels_yaml.unlink()
    # Don't leave real config in sys.modules — other tests may need mocked version
    # (No change needed here — setUp handles the reverse direction)
```

Wait, we need to be more careful. The issue is bidirectional:
- If test_run_cycle.py runs first, sys.modules["config"] is a MagicMock -> test_config_channels reload fails
- If test_config_channels.py runs first, it reloads real config (which needs channels.yaml) -> then test_run_cycle.py's setdefault is a no-op and the real config stays

The cleanest fix for test_config_channels.py's setUp:
```python
def setUp(self):
    self.channels_yaml = PROJECT_ROOT / "channels.yaml"
    self.channels_yaml.write_text(EXAMPLE_YAML)
    # Ensure we load the REAL config module, not a test mock
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    importlib.reload(config)
    self.config = config
```

And in tearDown, remove from sys.modules to avoid polluting other tests:
```python
def tearDown(self):
    if self.channels_yaml.exists():
        self.channels_yaml.unlink()
    # Remove real config to avoid SystemExit when other tests try to import
    if "config" in sys.modules and hasattr(sys.modules["config"], '__file__'):
        del sys.modules["config"]
```
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python3 -m pytest tests/test_reddit_scraper.py tests/test_story_generator.py tests/test_config_channels.py -v --tb=short 2>&1 | tail -40</automated>
  </verify>
  <done>All tests in test_reddit_scraper.py (3), test_story_generator.py (16+), and test_config_channels.py (12) pass both individually and when run together.</done>
</task>

<task type="auto">
  <name>Task 3: Full suite verification</name>
  <files>tests/test_run_cycle.py, tests/test_reddit_scraper.py, tests/test_story_generator.py, tests/test_config_channels.py</files>
  <action>
Run the complete test suite to verify no regressions:
```
python3 -m pytest tests/ -v --tb=short
```

If any test_config_channels.py tests still fail due to ordering, the issue is sys.modules["config"] contamination. Debug by checking the test collection order and ensuring:
1. test_config_channels.py setUp deletes mock config from sys.modules before importing real config
2. test_config_channels.py tearDown cleans up the real config from sys.modules
3. No test file's module-level code forces a real config import that would trigger SystemExit

If any other tests regress, investigate whether it's due to the sys.modules cleanup and adjust accordingly. The key invariant: tests that need mock config use `sys.modules.setdefault`, tests that need real config (test_config_channels.py) force-delete and re-import.
  </action>
  <verify>
    <automated>cd /mnt/c/Users/charl/School/cs_misc/auto-shorts && python3 -m pytest tests/ -v 2>&1 | tail -50</automated>
  </verify>
  <done>Full test suite passes with 0 failures. The 32 previously-failing tests are all green.</done>
</task>

</tasks>

<verification>
```bash
# Run full suite
python3 -m pytest tests/ -v --tb=short

# Verify the specific 4 files
python3 -m pytest tests/test_run_cycle.py tests/test_reddit_scraper.py tests/test_story_generator.py tests/test_config_channels.py -v

# Verify test_config_channels.py passes in both isolation AND full suite
python3 -m pytest tests/test_config_channels.py -v
```
</verification>

<success_criteria>
- All 32 previously-failing tests pass
- No regressions in other test files
- test_config_channels.py passes both in isolation and in full suite run
- No production code modified
</success_criteria>

<output>
After completion, create `.planning/quick/260319-kwt-fix-32-failing-tests-across-4-root-cause/260319-kwt-SUMMARY.md`
</output>
