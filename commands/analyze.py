"""
commands/analyze.py — YouTube channel analysis command.
"""

import logging
import time

logger = logging.getLogger(__name__)


def cmd_analyze(channel_urls: list[str], visual: bool, max_videos: int = 50,
                channel_cfg=None) -> None:
    from analysis.fetcher import fetch_channel
    from analysis.transcripts import fetch_transcripts
    from analysis.ranker import rank_channel
    from analysis.profiler import build_profile

    for url in channel_urls:
        logger.info("=" * 60)
        logger.info("ANALYZING CHANNEL: %s", url)
        logger.info("=" * 60)

        t0 = time.monotonic()

        logger.info("[1/4] Fetching channel videos…")
        channel_id = fetch_channel(url, max_videos=max_videos)

        logger.info("[2/4] Fetching transcripts…")
        fetched = fetch_transcripts(channel_id)
        logger.info("Transcripts: %d fetched", fetched)

        logger.info("[3/4] Ranking performance…")
        aggregates = rank_channel(channel_id)

        if visual:
            from analysis.visual import analyse_visuals
            logger.info("[4/4] Running visual analysis (this may take a while)…")
            n_visual = analyse_visuals(channel_id)
            logger.info("Visual analysis done: %d videos", n_visual)
        else:
            logger.info("[4/4] Skipping visual analysis (use --visual to enable)")

        logger.info("[5/5] Building style profile…")
        profile_path = build_profile(channel_id, aggregates, include_visual=visual)

        elapsed = time.monotonic() - t0
        logger.info("=" * 60)
        logger.info("ANALYSIS COMPLETE in %.1fs", elapsed)
        logger.info("Profile saved → %s", profile_path)
        logger.info("=" * 60)
        print(f"\nProfile saved: {profile_path}")
