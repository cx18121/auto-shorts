"""
commands/fetch_analytics.py — Fetch performance metrics from YouTube and Instagram.

Usage:
    python main.py --channel hypothetical-scenarios fetch-analytics
"""

import logging
import os
from pathlib import Path

import config
from config import CHANNELS_DIR

logger = logging.getLogger(__name__)


def cmd_fetch_analytics(channel_cfg) -> None:
    """Fetch latest YouTube and Instagram stats for recent uploads and store in video_insights."""
    from pipeline.db import get_connection, init_db
    from pipeline.analytics import (
        fetch_youtube_stats,
        fetch_instagram_insights,
        save_insights,
        get_recent_uploads_without_insights,
    )
    from pipeline.upload import refresh_instagram_token_if_needed

    slug = channel_cfg.slug
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    init_db()  # Ensure video_insights table exists
    conn = get_connection()

    try:
        # ---- YouTube ----
        if api_key:
            yt_uploads = get_recent_uploads_without_insights(conn, slug, "youtube", limit=50, days=30)
            if yt_uploads:
                video_ids = [u["video_id"] for u in yt_uploads]
                logger.info("fetch-analytics: fetching YouTube stats for %d videos", len(video_ids))
                stats = fetch_youtube_stats(video_ids, api_key)
                stats_map = {s["video_id"]: s for s in stats}
                for upload in yt_uploads:
                    vid = upload["video_id"]
                    if vid in stats_map:
                        s = stats_map[vid]
                        save_insights(
                            conn, slug, "youtube", vid,
                            metrics={
                                "view_count": s["view_count"],
                                "like_count": s["like_count"],
                                "comment_count": s["comment_count"],
                            },
                            title=upload.get("title"),
                            transcript_path=upload.get("transcript_path"),
                            bg_filename=upload.get("bg_filename"),
                        )
                        logger.info("fetch-analytics: saved YouTube insights for %s (views=%d)",
                                    vid, s["view_count"])
                    else:
                        logger.warning("fetch-analytics: no stats returned for YouTube video %s", vid)
            else:
                logger.info("fetch-analytics: no pending YouTube uploads to fetch")
        else:
            logger.warning("fetch-analytics: YOUTUBE_API_KEY not set, skipping YouTube")

        # ---- Instagram ----
        ig_token_path = CHANNELS_DIR / slug / "instagram_token.json"
        if not ig_token_path.exists():
            logger.warning("fetch-analytics: no Instagram token for %s, skipping", slug)
        else:
            access_token = refresh_instagram_token_if_needed(ig_token_path)
            ig_uploads = get_recent_uploads_without_insights(conn, slug, "instagram", limit=30, days=30)
            if ig_uploads:
                media_ids = [u["video_id"] for u in ig_uploads]
                logger.info("fetch-analytics: fetching Instagram insights for %d media IDs", len(media_ids))
                insights = fetch_instagram_insights(media_ids, access_token)
                insights_map = {i["media_id"]: i for i in insights}
                for upload in ig_uploads:
                    mid = upload["video_id"]
                    if mid in insights_map:
                        ins = insights_map[mid]
                        save_insights(
                            conn, slug, "instagram", mid,
                            metrics={
                                "reach": ins.get("reach"),
                                "likes": ins.get("likes"),
                                "comments": ins.get("comments"),
                                "shares": ins.get("shares"),
                                "saves": ins.get("saves"),
                                "watch_time_seconds": ins.get("watch_time_seconds"),
                            },
                            title=upload.get("title"),
                            transcript_path=upload.get("transcript_path"),
                            bg_filename=upload.get("bg_filename"),
                        )
                        logger.info("fetch-analytics: saved Instagram insights for %s (reach=%s)",
                                    mid, ins.get("reach"))
                    else:
                        logger.warning("fetch-analytics: no insights returned for Instagram media %s", mid)
            else:
                logger.info("fetch-analytics: no pending Instagram uploads to fetch")

        logger.info("fetch-analytics: complete for %s", slug)
        print(f"\n[{slug}] Analytics fetch complete. Run 'analytics-report --days 30' to see insights.")

    finally:
        conn.close()