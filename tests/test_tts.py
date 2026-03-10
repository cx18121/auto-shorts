"""
tests/test_tts.py — Standalone test for pipeline/tts.py.

Run from the project root:
    python tests/test_tts.py
"""

import json
import sys
from pathlib import Path

# Allow imports from project root regardless of working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

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

    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"  audio_path      : {result['audio_path']}")
    print(f"  timestamps_path : {result['timestamps_path']}")
    print(f"  duration_seconds: {result['duration_seconds']:.2f}s")

    # Show first few word timestamps
    timestamps = json.loads(Path(result["timestamps_path"]).read_text())
    print()
    print(f"Word timestamps ({len(timestamps)} total):")
    for entry in timestamps[:10]:
        print(f"  {entry['start_ms']:>6}ms – {entry['end_ms']:>6}ms  '{entry['word']}'")
    if len(timestamps) > 10:
        print(f"  … and {len(timestamps) - 10} more")

    # Basic sanity checks
    assert Path(result["audio_path"]).exists(), "Audio file missing!"
    assert Path(result["timestamps_path"]).exists(), "Timestamps file missing!"
    assert result["duration_seconds"] > 0, "Duration should be > 0"
    assert len(timestamps) > 0, "Timestamps list is empty!"

    print()
    print("All checks passed.")


if __name__ == "__main__":
    main()
