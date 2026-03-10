"""
main.py — Automated Shorts Pipeline CLI.

Commands:
    analyze  --channels URL [URL ...]  [--visual]
    generate --format storytelling|tweets  --profile PATH  --count N  [--thread]
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import config  # loads .env, sets up logging
from pipeline.tts import generate_tts
from pipeline.overlay import generate_ass
from formats.storytelling.assembler import assemble_video

logger = logging.getLogger(__name__)

_DEFAULT_BACKGROUND = "assets/backgrounds/subwaysurfers.mp4"
_MAX_QUALITY_RETRIES = 3


# ===========================================================================
# CLI
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated YouTube Shorts / Instagram Reels pipeline"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Fetch and analyse YouTube channel(s)")
    p_analyze.add_argument("--channels", nargs="+", required=True,
                            metavar="URL", help="Channel URLs or @handles")
    p_analyze.add_argument("--visual", action="store_true",
                            help="Include visual frame/thumbnail analysis (slower, uses Claude vision)")

    # --- generate ---
    p_gen = sub.add_parser("generate", help="Generate and produce videos")
    p_gen.add_argument("--format", choices=["storytelling", "tweets"], required=True)
    p_gen.add_argument("--profile", metavar="PATH",
                        help="Path to style profile JSON (not needed with --scrape)")
    p_gen.add_argument("--count", type=int, default=1)
    p_gen.add_argument("--thread", action="store_true",
                        help="Generate thread-style tweet videos (tweets format only)")
    p_gen.add_argument("--scrape", action="store_true",
                        help="Use real tweets scraped from X instead of AI-generated ones")
    p_gen.add_argument("--min-likes", type=int, default=500,
                        help="Minimum likes when scraping (default: 500)")

    # --- setup-twitter ---
    p_tw = sub.add_parser("setup-twitter", help="Add a Twitter/X account for scraping")
    p_tw.add_argument("--username", required=True, help="Twitter @handle (no @)")
    p_tw.add_argument("--password", required=True)
    p_tw.add_argument("--email",    required=True)
    p_tw.add_argument("--email-password", default=None,
                       help="Email password if different from Twitter password")

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args.channels, args.visual)
    elif args.command == "generate":
        scrape = getattr(args, "scrape", False)
        if not scrape and not args.profile:
            logger.error("--profile is required unless --scrape is set")
            sys.exit(1)
        cmd_generate(args.format, args.profile, args.count,
                     getattr(args, "thread", False),
                     scrape=scrape,
                     min_likes=getattr(args, "min_likes", 500))
    elif args.command == "setup-twitter":
        cmd_setup_twitter(args.username, args.password, args.email,
                          getattr(args, "email_password", None))


# ===========================================================================
# analyze command
# ===========================================================================

def cmd_analyze(channel_urls: list[str], visual: bool) -> None:
    from analysis.fetcher import fetch_channel
    from analysis.transcripts import fetch_transcripts
    from analysis.ranker import rank_channel
    from analysis.profiler import build_profile

    for url in channel_urls:
        logger.info("=" * 60)
        logger.info("ANALYZING CHANNEL: %s", url)
        logger.info("=" * 60)

        t0 = time.monotonic()

        # Step 1: fetch metadata + Shorts
        logger.info("[1/4] Fetching channel videos…")
        channel_id = fetch_channel(url)

        # Step 2: fetch transcripts
        logger.info("[2/4] Fetching transcripts…")
        fetched = fetch_transcripts(channel_id)
        logger.info("Transcripts: %d fetched", fetched)

        # Step 3: rank
        logger.info("[3/4] Ranking performance…")
        aggregates = rank_channel(channel_id)

        # Step 4 (optional): visual analysis
        if visual:
            from analysis.visual import analyse_visuals
            logger.info("[4/4] Running visual analysis (this may take a while)…")
            n_visual = analyse_visuals(channel_id)
            logger.info("Visual analysis done: %d videos", n_visual)
        else:
            logger.info("[4/4] Skipping visual analysis (use --visual to enable)")

        # Step 5: build style profile
        logger.info("[5/5] Building style profile…")
        profile_path = build_profile(channel_id, aggregates, include_visual=visual)

        elapsed = time.monotonic() - t0
        logger.info("=" * 60)
        logger.info("ANALYSIS COMPLETE in %.1fs", elapsed)
        logger.info("Profile saved → %s", profile_path)
        logger.info("=" * 60)
        print(f"\nProfile saved: {profile_path}")


# ===========================================================================
# generate command
# ===========================================================================

def cmd_setup_twitter(username: str, password: str, email: str,
                       email_password: str | None) -> None:
    from formats.tweets.scraper import setup_account
    setup_account(username, password, email, email_password)
    print(f"Twitter account @{username} added successfully.")


def cmd_generate(fmt: str, profile_path: str | None, count: int, thread: bool,
                 scrape: bool = False, min_likes: int = 500) -> None:
    profile = None
    if profile_path:
        if not Path(profile_path).exists():
            logger.error("Profile not found: %s", profile_path)
            sys.exit(1)
        profile = json.loads(Path(profile_path).read_text())
        logger.info("Generating %d %s video(s) from profile: %s",
                    count, fmt, Path(profile_path).name)
    else:
        logger.info("Generating %d %s video(s) (scrape mode)", count, fmt)

    produced: list[str] = []

    if fmt == "storytelling":
        produced = _generate_storytelling(count, profile, profile_path)
    elif fmt == "tweets":
        if scrape:
            produced = _scrape_tweets(count, min_likes)
        else:
            produced = _generate_tweets(count, profile, profile_path, thread)

    print(f"\nGenerated {len(produced)}/{count} videos:")
    for p in produced:
        print(f"  {p}")


# ---------------------------------------------------------------------------
# Storytelling pipeline
# ---------------------------------------------------------------------------

def _generate_storytelling(
    count: int, profile: dict, profile_path: str
) -> list[str]:
    from formats.storytelling.generator import generate_story
    from formats.storytelling.quality import check_quality

    background = _pick_background()
    produced: list[str] = []

    for i in range(count):
        logger.info("-" * 50)
        logger.info("STORY %d/%d", i + 1, count)

        story = _generate_with_quality(
            generate_fn=lambda: generate_story(profile),
            quality_fn=lambda s: check_quality(s, profile),
            label="story",
        )
        if story is None:
            logger.error("Story %d/%d rejected after all retries, skipping", i + 1, count)
            continue

        video_path = _run_storytelling_pipeline(story["story_text"], background)
        if video_path:
            produced.append(video_path)
            logger.info("Story %d/%d done → %s", i + 1, count, video_path)

    return produced


def _run_storytelling_pipeline(story_text: str, background: str) -> str | None:
    run_id  = int(time.time())
    workdir = config.OUTPUT_DIR / str(run_id)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("[1/3] TTS…")
        tts = generate_tts(story_text, str(workdir))

        logger.info("[2/3] Subtitles…")
        subs = generate_ass(tts["timestamps_path"], str(workdir / "subtitles.ass"))

        logger.info("[3/3] Assembling…")
        out = assemble_video(
            background_path=background,
            audio_path=tts["audio_path"],
            subtitles_path=subs,
            output_path=str(workdir / "final.mp4"),
            duration_seconds=tts["duration_seconds"],
        )
        return out
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Tweet pipeline
# ---------------------------------------------------------------------------

def _generate_tweets(
    count: int, profile: dict, profile_path: str, thread: bool
) -> list[str]:
    from formats.tweets.generator import generate_tweet, generate_thread
    from formats.tweets.quality import check_quality
    from formats.tweets.renderer import render_tweet
    from formats.tweets.assembler import assemble_tweet_video

    produced: list[str] = []

    if thread:
        # generate_thread returns list-of-threads; each thread → one video
        from formats.tweets.generator import generate_thread as gen_thread
        threads = gen_thread(count, profile_path)
        for i, tweet_list in enumerate(threads, 1):
            logger.info("-" * 50)
            logger.info("THREAD %d/%d (%d tweets)", i, count, len(tweet_list))
            # Use the first tweet as the main one for rendering / TTS
            tweet = tweet_list[0]
            video = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            if video:
                produced.append(video)
    else:
        for i in range(count):
            logger.info("-" * 50)
            logger.info("TWEET %d/%d", i + 1, count)

            tweet = _generate_with_quality(
                generate_fn=lambda: generate_tweet(profile),
                quality_fn=lambda t: check_quality(t, profile),
                label="tweet",
            )
            if tweet is None:
                logger.error("Tweet %d/%d rejected, skipping", i + 1, count)
                continue

            video = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            if video:
                produced.append(video)
                logger.info("Tweet %d/%d done → %s", i + 1, count, video)

    return produced


def _run_tweet_pipeline(tweet: dict, render_fn, assemble_fn) -> str | None:
    run_id  = int(time.time())
    workdir = config.OUTPUT_DIR / str(run_id)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("[1/3] Rendering tweet image…")
        img_path = render_fn(tweet, str(workdir / "tweet.png"))

        logger.info("[2/3] TTS…")
        tts = generate_tts(tweet["tweet_text"], str(workdir))

        logger.info("[3/3] Assembling…")
        out = assemble_fn(
            image_path=img_path,
            audio_path=tts["audio_path"],
            output_path=str(workdir / "final.mp4"),
            duration_seconds=tts["duration_seconds"],
        )
        return out
    except Exception as e:
        logger.error("Tweet pipeline failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Scrape pipeline (real tweets)
# ---------------------------------------------------------------------------

def _scrape_tweets(count: int, min_likes: int) -> list[str]:
    from formats.tweets.scraper import scrape_top_tweets
    from formats.tweets.renderer import render_tweet
    from formats.tweets.assembler import assemble_tweet_video

    logger.info("Scraping top tweets (need %d, min_likes=%d)…", count, min_likes)
    tweets = scrape_top_tweets(n=count * 3, min_likes=min_likes)
    if not tweets:
        logger.error("No tweets scraped — have you run setup-twitter?")
        return []

    produced: list[str] = []
    for tweet in tweets:
        if len(produced) >= count:
            break

        logger.info("-" * 50)
        logger.info("TWEET %d/%d — @%s (%d likes)",
                    len(produced) + 1, count, tweet["username"], tweet["likes"])

        run_id  = int(time.time())
        workdir = config.OUTPUT_DIR / str(run_id)
        workdir.mkdir(parents=True, exist_ok=True)

        try:
            logger.info("[1/3] Rendering tweet…")
            img_path = render_tweet(tweet, str(workdir / "tweet.png"))

            logger.info("[2/3] TTS…")
            tts = generate_tts(tweet["text"], str(workdir))

            logger.info("[3/3] Assembling…")
            out = assemble_tweet_video(
                image_path=img_path,
                audio_path=tts["audio_path"],
                output_path=str(workdir / "final.mp4"),
                duration_seconds=tts["duration_seconds"],
            )
            produced.append(out)
            logger.info("Done → %s", out)
        except Exception as e:
            logger.error("Scrape pipeline failed for %s: %s", tweet["url"], e)

    return produced


# ---------------------------------------------------------------------------
# Quality retry wrapper
# ---------------------------------------------------------------------------

def _generate_with_quality(generate_fn, quality_fn, label: str):
    """Generate content, quality-check it, retry up to MAX_QUALITY_RETRIES times."""
    for attempt in range(1, _MAX_QUALITY_RETRIES + 1):
        try:
            content = generate_fn()
            quality = quality_fn(content)
            logger.info(
                "%s attempt %d/%d: overall=%.1f passed=%s",
                label, attempt, _MAX_QUALITY_RETRIES,
                quality.get("overall", 0), quality.get("passed"),
            )
            if quality.get("passed"):
                return content
            logger.info("Rejected (%s), retrying…", quality.get("reason", "")[:80])
        except Exception as e:
            logger.warning("%s generation attempt %d failed: %s", label, attempt, e)
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_background() -> str:
    bg_dir = config.ASSETS_DIR / "backgrounds"
    clips  = [p for p in bg_dir.glob("*.mp4") if "test" not in p.name]
    if not clips:
        clips = list(bg_dir.glob("*.mp4"))
    if not clips:
        logger.error("No background clips found in %s", bg_dir)
        sys.exit(1)
    return str(clips[0])


if __name__ == "__main__":
    main()
