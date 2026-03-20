"""
commands/generate.py — Video generation command and all supporting pipeline helpers.

Public API:
    cmd_generate(fmt, count, thread, ...)
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
    count: int,
    thread: bool,
    scrape: bool = False,
    min_likes: int = 500,
    channel_cfg=None,
    from_backlog: bool = False,
    pick: bool = False,
    no_audio: bool = False,
    keep_backlog: bool = False,
    pick_background: bool = False,
    multi_bg: bool = False,
) -> None:
    if from_backlog:
        logger.info("Generating %d %s video(s) from backlog", count, fmt)
    else:
        logger.info("Generating %d %s video(s) (scrape mode)", count, fmt)

    if fmt == "storytelling":
        if multi_bg:
            backgrounds = _pick_backgrounds_interactive()
            produced = _generate_storytelling_from_backlog(
                count, channel_cfg, pick=pick,
                no_audio=no_audio, keep_backlog=keep_backlog,
                backgrounds=backgrounds,
            )
        else:
            background = _pick_background_interactive() if pick_background else None
            produced = _generate_storytelling_from_backlog(
                count, channel_cfg, pick=pick,
                no_audio=no_audio, keep_backlog=keep_backlog,
                background=background,
            )
    else:  # tweets
        if multi_bg:
            logger.warning("--multi-bg is only supported for storytelling format; ignoring for tweets")
        if scrape:
            produced = _scrape_tweets(count, min_likes)
        else:
            produced = _generate_tweets_from_backlog(
                count, channel_cfg, pick=pick,
                no_audio=no_audio, keep_backlog=keep_backlog,
            )

    print(f"\nGenerated {len(produced)}/{count} videos:")
    for p in produced:
        print(f"  {p}")


# ===========================================================================
# Storytelling pipeline
# ===========================================================================

def _generate_storytelling_from_backlog(
    count: int,
    channel_cfg,
    pick: bool = False,
    no_audio: bool = False,
    keep_backlog: bool = False,
    background: str | None = None,
    backgrounds: list[str] | None = None,
) -> list[str]:
    """Pull approved Reddit posts from the backlog and produce story videos.

    When `backgrounds` is provided (--multi-bg mode), TTS and subtitles are
    generated once per story, then one video is assembled per background. All
    variant paths are added to `produced`. Only one backlog item is consumed.
    """
    from pipeline.db import get_connection
    from pipeline.backlog import (
        get_approved_stories, mark_story_used,
        get_recent_backgrounds, log_background_use,
    )
    from formats.storytelling.generator import adapt_reddit_post

    slug = channel_cfg.slug if channel_cfg else ""

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
        # batch_used tracks backgrounds chosen during this run so each video gets a unique clip
        batch_used: list[str] = []
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
                generate_fn=lambda p=post, feedback="": adapt_reddit_post(p, slug, feedback=feedback),
                quality_fn=lambda s: {"passed": True, "overall": 10.0},
                label="story-from-backlog",
            )
            if story is None:
                logger.error("Backlog story %d rejected after all retries, skipping", i + 1)
                continue

            if backgrounds is not None:
                # Multi-bg mode: TTS once, assemble one video per background
                video_paths = _assemble_multi_bg(
                    story["story_text"], backgrounds, no_audio, channel_cfg
                )
                for video_path in video_paths:
                    _save_video_metadata(
                        video_path, story["story_text"], "storytelling",
                        channel_cfg.hashtags if channel_cfg else [],
                    )
                if not keep_backlog:
                    mark_story_used(conn, row["id"])
                    conn.commit()
                for bg in backgrounds:
                    log_background_use(conn, slug, Path(bg).name)
                conn.commit()
                produced.extend(video_paths)
                logger.info(
                    "Backlog story %d done → %d variant(s)", len(produced), len(video_paths)
                )
            else:
                # Single-bg mode: per-video background selection
                if background is not None:
                    video_bg = background
                else:
                    recent = get_recent_backgrounds(conn, slug, limit=5)
                    exclude = list(dict.fromkeys(recent + batch_used))  # dedup, preserve order
                    video_bg = _pick_background(exclude=exclude)

                video_path = _run_storytelling_pipeline(
                    story["story_text"], video_bg, no_audio=no_audio
                )
                if video_path:
                    _save_video_metadata(
                        video_path, story["story_text"], "storytelling",
                        channel_cfg.hashtags if channel_cfg else [],
                    )
                    if not keep_backlog:
                        mark_story_used(conn, row["id"])
                        conn.commit()
                    log_background_use(conn, slug, Path(video_bg).name)
                    conn.commit()
                    batch_used.append(Path(video_bg).name)
                    produced.append(video_path)
                    logger.info("Backlog story %d done → %s", len(produced), video_path)

        return produced
    finally:
        conn.close()


# ===========================================================================
# Tweet pipeline
# ===========================================================================

def _generate_tweets_from_backlog(
    count: int,
    channel_cfg,
    pick: bool = False,
    no_audio: bool = False,
    keep_backlog: bool = False,
) -> list[str]:
    """Pull approved tweets from the backlog and produce tweet videos."""
    from pipeline.db import get_connection
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


def _pick_background(exclude: list[str] | None = None) -> str:
    """Return a random background clip from assets/backgrounds/.

    Args:
        exclude: Optional list of clip basenames (e.g. ["subwaysurfers.mp4"]) to skip.
                 If all clips are excluded, falls back to the full list to avoid a crash.
    """
    bg_dir = config.ASSETS_DIR / "backgrounds"
    exts   = ("**/*.mp4", "**/*.webm", "**/*.mov", "**/*.mkv")
    clips  = [p for ext in exts for p in bg_dir.glob(ext)
              if "test" not in p.name and not p.name.endswith(".part")]
    if not clips:
        clips = [p for ext in exts for p in bg_dir.glob(ext) if not p.name.endswith(".part")]
    if not clips:
        logger.error("No background clips found in %s", bg_dir)
        sys.exit(1)

    if exclude:
        filtered = [p for p in clips if p.name not in exclude]
        if filtered:
            clips = filtered
        else:
            logger.warning(
                "_pick_background: all %d clips are excluded — allowing reuse", len(clips)
            )

    chosen = random.choice(clips)
    logger.info("Selected background clip: %s", chosen.name)
    return str(chosen)


def _pick_background_interactive() -> str:
    """Show a numbered list of background clips and let the user choose one."""
    bg_dir = config.ASSETS_DIR / "backgrounds"
    exts   = ("**/*.mp4", "**/*.webm", "**/*.mov", "**/*.mkv")
    clips  = sorted(
        [p for ext in exts for p in bg_dir.glob(ext) if not p.name.endswith(".part")],
        key=lambda p: p.name.lower(),
    )
    if not clips:
        logger.error("No background clips found in %s", bg_dir)
        sys.exit(1)

    print("\nAvailable background clips:")
    print("-" * 60)
    for i, clip in enumerate(clips, 1):
        # Show the parent folder name if the clip is in a subfolder
        rel = clip.relative_to(bg_dir)
        label = str(rel) if len(rel.parts) > 1 else clip.name
        print(f"  {i}. {label}")
    print()

    while True:
        try:
            choice = input("Select background (enter number): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNo selection made — choosing randomly.")
            return _pick_background()

        if choice.isdigit() and 1 <= int(choice) <= len(clips):
            chosen = clips[int(choice) - 1]
            logger.info("Selected background clip: %s", chosen.name)
            return str(chosen)

        print(f"Please enter a number between 1 and {len(clips)}.")


def _pick_backgrounds_interactive() -> list[str]:
    """Show a numbered list of background clips and let the user choose multiple.

    Returns a list of selected background paths (>= 2). Exits with an error
    message if the user selects fewer than 2 backgrounds.
    """
    bg_dir = config.ASSETS_DIR / "backgrounds"
    exts   = ("**/*.mp4", "**/*.webm", "**/*.mov", "**/*.mkv")
    clips  = sorted(
        [p for ext in exts for p in bg_dir.glob(ext) if not p.name.endswith(".part")],
        key=lambda p: p.name.lower(),
    )
    if not clips:
        logger.error("No background clips found in %s", bg_dir)
        sys.exit(1)

    print("\nAvailable background clips:")
    print("-" * 60)
    for i, clip in enumerate(clips, 1):
        rel = clip.relative_to(bg_dir)
        label = str(rel) if len(rel.parts) > 1 else clip.name
        print(f"  {i}. {label}")
    print()

    try:
        raw = input("Select backgrounds (comma-separated, e.g. 1,3,5): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nNo selection made.")
        sys.exit(1)

    selected: list[str] = []
    seen: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(clips) and idx not in seen:
                seen.add(idx)
                selected.append(str(clips[idx]))

    if len(selected) < 2:
        print("Use --background for single selection. --multi-bg requires >= 2 backgrounds.")
        sys.exit(1)

    logger.info("Multi-bg: selected %d background(s)", len(selected))
    return selected


def _assemble_multi_bg(
    story_text: str,
    backgrounds: list[str],
    no_audio: bool,
    channel_cfg,
) -> list[str]:
    """Generate TTS + subtitles once, then assemble one video per background.

    Args:
        story_text:  Narration text for TTS.
        backgrounds: List of background clip paths (one output per entry).
        no_audio:    When True, generate silent audio instead of calling ElevenLabs.
        channel_cfg: Channel configuration (unused here but available for future use).

    Returns:
        List of successfully assembled output paths (may be shorter than `backgrounds`
        if some assemblies fail — errors are logged and skipped).
    """
    from pipeline.tts import generate_tts
    from pipeline.overlay import generate_ass
    from formats.storytelling.assembler import assemble_video, AUDIO_SPEED

    run_id  = int(time.time())
    workdir = config.OUTPUT_DIR / str(run_id)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        if no_audio:
            logger.info("[multi-bg 1/3] Generating silent audio (--no-audio)…")
            tts = _generate_silent_audio(str(workdir))
        else:
            logger.info("[multi-bg 1/3] TTS (once for all backgrounds)…")
            tts = generate_tts(story_text, str(workdir))

        logger.info("[multi-bg 2/3] Subtitles…")
        subs = generate_ass(
            tts["timestamps_path"],
            str(workdir / "subtitles.ass"),
            speed_factor=AUDIO_SPEED,
        )
    except Exception as e:
        logger.error("Multi-bg: TTS/subtitle step failed: %s", e)
        return []

    logger.info("[multi-bg 3/3] Assembling %d video variant(s)…", len(backgrounds))
    outputs: list[str] = []
    for i, bg in enumerate(backgrounds, 1):
        output_path = str(workdir / f"final_bg{i}.mp4")
        try:
            out = assemble_video(
                background_path=bg,
                audio_path=tts["audio_path"],
                subtitles_path=subs,
                output_path=output_path,
                duration_seconds=tts["duration_seconds"],
            )
            outputs.append(out)
            logger.info("  bg%d assembled → %s", i, out)
        except Exception as e:
            logger.error("  bg%d assembly failed (%s): %s", i, Path(bg).name, e)

    return outputs


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
