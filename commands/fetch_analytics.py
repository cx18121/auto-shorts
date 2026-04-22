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
    """Fetch latest YouTube and Instagram stats for all channel videos and store in video_insights.

    YouTube: fetches ALL channel videos (including manually uploaded ones not in our uploads table)
    via the Analytics API, then upserts each into video_insights. Videos found on YouTube but
    missing from our uploads table are added to uploads so they are tracked going forward.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from pipeline.db import get_connection, init_db
    from pipeline.analytics import (
        fetch_all_youtube_channel_videos,
        fetch_instagram_insights,
        save_insights,
        get_recent_uploads_without_insights,
    )
    from pipeline.upload import refresh_instagram_token_if_needed

    slug = channel_cfg.slug
    yt_token_path = CHANNELS_DIR / slug / "youtube_token.json"
    init_db()
    conn = get_connection()

    try:
        # ---- YouTube: fetch ALL channel videos (including manual uploads) ----
        if yt_token_path.exists():
            creds = Credentials.from_authorized_user_file(str(yt_token_path))
            if creds.expired and creds.refresh_token:
                logger.info("fetch-analytics: refreshing expired YouTube OAuth token")
                creds.refresh(Request())
                with open(yt_token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())

            logger.info("fetch-analytics: fetching all YouTube channel videos")
            all_yt_videos = fetch_all_youtube_channel_videos(creds, days=365)
            logger.info("fetch-analytics: fetched %d YouTube videos from Analytics API", len(all_yt_videos))

            if not all_yt_videos:
                logger.warning("fetch-analytics: no YouTube videos returned from Analytics API")
            else:
                # Build set of video_ids we already track in uploads
                existing_uploads = {
                    row["video_id"]
                    for row in conn.execute(
                        "SELECT video_id FROM uploads WHERE channel=? AND platform='youtube'",
                        (slug,),
                    ).fetchall()
                }

                # Fetch titles from Data API for videos not in uploads
                new_video_ids = [v["video_id"] for v in all_yt_videos if v["video_id"] not in existing_uploads]
                title_map: dict[str, str] = {}
                if new_video_ids:
                    logger.info("fetch-analytics: fetching titles for %d videos not in uploads", len(new_video_ids))
                    for i in range(0, len(new_video_ids), 50):
                        batch = new_video_ids[i:i + 50]
                        try:
                            youtube = build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY)
                            resp = youtube.videos().list(
                                part="snippet",
                                id=",".join(batch),
                            ).execute()
                            for item in resp.get("items", []):
                                title_map[item["id"]] = item["snippet"]["title"]
                        except Exception as e:
                            logger.warning("fetch-analytics: failed to fetch titles for batch: %s", e)

                # Preserve existing transcript_path and bg_filename for videos already in video_insights,
                # and pull from uploads table for videos tracked by the pipeline.
                existing_insights: dict[str, dict] = {}
                prior_rows = conn.execute("""
                    SELECT video_id, transcript_path, bg_filename
                    FROM video_insights
                    WHERE channel=? AND platform='youtube'
                """, (slug,)).fetchall()
                for row in prior_rows:
                    existing_insights[row["video_id"]] = {
                        "transcript_path": row["transcript_path"],
                        "bg_filename": row["bg_filename"],
                    }

                # Also grab transcript_path and bg_filename from uploads table for tracked videos
                upload_meta: dict[str, dict] = {}
                upload_rows = conn.execute("""
                    SELECT video_id, transcript_path, bg_filename
                    FROM uploads
                    WHERE channel=? AND platform='youtube'
                      AND (transcript_path IS NOT NULL OR bg_filename IS NOT NULL)
                """, (slug,)).fetchall()
                for row in upload_rows:
                    upload_meta[row["video_id"]] = {
                        "transcript_path": row["transcript_path"],
                        "bg_filename": row["bg_filename"],
                    }

                # Backfill bg_filename from background_usage table for videos missing it.
                # Match each video to the background_usage entry closest to (and before) its uploaded_at.
                # Use a windowed approach: for each video, find the background_usage entry with
                # minimum absolute time diff, constrained to entries at or before the video's upload time.
                bg_backfill: dict[str, str] = {}
                if not upload_meta:
                    bg_rows = conn.execute("""
                        WITH closest_bg AS (
                            SELECT
                                u.video_id,
                                bu.bg_filename,
                                ROW_NUMBER() OVER (
                                    PARTITION BY u.video_id
                                    ORDER BY ABS(
                                        (julianday(u.uploaded_at) - julianday(bu.used_at)) * 86400
                                    ) ASC
                                ) AS rn
                            FROM uploads u
                            JOIN background_usage bu ON bu.channel = u.channel AND bu.used_at <= u.uploaded_at
                            WHERE u.channel = ? AND u.platform = 'youtube'
                        )
                        SELECT video_id, bg_filename FROM closest_bg WHERE rn = 1
                    """, (slug,)).fetchall()
                    for row in bg_rows:
                        bg_backfill[row["video_id"]] = row["bg_filename"]

                # Upsert each video into video_insights
                saved_count = 0
                for v in all_yt_videos:
                    vid = v["video_id"]
                    prior = existing_insights.get(vid, {})
                    meta = upload_meta.get(vid, {})  # pipeline-uploaded metadata takes priority
                    title = title_map.get(vid) or v.get("title")
                    save_insights(
                        conn, slug, "youtube", vid,
                        metrics={
                            "view_count": v.get("views", 0),
                            "like_count": v.get("likes", 0),
                            "comment_count": v.get("comments", 0),
                            "watch_time_seconds": int(v.get("estimated_minutes_watched", 0) * 60),
                            "shares": v.get("shares", 0),
                            "average_view_duration_seconds": v.get("average_view_duration_seconds"),
                            "average_view_percentage": v.get("average_view_percentage"),
                            "dislikes": v.get("dislikes", 0),
                        },
                        title=title,
                        transcript_path=prior.get("transcript_path") or meta.get("transcript_path"),
                        bg_filename=prior.get("bg_filename") or meta.get("bg_filename") or bg_backfill.get(vid),
                    )
                    saved_count += 1

                logger.info("fetch-analytics: saved YouTube analytics for %d videos", saved_count)

                # Add any new videos (not in uploads) to uploads table so they're tracked going forward
                for vid, title in title_map.items():
                    try:
                        conn.execute("""
                            INSERT OR IGNORE INTO uploads
                            (channel, platform, video_id, title, status, uploaded_at)
                            VALUES (?, 'youtube', ?, ?, 'success', datetime('now'))
                        """, (slug, vid, title))
                        conn.commit()
                    except Exception as e:
                        logger.warning("fetch-analytics: failed to insert new upload: %s", e)
                if title_map:
                    logger.info("fetch-analytics: added %d new videos to uploads table", len(title_map))

        else:
            logger.warning("fetch-analytics: no YouTube OAuth token for %s, skipping", slug)

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