"""
commands/status.py — Channel health status command.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def cmd_status(channel_cfg) -> None:
    """Print a formatted health summary for the channel.

    Shows backlog counts, last upload, token status, and output file count.
    """
    from pipeline.db import get_connection
    from pipeline.backlog import get_status_counts, init_backlog_tables
    from pipeline.upload import init_upload_table

    slug = channel_cfg.slug

    conn = get_connection()
    try:
        # Ensure tables exist before querying
        init_backlog_tables(conn)
        init_upload_table(conn)

        # ---------------------------------------------------------------
        # Channel info
        # ---------------------------------------------------------------
        enabled_label = "ENABLED" if channel_cfg.enabled else "DISABLED"
        print(f"\n=== Channel: {slug} ===")
        print(f"Name:    {channel_cfg.name}")
        print(f"Format:  {channel_cfg.format}")
        print(f"Status:  {enabled_label}")

        # ---------------------------------------------------------------
        # Backlog counts
        # ---------------------------------------------------------------
        counts_by_channel = get_status_counts(conn, slug)
        counts = counts_by_channel.get(slug, {"pending": 0, "approved": 0, "used": 0, "rejected": 0})

        print("\nBacklog:")
        print(f"  Pending:  {counts.get('pending', 0)}")
        print(f"  Approved:  {counts.get('approved', 0)}")
        print(f"  Used:     {counts.get('used', 0)}")
        print(f"  Rejected: {counts.get('rejected', 0)}")

        # ---------------------------------------------------------------
        # Last upload
        # ---------------------------------------------------------------
        print("\nLast Upload:")
        try:
            row = conn.execute(
                "SELECT * FROM uploads WHERE channel=? ORDER BY uploaded_at DESC LIMIT 1",
                (slug,),
            ).fetchone()
            if row:
                print(f"  Date:     {row['uploaded_at']}")
                print(f"  Platform: {row['platform']}")
                print(f"  Status:   {row['status']}")
            else:
                print("  No uploads yet")
        except Exception as e:
            logger.debug("Could not query uploads table: %s", e)
            print("  No uploads yet")

        # ---------------------------------------------------------------
        # Token status
        # ---------------------------------------------------------------
        channels_dir = Path(config.CHANNELS_DIR) / slug
        yt_token_path = channels_dir / "youtube_token.json"
        ig_token_path = channels_dir / "instagram_token.json"

        print("\nTokens:")

        # YouTube
        yt_status = "Found" if yt_token_path.exists() else "Missing"
        print(f"  YouTube:   {yt_status}")

        # Instagram
        if ig_token_path.exists():
            ig_status = "Found"
            try:
                ig_data = json.loads(ig_token_path.read_text())
                expires_at = ig_data.get("expires_at")
                if expires_at:
                    # expires_at may be a Unix timestamp (int) or ISO string
                    if isinstance(expires_at, (int, float)):
                        expiry_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                    else:
                        expiry_dt = datetime.fromisoformat(str(expires_at))
                        if expiry_dt.tzinfo is None:
                            expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                    now = datetime.now(tz=timezone.utc)
                    days_left = (expiry_dt - now).days
                    ig_status = f"Found (expires in {days_left} days)"
            except Exception as e:
                logger.debug("Could not parse Instagram token expiry: %s", e)
            print(f"  Instagram: {ig_status}")
        else:
            print("  Instagram: Missing")

        # ---------------------------------------------------------------
        # Output directory
        # ---------------------------------------------------------------
        output_dir = config.OUTPUT_DIR
        mp4_count = len(list(output_dir.rglob("*.mp4"))) if output_dir.exists() else 0
        print(f"\nOutput: {mp4_count} videos in output/")
        print()

    finally:
        conn.close()
