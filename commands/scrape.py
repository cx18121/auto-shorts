"""
commands/scrape.py — Scrape, backlog-status, and upload-history commands.
"""

import logging

import config

logger = logging.getLogger(__name__)


def cmd_scrape(fmt: str, window: str, channel_cfg) -> None:
    """Scrape content into the backlog for one channel."""
    if fmt == "reddit":
        from pipeline.reddit_scraper import scrape_and_store_reddit
        result = scrape_and_store_reddit(channel_cfg, window=window)
    elif fmt == "tweets":
        from formats.tweets.scraper import scrape_and_store_tweets
        result = scrape_and_store_tweets(channel_cfg, window=window)
    logger.info(
        "Scrape complete [%s/%s]: scraped=%d passed=%d inserted=%d duplicates=%d",
        channel_cfg.slug, fmt,
        result["scraped"], result["passed"], result["inserted"], result["duplicates"],
    )
    print(f"  {channel_cfg.slug}/{fmt}: +{result['inserted']} new "
          f"({result['passed']} passed, {result['scraped']} scraped)")


def cmd_backlog_status(channel_cfg=None) -> None:
    """Print backlog counts. channel_cfg=None means all channels."""
    from pipeline.db import get_connection
    from pipeline.backlog import get_status_counts

    conn = get_connection()
    try:
        channels_to_show = (
            [channel_cfg.slug] if channel_cfg is not None
            else list(config.CHANNELS.keys())
        )

        print(f"\n{'Channel':<30} {'Pending':>8} {'Approved':>9} {'Used':>6} {'Rejected':>9}")
        print("-" * 66)
        for slug in channels_to_show:
            counts = get_status_counts(conn, slug)
            ch = counts.get(slug, {"pending": 0, "approved": 0, "used": 0, "rejected": 0})
            print(f"{slug:<30} {ch['pending']:>8} {ch['approved']:>9} {ch['used']:>6} {ch['rejected']:>9}")
    finally:
        conn.close()


def cmd_upload_history(channel_cfg, limit: int = 20) -> None:
    """Print a formatted table of recent uploads for the given channel."""
    from pipeline.db import get_connection
    from pipeline.upload import get_upload_history

    conn = get_connection()
    try:
        records = get_upload_history(conn, channel_cfg.slug, limit)
    finally:
        conn.close()

    if not records:
        print(f"No upload records found for [{channel_cfg.slug}].")
        return

    print(f"\n{'Date':<28} {'Platform':<12} {'Video ID':<18} {'Status':<9} {'Title'}")
    print("-" * 100)
    for rec in records:
        date     = rec.get("uploaded_at", "")[:19].replace("T", " ")
        platform = rec.get("platform", "")
        video_id = rec.get("video_id", "")[:16]
        status   = rec.get("status", "")
        title    = rec.get("title", "")[:40]
        print(f"{date:<28} {platform:<12} {video_id:<18} {status:<9} {title}")
