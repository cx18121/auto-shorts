"""
main.py — Automated Shorts Pipeline CLI.

Commands:
    generate       Generate videos (from backlog or scrape)
    scrape         Scrape content into the backlog
    review         Review pending backlog items
    backlog-status Show backlog counts
    status         Show channel health summary (backlog, tokens, uploads)
    run-cycle      Full automated cycle (generate + upload + mark-used)
    upload-history Show recent upload history
    setup-youtube  Run YouTube OAuth flow
    setup-instagram Exchange Instagram short-lived token
    setup-twitter   (deprecated no-op — cookie-based auth is used instead)
"""

import argparse
import logging
import sys

import config  # loads .env, configures logging, creates output dirs

logger = logging.getLogger(__name__)


# ===========================================================================
# CLI definition
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated YouTube Shorts / Instagram Reels pipeline"
    )
    parser.add_argument(
        "--channel",
        required=True,
        metavar="SLUG",
        help=(
            "Channel to operate on (e.g. hypothetical-scenarios, finance-hustle) "
            "or 'all' to run all channels sequentially."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- generate ---
    p_gen = sub.add_parser("generate", help="Generate and produce videos")
    p_gen.add_argument("--format", choices=["storytelling", "tweets"], required=True)
    p_gen.add_argument("--count", type=int, default=1)
    p_gen.add_argument("--thread", action="store_true",
                       help="Generate thread-style tweet videos (tweets format only)")
    p_gen.add_argument("--scrape", action="store_true",
                       help="Scrape fresh tweets and immediately produce videos (tweets only)")
    p_gen.add_argument("--min-likes", type=int, default=500,
                       help="Minimum likes when scraping (default: 500)")
    p_gen.add_argument("--from-backlog", action="store_true",
                       help="Pull approved items from backlog instead of generating/scraping")
    p_gen.add_argument("--pick", action="store_true",
                       help="Interactively choose which backlog items to use (implies --from-backlog)")
    p_gen.add_argument("--no-audio", action="store_true",
                       help="Skip TTS — use silent audio for testing video layout")
    p_gen.add_argument("--keep-backlog", action="store_true",
                       help="Don't mark backlog items as used after production (for testing)")
    p_gen.add_argument("--background", action="store_true",
                       help="Interactively pick ONE background clip; all videos in the batch use it (storytelling only)")
    p_gen.add_argument("--multi-bg", action="store_true",
                       help="Interactively pick MULTIPLE backgrounds; TTS+captions generated once, one output video per clip — final_bg1.mp4, final_bg2.mp4, ... (storytelling only; overrides --background)")

    # --- scrape ---
    p_scrape = sub.add_parser("scrape", help="Scrape content into the backlog")
    p_scrape.add_argument("--format", choices=["reddit", "tweets"], required=True,
                          help="Content source to scrape")
    p_scrape.add_argument("--window", choices=["24h", "month", "year"], default="24h",
                          help="Time window for scraping (default: 24h)")
    p_scrape.add_argument("--review", action="store_true",
                          help="Run review immediately after scraping")
    p_scrape.add_argument("--ai", action="store_true",
                          help="Use Claude to auto-approve/reject instead of manual input")

    # --- review ---
    p_review = sub.add_parser("review", help="Review pending backlog items")
    p_review.add_argument("--ai", action="store_true",
                          help="Use Claude to auto-approve/reject")

    # --- backlog-status ---
    sub.add_parser("backlog-status", help="Show backlog counts per channel")

    # --- run-cycle ---
    p_run = sub.add_parser("run-cycle", help="Full automated cycle: generate + upload + mark-used")
    p_run.add_argument("--publish-at", metavar="ISO8601",
                       help="Schedule YouTube upload (private until this UTC time)")

    # --- upload-history ---
    p_hist = sub.add_parser("upload-history", help="Show recent upload records")
    p_hist.add_argument("--limit", type=int, default=20, metavar="N",
                        help="Maximum records to display (default: 20)")

    # --- setup-youtube ---
    sub.add_parser("setup-youtube", help="Run YouTube OAuth flow and save token")

    # --- setup-instagram ---
    p_ig = sub.add_parser("setup-instagram", help="Exchange Instagram token and save")
    p_ig.add_argument("--token", metavar="TOKEN",
                      help="Short-lived Instagram access token (prompted if omitted)")

    # --- status ---
    sub.add_parser("status", help="Show channel health summary (backlog, tokens, uploads)")

    # --- fetch-analytics ---
    p_fetch = sub.add_parser("fetch-analytics", help="Fetch latest YouTube/Instagram performance metrics")
    p_fetch.add_argument("--days", type=int, default=30, metavar="N",
                         help="Lookback window in days (default: 30)")

    # --- analytics-report ---
    p_report = sub.add_parser("analytics-report", help="Print human-readable insights and recommendations")
    p_report.add_argument("--days", type=int, default=30, metavar="N",
                         help="Lookback window in days (default: 30)")

    # --- setup-twitter (deprecated no-op) ---
    p_tw = sub.add_parser("setup-twitter", help="(Deprecated) Add a Twitter/X account")
    p_tw.add_argument("--username", required=True)
    p_tw.add_argument("--password", required=True)
    p_tw.add_argument("--email",    required=True)
    p_tw.add_argument("--email-password", default=None)
    p_tw.add_argument("--cookies",        default=None)

    args = parser.parse_args()

    if args.channel == "all":
        for slug, channel_cfg in config.CHANNELS.items():
            logger.info("=" * 60)
            logger.info("CHANNEL: %s", slug)
            logger.info("=" * 60)
            try:
                _dispatch_command(args, channel_cfg)
            except Exception as e:
                logger.error("Channel %s failed: %s", slug, e)
    else:
        channel_cfg = config.get_channel(args.channel)
        _dispatch_command(args, channel_cfg)


# ===========================================================================
# Command dispatcher
# ===========================================================================

def _dispatch_command(args: argparse.Namespace, channel_cfg) -> None:
    """Route the parsed command to the correct handler for a single channel."""
    from commands.generate  import cmd_generate
    from commands.review    import cmd_review
    from commands.run_cycle import cmd_run_cycle
    from commands.scrape    import cmd_scrape, cmd_backlog_status, cmd_upload_history
    from commands.setup     import cmd_setup_twitter, cmd_setup_youtube, cmd_setup_instagram
    from commands.status    import cmd_status

    if args.command == "generate":
        if args.pick:
            args.from_backlog = True
        if not args.scrape and not args.from_backlog:
            logger.error("--scrape or --from-backlog is required for generate command")
            sys.exit(1)
        # --multi-bg wins over --background when both are set
        pick_bg = args.background and not args.multi_bg
        cmd_generate(
            args.format, args.count,
            args.thread,
            scrape=args.scrape,
            min_likes=args.min_likes,
            channel_cfg=channel_cfg,
            from_backlog=args.from_backlog,
            pick=args.pick,
            no_audio=args.no_audio,
            keep_backlog=args.keep_backlog,
            pick_background=pick_bg,
            multi_bg=args.multi_bg,
        )

    elif args.command == "scrape":
        cmd_scrape(args.format, args.window, channel_cfg)
        if args.review:
            cmd_review(channel_cfg, ai=args.ai)

    elif args.command == "review":
        cmd_review(channel_cfg, ai=args.ai)

    elif args.command == "backlog-status":
        cmd_backlog_status(channel_cfg)

    elif args.command == "status":
        cmd_status(channel_cfg)

    elif args.command == "run-cycle":
        cmd_run_cycle(channel_cfg, publish_at=args.publish_at)

    elif args.command == "upload-history":
        cmd_upload_history(channel_cfg, args.limit)

    elif args.command == "setup-youtube":
        cmd_setup_youtube(channel_cfg)

    elif args.command == "setup-instagram":
        cmd_setup_instagram(channel_cfg, args.token)

    elif args.command == "setup-twitter":
        cmd_setup_twitter(
            args.username, args.password, args.email,
            args.email_password,
            args.cookies,
            channel_cfg=channel_cfg,
        )

    elif args.command == "fetch-analytics":
        from commands.fetch_analytics import cmd_fetch_analytics
        cmd_fetch_analytics(channel_cfg)

    elif args.command == "analytics-report":
        from commands.analytics_report import cmd_analytics_report
        cmd_analytics_report(channel_cfg, days=args.days)


if __name__ == "__main__":
    main()
