"""
commands/generate.py — Video generation command and all supporting pipeline helpers.

Public API:
    cmd_generate(fmt, profile_path, count, thread, ...)
"""

import json
import logging
import random
import subprocess
import sys
import time
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_MAX_QUALITY_RETRIES = 3
_SILENT_DURATION     = 10.0   # seconds of silent audio for --no-audio testing
_DEFAULT_BACKGROUND  = "assets/backgrounds/subwaysurfers.mp4"


# ===========================================================================
# Public command entry point
# ===========================================================================

def cmd_generate(
    fmt: str,
    profile_path: str | None,
    count: int,
    thread: bool,
    scrape: bool = False,
    min_likes: int = 500,
    channel_cfg=None,
    from_backlog: bool = False,
    pick: bool = False,
    no_audio: bool = False,
    keep_backlog: bool = False,
) -> None:
    profile = None
    if profile_path:
        if not Path(profile_path).exists():
            logger.error("Profile not found: %s", profile_path)
            sys.exit(1)
        profile = json.loads(Path(profile_path).read_text())
        logger.info("Generating %d %s video(s) from profile: %s",
                    count, fmt, Path(profile_path).name)
    elif from_backlog:
        logger.info("Generating %d %s video(s) from backlog", count, fmt)
    else:
        logger.info("Generating %d %s video(s) (scrape mode)", count, fmt)

    if fmt == "storytelling":
        if from_backlog:
            produced = _generate_storytelling_from_backlog(
                count, channel_cfg, pick=pick,
                no_audio=no_audio, keep_backlog=keep_backlog,
            )
        else:
            produced = _generate_storytelling(count, profile, profile_path, no_audio=no_audio)
    else:  # tweets
        if scrape:
            produced = _scrape_tweets(count, min_likes)
        elif from_backlog or pick:
            produced = _generate_tweets_from_backlog(
                count, channel_cfg, pick=pick,
                no_audio=no_audio, keep_backlog=keep_backlog,
            )
        else:
            produced = _generate_tweets(count, profile, profile_path, thread)

    print(f"\nGenerated {len(produced)}/{count} videos:")
    for p in produced:
        print(f"  {p}")


# ===========================================================================
# Storytelling pipeline
# ===========================================================================

def _generate_storytelling(
    count: int,
    profile: dict,
    profile_path: str,
    no_audio: bool = False,
) -> list[str]:
    from formats.storytelling.generator import generate_story
    from formats.storytelling.quality import check_quality

    background = _pick_background()
    produced: list[str] = []

    for i in range(count):
        logger.info("-" * 50)
        logger.info("STORY %d/%d", i + 1, count)

        story = _generate_with_quality(
            generate_fn=lambda feedback="": generate_story(profile, feedback=feedback),
            quality_fn=lambda s: check_quality(s, profile),
            label="story",
        )
        if story is None:
            logger.error("Story %d/%d rejected after all retries, skipping", i + 1, count)
            continue

        video_path = _run_storytelling_pipeline(story["story_text"], background, no_audio=no_audio)
        if video_path:
            _save_video_metadata(video_path, story["story_text"], "storytelling")
            produced.append(video_path)
            logger.info("Story %d/%d done → %s", i + 1, count, video_path)

    return produced


def _generate_storytelling_from_backlog(
    count: int,
    channel_cfg,
    pick: bool = False,
    no_audio: bool = False,
    keep_backlog: bool = False,
) -> list[str]:
    """Pull approved Reddit posts from the backlog and produce story videos."""
    from analysis.db import get_connection
    from pipeline.backlog import get_approved_stories, mark_story_used
    from formats.storytelling.generator import adapt_reddit_post
    from formats.storytelling.quality import check_quality

    slug    = channel_cfg.slug if channel_cfg else ""
    profile = _load_style_profile(channel_cfg)

    conn = get_connection()
    try:
        rows = get_approved_stories(conn, slug)
        if not rows:
            logger.warning("No approved stories in backlog for [%s]", slug)
            return []

        if pick:
            rows = _interactive_pick(rows, count, "storytelling")
            if not rows:
                print("No stories selected.")
                return []

        logger.info("Found %d approved story/stories in backlog for [%s]", len(rows), slug)
        background = _pick_background()
        produced: list[str] = []

        for i, row in enumerate(rows):
            if len(produced) >= count:
                break

            logger.info("-" * 50)
            logger.info("BACKLOG STORY %d/%d", len(produced) + 1, count)

            post = {
                "title":     row["title"],
                "body":      row["body"],
                "subreddit": row["subreddit"],
                "score":     row["score"],
            }

            story = _generate_with_quality(
                generate_fn=lambda p=post, feedback="": adapt_reddit_post(p, slug, profile, feedback=feedback),
                quality_fn=lambda s: check_quality(s, profile) if profile else {"passed": True, "overall": 10.0},
                label="story-from-backlog",
            )
            if story is None:
                logger.error("Backlog story %d rejected after all retries, skipping", i + 1)
                continue

            video_path = _run_storytelling_pipeline(story["story_text"], background, no_audio=no_audio)
            if video_path:
                _save_video_metadata(
                    video_path, story["story_text"], "storytelling",
                    channel_cfg.hashtags if channel_cfg else [],
                )
                if not keep_backlog:
                    mark_story_used(conn, row["id"])
                    conn.commit()
                produced.append(video_path)
                logger.info("Backlog story %d done → %s", len(produced), video_path)

        return produced
    finally:
        conn.close()


# ===========================================================================
# Tweet pipeline
# ===========================================================================

def _generate_tweets(
    count: int,
    profile: dict,
    profile_path: str,
    thread: bool,
) -> list[str]:
    from formats.tweets.generator import generate_tweet, generate_thread
    from formats.tweets.quality import check_quality
    from formats.tweets.renderer import render_tweet
    from formats.tweets.assembler import assemble_tweet_video

    produced: list[str] = []

    if thread:
        threads = generate_thread(count, profile_path)
        for i, tweet_list in enumerate(threads, 1):
            logger.info("-" * 50)
            logger.info("THREAD %d/%d (%d tweets)", i, count, len(tweet_list))
            tweet = tweet_list[0]
            video = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            if video:
                _save_video_metadata(video, tweet["tweet_text"], "tweets")
                produced.append(video)
    else:
        for i in range(count):
            logger.info("-" * 50)
            logger.info("TWEET %d/%d", i + 1, count)

            tweet = _generate_with_quality(
                generate_fn=lambda feedback="": generate_tweet(profile, feedback=feedback),
                quality_fn=lambda t: check_quality(t, profile),
                label="tweet",
            )
            if tweet is None:
                logger.error("Tweet %d/%d rejected, skipping", i + 1, count)
                continue

            video = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            if video:
                _save_video_metadata(video, tweet["tweet_text"], "tweets")
                produced.append(video)
                logger.info("Tweet %d/%d done → %s", i + 1, count, video)

    return produced


def _generate_tweets_from_backlog(
    count: int,
    channel_cfg,
    pick: bool = False,
    no_audio: bool = False,
    keep_backlog: bool = False,
) -> list[str]:
    """Pull approved tweets from the backlog and produce tweet videos."""
    from analysis.db import get_connection
    from pipeline.backlog import get_approved_tweets, mark_used
    from formats.tweets.renderer import render_tweet
    from formats.tweets.assembler import assemble_tweet_video

    slug = channel_cfg.slug if channel_cfg else ""

    conn = get_connection()
    try:
        rows = get_approved_tweets(conn, slug)
        if not rows:
            logger.warning("No approved tweets in backlog for [%s]", slug)
            return []

        if pick:
            rows = _interactive_pick(rows, count, "tweets")
            if not rows:
                print("No tweets selected.")
                return []

        logger.info("Found %d approved tweet(s) in backlog for [%s]", len(rows), slug)
        produced: list[str] = []

        for i, row in enumerate(rows):
            if len(produced) >= count:
                break

            logger.info("-" * 50)
            logger.info("BACKLOG TWEET %d/%d — @%s (%d likes)",
                        len(produced) + 1, count, row["username"], row["likes"])

            tweet = {
                "tweet_id":   row["tweet_id"],
                "tweet_text": row["tweet_text"],
                "username":   row["username"],
                "likes":      row["likes"],
                "retweets":   row["retweets"],
            }
            video_path = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            if video_path:
                _save_video_metadata(video_path, row["tweet_text"], "tweets")
                if not keep_backlog:
                    mark_used(conn, "backlog_tweets", row["tweet_id"])
                produced.append(video_path)
                logger.info("Tweet %d/%d done → %s", len(produced), count, video_path)
            else:
                logger.error("Backlog tweet %d failed, skipping", i + 1)

        return produced
    finally:
        conn.close()


def _scrape_tweets(count: int, min_likes: int) -> list[str]:
    """Scrape tweets from X and immediately produce videos (bypasses backlog)."""
    from formats.tweets.scraper import scrape_top_tweets
    from formats.tweets.renderer import render_tweet
    from formats.tweets.assembler import assemble_tweet_video

    logger.info("Scraping top tweets (need %d, min_likes=%d)…", count, min_likes)
    raw_tweets = scrape_top_tweets(n=count * 3, min_likes=min_likes)
    if not raw_tweets:
        logger.error("No tweets scraped — have you configured X cookies?")
        return []

    produced: list[str] = []
    for raw in raw_tweets:
        if len(produced) >= count:
            break

        logger.info("-" * 50)
        logger.info("TWEET %d/%d — @%s (%d likes)",
                    len(produced) + 1, count, raw["username"], raw["likes"])

        # Normalise scraper key (text) to the shared key (tweet_text)
        tweet = {
            "tweet_text": raw["text"],
            "username":   raw["username"],
            "likes":      raw["likes"],
            "retweets":   raw.get("retweets", 0),
        }
        video_path = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
        if video_path:
            _save_video_metadata(video_path, tweet["tweet_text"], "tweets")
            produced.append(video_path)
            logger.info("Done → %s", video_path)
        else:
            logger.error("Scrape pipeline failed for %s", raw.get("url", ""))

    return produced


# ===========================================================================
# Shared pipeline runners
# ===========================================================================

def _run_storytelling_pipeline(
    story_text: str,
    background: str,
    no_audio: bool = False,
) -> str | None:
    """TTS → subtitles → assemble. Returns output path or None on failure."""
    from pipeline.tts import generate_tts
    from pipeline.overlay import generate_ass
    from formats.storytelling.assembler import assemble_video, AUDIO_SPEED

    run_id  = int(time.time())
    workdir = config.OUTPUT_DIR / str(run_id)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        if no_audio:
            logger.info("[1/4] Generating silent audio (--no-audio)…")
            tts = _generate_silent_audio(str(workdir))
        else:
            logger.info("[1/4] TTS…")
            tts = generate_tts(story_text, str(workdir))

        logger.info("[2/4] Subtitles…")
        subs = generate_ass(
            tts["timestamps_path"],
            str(workdir / "subtitles.ass"),
            speed_factor=AUDIO_SPEED,
        )

        logger.info("[3/4] Assembling…")
        out = assemble_video(
            background_path=background,
            audio_path=tts["audio_path"],
            subtitles_path=subs,
            output_path=str(workdir / "final.mp4"),
            duration_seconds=tts["duration_seconds"],
        )
        return out
    except Exception as e:
        logger.error("Storytelling pipeline failed: %s", e)
        return None


def _run_tweet_pipeline(tweet: dict, render_fn, assemble_fn) -> str | None:
    """Render → TTS → assemble. Returns output path or None on failure."""
    from pipeline.tts import generate_tts

    run_id  = int(time.time())
    workdir = config.OUTPUT_DIR / str(run_id)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("[1/3] Rendering tweet image…")
        img_path = render_fn(tweet, str(workdir / "tweet.png"))

        logger.info("[2/3] TTS…")
        tts_script = f"@{tweet.get('username', '')} says: {tweet['tweet_text']}"
        tts = generate_tts(tts_script, str(workdir))

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


# ===========================================================================
# Shared helpers
# ===========================================================================

def _generate_with_quality(generate_fn, quality_fn, label: str):
    """Generate content, quality-check it, retry up to _MAX_QUALITY_RETRIES times.

    The rejection reason from each failed attempt is passed back to generate_fn
    as feedback so the generator can correct its mistakes.
    """
    feedback = ""
    for attempt in range(1, _MAX_QUALITY_RETRIES + 1):
        try:
            content = generate_fn(feedback=feedback)
            quality = quality_fn(content)
            logger.info(
                "%s attempt %d/%d: overall=%.1f passed=%s",
                label, attempt, _MAX_QUALITY_RETRIES,
                quality.get("overall", 0), quality.get("passed"),
            )
            if quality.get("passed"):
                return content
            feedback = quality.get("reason", "")
            logger.info("Rejected (%s), retrying with feedback…", feedback[:80])
        except Exception as e:
            logger.warning("%s generation attempt %d failed: %s", label, attempt, e)
    return None


def _interactive_pick(rows: list, max_picks: int, fmt: str) -> list:
    """Display approved backlog items and let the user choose which to produce."""
    if fmt == "storytelling":
        print(f"\n{'#':<4} {'Score':<8} {'Words':<7} {'Subreddit':<22} Title")
        print("-" * 90)
        for i, row in enumerate(rows, 1):
            title      = row["title"][:50] + ("…" if len(row["title"]) > 50 else "")
            word_count = len(row["body"].split()) if row["body"] else 0
            print(f"{i:<4} {row['score']:<8} {word_count:<7} r/{row['subreddit']:<20} {title}")
    else:  # tweets
        print(f"\n{'#':<4} {'Likes':<8} {'RT':<6} {'User':<20} Tweet")
        print("-" * 90)
        for i, row in enumerate(rows, 1):
            preview = row["tweet_text"][:50] + ("…" if len(row["tweet_text"]) > 50 else "")
            print(f"{i:<4} {row['likes']:<8} {row['retweets']:<6} @{row['username']:<19} {preview}")

    print(f"\nEnter numbers to select (comma-separated, max {max_picks}).")
    print("Example: 1,3,5  or just: 2")
    try:
        choice = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        return []

    if not choice:
        return []

    selected = []
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(rows):
                selected.append(rows[idx])
    return selected[:max_picks]


def _load_style_profile(channel_cfg) -> dict | None:
    """Load the style profile JSON for a channel, or return None if not configured."""
    if not channel_cfg or not channel_cfg.style_profile:
        return None
    profile_path = Path(channel_cfg.style_profile)
    if not profile_path.exists():
        logger.warning("style_profile path not found: %s — continuing without profile", profile_path)
        return None
    try:
        profile = json.loads(profile_path.read_text())
        logger.info("Loaded style profile: %s", profile_path)
        return profile
    except Exception as e:
        logger.warning("Failed to load style profile %s: %s — continuing without profile", profile_path, e)
        return None


def _pick_background() -> str:
    """Return a random background clip from assets/backgrounds/."""
    bg_dir = config.ASSETS_DIR / "backgrounds"
    exts   = ("**/*.mp4", "**/*.webm", "**/*.mov", "**/*.mkv")
    clips  = [p for ext in exts for p in bg_dir.glob(ext)
              if "test" not in p.name and not p.name.endswith(".part")]
    if not clips:
        clips = [p for ext in exts for p in bg_dir.glob(ext) if not p.name.endswith(".part")]
    if not clips:
        logger.error("No background clips found in %s", bg_dir)
        sys.exit(1)
    chosen = random.choice(clips)
    logger.info("Selected background clip: %s", chosen.name)
    return str(chosen)


def _save_video_metadata(
    video_path: str,
    content_text: str,
    format_type: str,
    niche_hashtags: list[str] | None = None,
) -> None:
    """Generate title/description/hashtags and save a .txt file next to the video."""
    from pipeline.upload import generate_upload_metadata, save_metadata_file
    try:
        metadata = generate_upload_metadata(content_text, niche_hashtags or [], format_type)
        save_metadata_file(video_path, metadata)
    except Exception as e:
        logger.warning("Failed to generate upload metadata: %s", e)


def _generate_silent_audio(output_dir: str) -> dict:
    """Generate a silent MP3 and dummy timestamps for --no-audio testing."""
    out            = Path(output_dir)
    audio_path     = out / "narration.mp3"
    timestamps_path = out / "timestamps.json"

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "anullsrc=r=44100:cl=mono", "-t", str(_SILENT_DURATION),
         "-c:a", "libmp3lame", "-b:a", "128k", str(audio_path)],
        capture_output=True, check=True,
    )

    words = []
    for i in range(int(_SILENT_DURATION / 2)):
        words.append({"word": "TEST", "start_ms": i * 2000, "end_ms": i * 2000 + 500})
    timestamps_path.write_text(json.dumps(words))

    return {
        "audio_path":      str(audio_path),
        "timestamps_path": str(timestamps_path),
        "duration_seconds": _SILENT_DURATION,
    }
