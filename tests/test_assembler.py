"""
tests/test_assembler.py — Standalone test for formats/storytelling/assembler.py.

Requires:
  - output/test/narration.mp3    (from test_tts.py)
  - output/test/subtitles.ass    (from overlay.py)
  - assets/backgrounds/test_bg.mp4  (any video file)

Run from project root:
    python tests/test_assembler.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from formats.storytelling.assembler import assemble_video

BACKGROUND  = "assets/backgrounds/test_bg.mp4"
AUDIO       = "output/test/narration.mp3"
SUBTITLES   = "output/test/subtitles.ass"
OUTPUT      = "output/test/final.mp4"


def main() -> None:
    print("=" * 60)
    print("ASSEMBLER TEST")
    print("=" * 60)

    for label, path in [("background", BACKGROUND), ("audio", AUDIO), ("subtitles", SUBTITLES)]:
        exists = Path(path).exists()
        print(f"  {label:12}: {path}  {'OK' if exists else 'MISSING'}")
        if not exists:
            print(f"\nERROR: {path} is missing. Run test_tts.py first.")
            sys.exit(1)

    print(f"\nOutput  : {OUTPUT}")
    print()

    result = assemble_video(BACKGROUND, AUDIO, SUBTITLES, OUTPUT)

    out = Path(result)
    size_mb = out.stat().st_size / 1_048_576
    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"  output : {result}")
    print(f"  size   : {size_mb:.1f} MB")

    assert out.exists(), "Output file missing!"
    assert out.stat().st_size > 10_000, "Output file suspiciously small"
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
