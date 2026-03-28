# Testing Patterns

**Analysis Date:** 2026-03-11

## Test Framework

**Runner:**
- Custom Python test scripts (no pytest/unittest framework detected)
- Tests are standalone scripts in `tests/` directory, runnable via `python tests/test_NAME.py`

**Assertion Library:**
- Python built-in `assert` statements only

**Run Commands:**
```bash
python tests/test_tts.py              # Run TTS module test
python tests/test_assembler.py        # Run video assembly test
```

## Test File Organization

**Location:**
- Co-located in dedicated `tests/` directory separate from source
- Test files: `tests/test_tts.py`, `tests/test_assembler.py`, `tests/__init__.py`

**Naming:**
- `test_MODULENAME.py` convention: `test_tts.py` tests `pipeline/tts.py`

**Structure:**
```
tests/
├── __init__.py
├── test_tts.py          # Tests pipeline.tts.generate_tts()
└── test_assembler.py    # Tests formats.storytelling.assembler.assemble_video()
```

## Test Structure

**Suite Organization:**
Tests are standalone scripts with a `main()` function that:
1. Sets up test constants/fixtures
2. Calls the function under test
3. Validates outputs with assertions
4. Prints progress and results

Example structure from `test_tts.py`:
```python
"""
tests/test_tts.py — Standalone test for pipeline/tts.py.

Run from the project root:
    python tests/test_tts.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # Allow imports from project root

from pipeline.tts import generate_tts

TEST_TEXT = (
    "A man walked into a bar and ordered a drink. "
    "The bartender looked at him and said, you're not from around here, are you?"
)
OUTPUT_DIR = "output/test"


def main() -> None:
    print("=" * 60)
    print("TTS MODULE TEST")
    print("=" * 60)
    print(f"Text : {TEST_TEXT}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    result = generate_tts(TEST_TEXT, OUTPUT_DIR)

    # Validation
    assert Path(result["audio_path"]).exists(), "Audio file missing!"
    assert Path(result["timestamps_path"]).exists(), "Timestamps file missing!"

    print("All checks passed.")


if __name__ == "__main__":
    main()
```

**Patterns:**
- Module under test imported at top
- Test data defined as module-level constants
- Single `main()` function as entry point
- Print progress before assertions (observability during manual runs)
- No test discovery framework; tests run individually

## Test Types

**Unit Tests:**
- Scope: Individual module functions (`generate_tts()`, `assemble_video()`)
- Approach: Call the function with test inputs, verify outputs exist and have correct structure
- Example from `test_tts.py`: Calls `generate_tts()`, checks audio file exists, checks timestamps JSON parses, validates duration > 0

**Integration Tests:**
- Scope: Multi-step pipelines (TTS → overlays → video assembly)
- Approach: `test_assembler.py` depends on outputs from `test_tts.py`
  ```python
  BACKGROUND  = "assets/backgrounds/test_bg.mp4"
  AUDIO       = "output/test/narration.mp3"      # From test_tts.py
  SUBTITLES   = "output/test/subtitles.ass"      # From overlay.py
  OUTPUT      = "output/test/final.mp4"
  ```
- Validates that combined pipeline produces a valid video file

**E2E Tests:**
- Not detected in codebase
- Manual CLI testing via commands: `python main.py analyze --channels URL`, `python main.py generate --format storytelling`

## Fixtures and Factories

**Test Data:**
- Inline string constants: `TEST_TEXT = "A man walked into a bar..."`
- Hardcoded paths in test modules: `OUTPUT_DIR = "output/test"`, `BACKGROUND = "assets/backgrounds/test_bg.mp4"`
- No fixture factory objects; raw data passed to functions

**Location:**
- Test data defined at module level in each test file
- Shared test assets (e.g., background video) referenced from `assets/` directory

## Coverage

**Requirements:** None enforced
- No coverage tooling detected (no pytest-cov, no coverage.py config)
- No minimum coverage threshold

**View Coverage:** Not applicable (no automated coverage tracking)

## Assertions

**Validation Patterns:**
- File existence: `assert Path(result["audio_path"]).exists(), "Audio file missing!"`
- Value constraints: `assert result["duration_seconds"] > 0, "Duration should be > 0"`
- Collection non-empty: `assert len(timestamps) > 0, "Timestamps list is empty!"`
- File size sanity checks: `assert out.stat().st_size > 10_000, "Output file suspiciously small"`

**Example from `test_assembler.py`:**
```python
# Validate inputs exist
for label, path in [("background", BACKGROUND), ("audio", AUDIO), ("subtitles", SUBTITLES)]:
    exists = Path(path).exists()
    print(f"  {label:12}: {path}  {'OK' if exists else 'MISSING'}")
    if not exists:
        print(f"\nERROR: {path} is missing. Run test_tts.py first.")
        sys.exit(1)

# Validate output
assert out.exists(), "Output file missing!"
assert out.stat().st_size > 10_000, "Output file suspiciously small"
```

## Manual Test Workflow

**Current Practice:**
1. Tests are manual, run sequentially
2. Test interdependency managed by running in order: `test_tts.py` → `test_assembler.py`
3. Output files written to `output/test/` directory
4. Developer inspects logs and result files manually

**Example workflow:**
```bash
# 1. Test TTS generation
python tests/test_tts.py
# → Creates: output/test/narration.mp3, output/test/timestamps.json

# 2. Test video assembly (depends on test_tts output)
python tests/test_assembler.py
# → Creates: output/test/final.mp4
```

## Limitations and Gaps

**No automated testing:**
- No continuous integration setup detected
- No test framework (pytest, unittest) for parallel runs or discovery
- No mocking of external APIs (ElevenLabs, YouTube, Anthropic)
  - Tests actually call real APIs if run

**Limited scope:**
- Only 2 test modules covering ~2 core functions
- No tests for: analysis modules, tweet generation, tweet rendering, scraper, CLI argument parsing
- No negative test cases (error handling, malformed input)
- No performance benchmarks

**Recommended for future phases:**
- Add pytest with fixtures and parameterization
- Mock external API calls to avoid test failures due to service outages
- Add tests for error handling paths (bad API keys, network failures, invalid JSON)
- Add CLI integration tests
- Add tweet rendering tests (compare image output)

---

*Testing analysis: 2026-03-11*
