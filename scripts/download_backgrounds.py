"""
scripts/download_backgrounds.py — Download background gameplay videos via yt-dlp.

Downloads YouTube videos as MP4 into assets/backgrounds/<game>/.

Usage:
    # Download a single video
    python scripts/download_backgrounds.py --url "URL" --game "subway-surfers"

    # Download from a text file of URLs (one per line)
    python scripts/download_backgrounds.py --urls-file urls.txt --game "minecraft"

    # Dry run (print what would be downloaded)
    python scripts/download_backgrounds.py --url "URL" --game "subway-surfers" --dry-run
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

BACKGROUNDS_DIR = Path(__file__).parent.parent / "assets" / "backgrounds"


def check_ytdlp() -> None:
    result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        log.error("yt-dlp not found. Install it with: pip install yt-dlp")
        sys.exit(1)


def download(urls: list[str], game: str, dry_run: bool) -> None:
    """Download a list of URLs into assets/backgrounds/<game>/."""
    out_dir = BACKGROUNDS_DIR / game
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    out_template = str(out_dir / "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        # Best quality MP4 with merged audio
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "--merge-output-format", "mp4",
        "--output", out_template,
        "--no-overwrites",               # skip already-downloaded files
        "--ignore-errors",               # skip unavailable videos, keep going
        "--sleep-interval", "2",
    ]

    if dry_run:
        cmd += ["--simulate", "--print", "%(title)s — %(webpage_url)s"]

    cmd += urls

    log.info("Downloading %d URL(s) → %s", len(urls), out_dir)
    subprocess.run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download background gameplay videos")
    parser.add_argument("--game", required=True, help="Game name (used as subfolder, e.g. subway-surfers)")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Single YouTube URL to download")
    source.add_argument("--urls-file", type=Path, help="Text file with one URL per line")

    parser.add_argument("--dry-run", action="store_true", help="Print what would be downloaded without saving")
    args = parser.parse_args()

    check_ytdlp()

    if args.urls_file:
        if not args.urls_file.exists():
            log.error("File not found: %s", args.urls_file)
            sys.exit(1)
        urls = [u.strip() for u in args.urls_file.read_text().splitlines() if u.strip()]
    else:
        urls = [args.url]

    download(urls, args.game, args.dry_run)
    log.info("Done. Videos saved to: %s", BACKGROUNDS_DIR / args.game)


if __name__ == "__main__":
    main()
