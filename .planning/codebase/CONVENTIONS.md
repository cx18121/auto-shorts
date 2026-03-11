# Coding Conventions

**Analysis Date:** 2026-03-11

## Naming Patterns

**Files:**
- Lowercase with underscores: `pipeline/tts.py`, `analysis/fetcher.py`, `formats/tweets/renderer.py`
- Single-word or two-word modules preferred: `db.py`, `quality.py`, `profiler.py`

**Functions:**
- Snake case throughout: `generate_tts()`, `_fetch_channel_by_id()`, `_group_into_phrases()`
- Public functions: no leading underscore
- Private/internal functions: single leading underscore prefix (`_resolve_channel()`, `_api_call()`)
- Descriptive verb-first naming: `fetch_channel()`, `rank_channel()`, `check_quality()`

**Variables:**
- Snake case: `channel_id`, `video_ids`, `profile_path`, `max_videos`
- Type-hint-aware: `response_data`, `word_timestamps`, `eligible`
- Clarity over brevity: `video_ids` not `v_ids`

**Types/Classes:**
- PascalCase for classes (minimal use; codebase favors functions)
- Type hints on all function parameters and returns (see Function Design section)
- Type aliases via dict[str, Any] and list patterns explicitly

**Constants:**
- UPPERCASE with underscores: `_MAX_VIDEOS = 50`, `_TEMPERATURE = 0.85`, `_MODEL = "claude-haiku-4-5-20251001"`
- Private constants use leading underscore: `_ELEVENLABS_BASE`, `_REQUIRED_KEYS`
- Module-level configuration constants at top after docstring

## Code Style

**Formatting:**
- No explicit linter/formatter config detected (no .pylintrc, .flake8, pyproject.toml)
- Implicit Python conventions observed:
  - 4-space indentation (standard Python)
  - Line breaks before section comments (60-character divider lines: `# -----------` pattern)
  - Blank lines separate logical sections within functions

**Linting:**
- No automated linting observed; code follows PEP 8 conventions by convention
- Type hints strictly enforced on all public functions

**Docstring Format:**
- Module docstrings at top: triple-quote with summary and "Public API" section
  ```python
  """
  module/name.py — Short description of purpose.

  Public API:
      function_name(params) -> return_type    (description)
  """
  ```
- Function docstrings: comprehensive, with Args, Returns, and Raises sections
- Example from `pipeline/tts.py`:
  ```python
  def generate_tts(text: str, output_dir: str) -> dict[str, Any]:
      """Generate TTS audio and word-level timestamps.

      Calls the ElevenLabs /with-timestamps endpoint, saves the MP3 audio
      and a JSON timestamp file into *output_dir*, then returns their paths
      along with the audio duration.

      Args:
          text: The text to convert to speech.
          output_dir: Directory where 'narration.mp3' and 'timestamps.json'
              will be saved (created if it doesn't exist).

      Returns:
          {
              "audio_path": str,
              "timestamps_path": str,
              "duration_seconds": float,
          }
      """
  ```

## Import Organization

**Order:**
1. Standard library imports: `json`, `logging`, `time`, `pathlib`, `typing`
2. Third-party imports: `requests`, `anthropic`, `google-api-python-client`, `playwright`
3. Local imports: `import config`, `from analysis.db import get_connection`

**Example from `analysis/transcripts.py`:**
```python
import http.cookiejar
import logging
import time
from pathlib import Path
from typing import Any

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

import config
from analysis.db import get_connection
```

**Path Aliases:**
- None detected; codebase uses relative imports within the project
- Local modules imported directly: `from pipeline.tts import generate_tts`

## Error Handling

**Patterns:**
- **Exponential backoff with retries**: Applied to external API calls (YouTube, ElevenLabs, Anthropic)
  ```python
  # From pipeline/tts.py
  for attempt in range(1, max_attempts + 1):
      try:
          resp = requests.post(url, headers=headers, json=payload, timeout=60)
          resp.raise_for_status()
          return resp.json()
      except requests.RequestException as exc:
          last_exc = exc
          logger.warning("Attempt %d failed: %s", attempt, exc)
          if attempt < max_attempts:
              wait = 2 ** attempt
              time.sleep(wait)
  raise RuntimeError(f"Failed after {max_attempts} attempts") from last_exc
  ```

- **Graceful degradation in main.py**: Content generation failures log and continue, never block pipeline
  ```python
  # From main.py _run_storytelling_pipeline()
  try:
      tts = generate_tts(story_text, str(workdir))
      # ... process
      return out
  except Exception as e:
      logger.error("Pipeline failed: %s", e)
      return None
  ```

- **Type-specific exception catching**: Catch specific exceptions, not bare `except:`
  ```python
  # From analysis/transcripts.py
  except (json.JSONDecodeError, TypeError):
      # handle parse error
  ```

- **Nested try blocks for protocol fallback**: YouTube transcript fetching tries multiple auth methods
  ```python
  try:
      transcript_list = _ytt_api.list(video_id)
      transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
      entries = transcript.fetch()
  except Exception:
      entries = _ytt_api.fetch(video_id)  # fallback
  ```

## Logging

**Framework:** Python's built-in `logging` module

**Pattern:**
- Logger instantiated per-module: `logger = logging.getLogger(__name__)`
- Configured centrally in `config.py` with console + file handlers
- Logging levels used appropriately:
  - `logger.info()`: Progress steps, completions, key decisions (150+ calls across codebase)
  - `logger.warning()`: Retries, degraded behavior, non-fatal issues
  - `logger.error()`: Failures, exceptions caught at boundary
  - `logger.debug()`: Verbose filtering (e.g., skipping too-young videos)

**Examples:**
```python
# Step progress
logger.info("[1/4] Fetching channel videos…")
logger.info("Fetched %d/50 videos from @%s (cap: %d)...", len(video_ids), channel_name, max_videos)

# Retry logging
logger.warning("YouTube API rate limit (attempt %d), retrying in %ds", attempt, wait)

# Completion
logger.info("Saved %d Shorts to database for channel %s", len(shorts), channel_name)
```

## Comments

**When to Comment:**
- Section dividers: `# -----------` lines mark logical blocks
- Algorithm explanation: Comments explain non-obvious logic (e.g., phrase grouping algorithm in `overlay.py`)
- Configuration: Constants have inline comments explaining purpose
  ```python
  PHRASE_MIN_WORDS = 1          # don't break on soft punctuation below this
  PHRASE_MAX_WORDS = 2          # hard cap; flush regardless
  PHRASE_MAX_DURATION_MS = 1500 # also flush if a phrase would span > 1.5 s
  ```

**JSDoc/Docstring:**
- All public functions have structured docstrings (Args, Returns, Raises)
- Private functions document purpose and behavior when non-obvious
- Module docstrings include "Public API" section listing exported functions

## Function Design

**Size:** Most functions are 15–50 lines
- Small, focused scope (one responsibility)
- Complex pipelines broken into 3–5 sequential steps
- Example: `_run_storytelling_pipeline()` in `main.py` calls 3 substeps (TTS → overlays → assemble)

**Parameters:**
- Explicit over implicit; all parameters passed rather than relying on global state
- Type hints required: `def fetch_channel(url_or_id: str, max_videos: int = _MAX_VIDEOS) -> str:`
- Defaults for non-critical params: `max_videos: int = _MAX_VIDEOS`

**Return Values:**
- Dict return for multiple related values: `{"audio_path": str, "timestamps_path": str, "duration_seconds": float}`
- Single-type returns preferred: strings for paths, ints for counts, dicts for structured data
- None used explicitly for "not found" or "failed" cases
- Tuples for fixed-size multi-value returns: `tuple[str, str, int]` for (id, name, count)

## Module Design

**Exports:**
- Public functions documented in module docstring "Public API" section
- Single entry point per module when possible (e.g., `generate_tts()` in `pipeline/tts.py`)
- Private functions prefixed with `_` to signal internal use

**Barrel Files:**
- `formats/__init__.py` and `analysis/__init__.py` are empty
- No barrel exports; modules imported directly by full path

**Cohesion:**
- Modules group by layer or domain: `pipeline/` (core processing), `formats/` (format-specific), `analysis/` (channel analysis)
- No deep nested imports; imports happen at function call site when not needed at module level (e.g., `from analysis.fetcher import fetch_channel` inside `cmd_analyze()`)

---

*Convention analysis: 2026-03-11*
