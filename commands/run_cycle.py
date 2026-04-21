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

import logging
import os
from pathlib import Path

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

        # ---------------------------------------------------------------
        # Step 3: Generate upload metadata
        # ---------------------------------------------------------------
        metadata    = generate_upload_metadata(content_text, channel_cfg.hashtags, fmt)
        title       = metadata["title"]
        hashtags    = metadata["hashtags"]
        desc_body   = metadata.get("description", "")
        hashtag_str = " ".join(f"#{t}" for t in hashtags) if hashtags else ""
        description = "\n\n".join(filter(None, [desc_body, hashtag_str]))

        save_metadata_file(video_path, metadata)

        # ---------------------------------------------------------------
        # Step 4: Upload to YouTube
        # ---------------------------------------------------------------
        yt_token_path = Path(config.CHANNELS_DIR) / slug / "youtube_token.json"
        yt_status     = "skipped"

        if not yt_token_path.exists():
            logger.warning("No YouTube token for %s — skipping YouTube upload", slug)
        else:
            try:
                video_id = upload_to_youtube(
                    video_path, title, description, hashtags,
                    yt_token_path,
                    channel_cfg.youtube_client_id,
                    channel_cfg.youtube_client_secret,
                    publish_at=publish_at,
                    made_for_kids=channel_cfg.youtube_made_for_kids,
                )
                logger.info("run-cycle: YouTube upload success video_id=%s", video_id)
                log_upload(conn, slug, "youtube", video_id, title, "success")
                yt_status = "success"
            except Exception as exc:
                logger.error("run-cycle: YouTube upload failed for %s: %s", slug, exc)
                log_upload(conn, slug, "youtube", "", title, "failed", error_msg=str(exc))
                yt_status = "failed"

        # ---------------------------------------------------------------
        # Step 5: Upload to Instagram
        # ---------------------------------------------------------------
        ig_token_path = Path(config.CHANNELS_DIR) / slug / "instagram_token.json"
        ig_status     = "skipped"

        if publish_at:
            logger.info("run-cycle: --publish-at set — skipping Instagram (not supported)")
        elif not channel_cfg.instagram_user_id or not ig_token_path.exists():
            logger.info("Instagram not configured for %s — skipping", slug)
        else:
            caption = "\n\n".join(filter(None, [title, desc_body, hashtag_str]))
            try:
                access_token = refresh_instagram_token_if_needed(ig_token_path)
                media_id = upload_to_instagram(
                    Path(video_path), caption,
                    channel_cfg.instagram_user_id,
                    access_token,
                )
                logger.info("run-cycle: Instagram upload success media_id=%s", media_id)
                log_upload(conn, slug, "instagram", media_id, title, "success")
                ig_status = "success"
            except Exception as exc:
                logger.error("run-cycle: Instagram upload failed for %s: %s", slug, exc)
                log_upload(conn, slug, "instagram", "", title, "failed", error_msg=str(exc))
                ig_status = "failed"

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

    finally:
        conn.close()
