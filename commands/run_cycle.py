"""
commands/run_cycle.py — Full automated posting cycle for one channel.

Flow:
  1. Check enabled flag — skip if False.
  2. Pull highest-scored approved item from backlog.
  3. If backlog is empty, run scrape fallback once then re-query.
  4. Generate a video from the item.
  5. Generate upload metadata (title + hashtags) via Claude Haiku.
  6. Upload to YouTube (skip if token missing).
  7. Upload to Instagram (skip if user_id empty or token missing, or if publish_at is set).
  8. Mark item as used in the DB.
  9. Log summary.
"""

import concurrent.futures
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable

import config
from commands.generate import (
    _generate_with_quality,
    _pick_background,
    _run_storytelling_pipeline,
    _run_tweet_pipeline,
    _save_video_metadata,
)
from commands.scrape import cmd_scrape

logger = logging.getLogger(__name__)

_OUTPUT_CLEANUP_DAYS = 7  # delete completed run dirs older than this


def _cleanup_old_output(keep_dir: str | None = None, max_age_days: int = _OUTPUT_CLEANUP_DAYS) -> None:
    """Delete completed output run directories older than max_age_days.

    A run directory is eligible if:
      - Its name is a numeric Unix timestamp.
      - It contains at least one *.mp4 file (i.e. generation completed).
      - Its timestamp is older than max_age_days ago.

    keep_dir is the path of the just-created run dir, which is never deleted.
    """
    cutoff = time.time() - max_age_days * 86400
    deleted = 0
    freed_bytes = 0

    for entry in config.OUTPUT_DIR.iterdir():
        if not entry.is_dir():
            continue
        if not entry.name.isdigit():
            continue
        if keep_dir and str(entry) == str(keep_dir):
            continue
        run_ts = int(entry.name)
        if run_ts >= cutoff:
            continue
        mp4s = list(entry.glob("*.mp4"))
        if not mp4s:
            continue
        try:
            size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            shutil.rmtree(entry)
            deleted += 1
            freed_bytes += size
        except Exception as exc:
            logger.warning("_cleanup_old_output: could not delete %s — %s", entry, exc)

    if deleted:
        freed_mb = freed_bytes / (1024 * 1024)
        logger.info("_cleanup_old_output: removed %d run dir(s), freed %.1f MB", deleted, freed_mb)


def cmd_run_cycle(channel_cfg, publish_at: str | None = None) -> None:
    """Orchestrate one posting cycle for a channel."""
    slug = channel_cfg.slug

    if not channel_cfg.enabled:
        logger.info("Channel %s is disabled, skipping", slug)
        return

    from pipeline.db import get_connection
    from pipeline.backlog import (
        get_approved_stories, get_approved_tweets,
        mark_story_used, mark_used,
        get_recent_backgrounds, log_background_use,
    )
    from pipeline.upload import (
        upload_to_youtube, upload_to_instagram,
        generate_upload_metadata, save_metadata_file,
        init_upload_table, log_upload,
        refresh_instagram_token_if_needed,
    )

    conn = get_connection()
    try:
        init_upload_table(conn)
        fmt = channel_cfg.format

        # ---------------------------------------------------------------
        # Step 1: Pick best item from backlog (with scrape fallback)
        # ---------------------------------------------------------------
        if fmt == "storytelling":
            rows = get_approved_stories(conn, slug)
            if not rows:
                logger.info("Backlog empty for [%s] — running scrape fallback", slug)
                cmd_scrape("reddit", "week", channel_cfg)
                rows = get_approved_stories(conn, slug)
        else:
            rows = get_approved_tweets(conn, slug)
            if not rows:
                logger.info("Backlog empty for [%s] — running scrape fallback", slug)
                cmd_scrape("tweets", "week", channel_cfg)
                rows = get_approved_tweets(conn, slug)

        if not rows:
            logger.warning("No approved items for %s after scrape fallback — aborting", slug)
            return

        row = rows[0]

        # ---------------------------------------------------------------
        # Step 2: Generate video
        # ---------------------------------------------------------------
        video_path: str | None = None

        if fmt == "storytelling":
            from formats.storytelling.generator import adapt_reddit_post

            post = {
                "title":     row["title"],
                "body":      row["body"],
                "subreddit": row["subreddit"],
                "score":     row["score"],
            }

            story = _generate_with_quality(
                generate_fn=lambda p=post, feedback="": adapt_reddit_post(p, slug, feedback=feedback),
                quality_fn=lambda s: {"passed": True, "overall": 10.0},
                label="run-cycle-story",
            )
            if story is None:
                logger.error("run-cycle: story generation failed for %s — aborting", slug)
                return

            recent_bgs   = get_recent_backgrounds(conn, slug, limit=5)
            background   = _pick_background(exclude=recent_bgs)
            video_path   = _run_storytelling_pipeline(story["story_text"], background)
            content_text = story["story_text"]

        else:  # tweets
            from formats.tweets.renderer import render_tweet
            from formats.tweets.assembler import assemble_tweet_video

            tweet = {
                "tweet_id":   row["tweet_id"],
                "tweet_text": row["tweet_text"],
                "username":   row["username"],
                "likes":      row["likes"],
                "retweets":   row["retweets"],
            }
            video_path   = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            content_text = row["tweet_text"]

        if not video_path:
            logger.error("run-cycle: video generation failed for %s — aborting", slug)
            return

        # Build content references for analytics tracking
        output_dir = str(Path(video_path).parent)
        if fmt == "storytelling":
            transcript_path = str(Path(output_dir) / "timestamps.json")
            bg_name = Path(background).name
        else:
            transcript_path = None
            bg_name = None

        # ---------------------------------------------------------------
        # Step 3: Upload metadata — from story generation (storytelling) or Haiku call (tweets)
        # ---------------------------------------------------------------
        if fmt == "storytelling":
            title       = story["title"]
            desc_body   = story.get("description", "")
            # Merge and deduplicate hashtags: story tags + channel niche tags
            seen: set[str] = set()
            story_tags  = story.get("hashtags", [])
            merged: list[str] = []
            for tag in story_tags + channel_cfg.hashtags:
                normalized = tag.lstrip("#").lower()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    merged.append(normalized)
            hashtags    = merged
            metadata    = {"title": title, "description": desc_body, "hashtags": hashtags}
        else:
            metadata    = generate_upload_metadata(content_text, channel_cfg.hashtags, fmt)
            title       = metadata["title"]
            hashtags    = metadata["hashtags"]
            desc_body   = metadata.get("description", "")
        hashtag_str = " ".join(f"#{t}" for t in hashtags) if hashtags else ""
        description = "\n\n".join(filter(None, [desc_body, hashtag_str]))

        save_metadata_file(video_path, metadata)

        # ---------------------------------------------------------------
        # Steps 4 + 5: Upload to YouTube and Instagram in parallel
        # ---------------------------------------------------------------
        yt_token_path = Path(config.CHANNELS_DIR) / slug / "youtube_token.json"
        ig_token_path = Path(config.CHANNELS_DIR) / slug / "instagram_token.json"
        caption = "\n\n".join(filter(None, [title, desc_body, hashtag_str]))

        def _yt_upload() -> dict:
            video_id = upload_to_youtube(
                video_path, title, description, hashtags,
                yt_token_path,
                channel_cfg.youtube_client_id,
                channel_cfg.youtube_client_secret,
                publish_at=publish_at,
                made_for_kids=channel_cfg.youtube_made_for_kids,
            )
            logger.info("run-cycle: YouTube upload success video_id=%s", video_id)
            return {"id": video_id}

        def _ig_upload() -> dict:
            access_token = refresh_instagram_token_if_needed(ig_token_path)
            media_id = upload_to_instagram(
                Path(video_path), caption,
                channel_cfg.instagram_user_id,
                access_token,
            )
            logger.info("run-cycle: Instagram upload success media_id=%s", media_id)
            return {"id": media_id}

        upload_fns: dict[str, Any] = {}
        if yt_token_path.exists():
            upload_fns["youtube"] = _yt_upload
        else:
            logger.warning("No YouTube token for %s — skipping YouTube upload", slug)

        ig_skip_reason: str | None = None
        if publish_at:
            ig_skip_reason = "--publish-at set — skipping Instagram (not supported)"
        elif not channel_cfg.instagram_user_id or not ig_token_path.exists():
            ig_skip_reason = "Instagram not configured"
        if ig_skip_reason:
            logger.info("run-cycle: %s for %s", ig_skip_reason, slug)
        else:
            upload_fns["instagram"] = _ig_upload

        upload_results: dict[str, dict] = {}
        if upload_fns:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(upload_fns)) as pool:
                futures = {pool.submit(fn): platform for platform, fn in upload_fns.items()}
                for future, platform in futures.items():
                    try:
                        upload_results[platform] = {"status": "success", **future.result()}
                    except Exception as exc:
                        logger.error("run-cycle: %s upload failed for %s: %s", platform, slug, exc)
                        upload_results[platform] = {"status": "failed", "error": str(exc)}

        for platform in ("youtube", "instagram"):
            if platform not in upload_fns:
                continue
            result = upload_results.get(platform, {"status": "failed", "error": "no result"})
            if result["status"] == "success":
                log_upload(conn, slug, platform, result["id"], title, "success",
                           transcript_path=transcript_path, bg_filename=bg_name)
            else:
                log_upload(conn, slug, platform, "", title, "failed",
                           error_msg=result.get("error"), transcript_path=transcript_path, bg_filename=bg_name)

        yt_status = upload_results.get("youtube", {}).get("status", "skipped")
        ig_status = upload_results.get("instagram", {}).get("status", "skipped")

        # ---------------------------------------------------------------
        # Step 6: Mark item as used (and log background for storytelling)
        # ---------------------------------------------------------------
        if fmt == "storytelling":
            mark_story_used(conn, row["id"])
            log_background_use(conn, slug, Path(background).name)
        else:
            mark_used(conn, "backlog_tweets", row["tweet_id"])
        conn.commit()

        logger.info(
            "Run cycle complete for %s: YouTube=%s, Instagram=%s",
            slug, yt_status, ig_status,
        )

        # Clean up old completed output run directories to reclaim disk space
        keep = str(Path(video_path).parent) if video_path else None
        _cleanup_old_output(keep_dir=keep)

    finally:
        conn.close()
