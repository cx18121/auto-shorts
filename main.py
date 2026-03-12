"""
main.py — Automated Shorts Pipeline CLI.

Commands:
    analyze  --channels URL [URL ...]  [--visual]
    generate --format storytelling|tweets  --profile PATH  --count N  [--thread]
             --from-backlog  (storytelling only: pull approved Reddit posts from backlog)
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import config  # loads .env, sets up logging
from pipeline.tts import generate_tts
from pipeline.overlay import generate_ass
from formats.storytelling.assembler import assemble_video

logger = logging.getLogger(__name__)

_DEFAULT_BACKGROUND = "assets/backgrounds/subwaysurfers.mp4"
_MAX_QUALITY_RETRIES = 3


# ===========================================================================
# CLI
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
            "Channel to operate on (e.g. hypothetical-scenarios, relationships, finance-hustle) "
            "or 'all' to run all channels sequentially."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Fetch and analyse YouTube channel(s)")
    p_analyze.add_argument("--channels", nargs="+", required=True,
                            metavar="URL", help="Channel URLs or @handles")
    p_analyze.add_argument("--visual", action="store_true",
                            help="Include visual frame/thumbnail analysis (slower, uses Claude vision)")
    p_analyze.add_argument("--max-videos", type=int, default=50,
                            help="Max videos to fetch from channel (default: 50)")

    # --- generate ---
    p_gen = sub.add_parser("generate", help="Generate and produce videos")
    p_gen.add_argument("--format", choices=["storytelling", "tweets"], required=True)
    p_gen.add_argument("--profile", metavar="PATH",
                        help="Path to style profile JSON (not needed with --scrape)")
    p_gen.add_argument("--count", type=int, default=1)
    p_gen.add_argument("--thread", action="store_true",
                        help="Generate thread-style tweet videos (tweets format only)")
    p_gen.add_argument("--scrape", action="store_true",
                        help="Use real tweets scraped from X instead of AI-generated ones")
    p_gen.add_argument("--min-likes", type=int, default=500,
                        help="Minimum likes when scraping (default: 500)")
    p_gen.add_argument("--from-backlog", action="store_true",
                        help="Pull approved stories from backlog and adapt via Claude (storytelling only)")

    # --- setup-twitter ---
    p_tw = sub.add_parser("setup-twitter", help="Add a Twitter/X account for scraping")
    p_tw.add_argument("--username", required=True, help="Twitter @handle (no @)")
    p_tw.add_argument("--password", required=True)
    p_tw.add_argument("--email",    required=True)
    p_tw.add_argument("--email-password", default=None,
                       help="Email password if different from Twitter password")
    p_tw.add_argument("--cookies", default=None,
                       help="Browser cookie string (\"key=val; key=val\") or path to "
                            "a JSON cookies file. If ct0 is present, login is skipped.")

    # --- scrape ---
    p_scrape = sub.add_parser("scrape", help="Scrape content into the backlog")
    p_scrape.add_argument("--format", choices=["reddit", "tweets"], required=True,
                          help="Content source to scrape")
    p_scrape.add_argument("--window", choices=["24h", "month"], default="24h",
                          help="Time window: '24h' for daily (default), 'month' for bootstrap fill")

    # --- review ---
    sub.add_parser("review", help="Review pending backlog items interactively")

    # --- backlog-status ---
    sub.add_parser("backlog-status", help="Print backlog counts per channel")

    # --- setup-youtube ---
    sub.add_parser(
        "setup-youtube",
        help="Run YouTube OAuth flow and save token for the selected channel",
    )

    # --- setup-instagram ---
    p_ig = sub.add_parser(
        "setup-instagram",
        help="Exchange an Instagram short-lived token and save for the selected channel",
    )
    p_ig.add_argument(
        "--token",
        default=None,
        metavar="SHORT_LIVED_TOKEN",
        help=(
            "Short-lived Instagram access token to exchange for a long-lived token. "
            "If omitted, the CLI will print instructions and prompt for it."
        ),
    )

    # --- run-cycle ---
    sub.add_parser(
        "run-cycle",
        help=(
            "Pull the highest-scored approved item from the backlog, generate a video, "
            "upload to YouTube and Instagram, mark item used, and log upload records."
        ),
    )

    # --- upload-history ---
    p_hist = sub.add_parser(
        "upload-history",
        help="Print recent upload history for the selected channel",
    )
    p_hist.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="Maximum number of records to display (default: 20)",
    )

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
                continue
    else:
        channel_cfg = config.get_channel(args.channel)
        _dispatch_command(args, channel_cfg)


# ===========================================================================
# analyze command
# ===========================================================================

def cmd_analyze(channel_urls: list[str], visual: bool, max_videos: int = 50,
                channel_cfg: "config.ChannelConfig | None" = None) -> None:
    from analysis.fetcher import fetch_channel
    from analysis.transcripts import fetch_transcripts
    from analysis.ranker import rank_channel
    from analysis.profiler import build_profile

    for url in channel_urls:
        logger.info("=" * 60)
        logger.info("ANALYZING CHANNEL: %s", url)
        logger.info("=" * 60)

        t0 = time.monotonic()

        # Step 1: fetch metadata + Shorts
        logger.info("[1/4] Fetching channel videos…")
        channel_id = fetch_channel(url, max_videos=max_videos)

        # Step 2: fetch transcripts
        logger.info("[2/4] Fetching transcripts…")
        fetched = fetch_transcripts(channel_id)
        logger.info("Transcripts: %d fetched", fetched)

        # Step 3: rank
        logger.info("[3/4] Ranking performance…")
        aggregates = rank_channel(channel_id)

        # Step 4 (optional): visual analysis
        if visual:
            from analysis.visual import analyse_visuals
            logger.info("[4/4] Running visual analysis (this may take a while)…")
            n_visual = analyse_visuals(channel_id)
            logger.info("Visual analysis done: %d videos", n_visual)
        else:
            logger.info("[4/4] Skipping visual analysis (use --visual to enable)")

        # Step 5: build style profile
        logger.info("[5/5] Building style profile…")
        profile_path = build_profile(channel_id, aggregates, include_visual=visual)

        elapsed = time.monotonic() - t0
        logger.info("=" * 60)
        logger.info("ANALYSIS COMPLETE in %.1fs", elapsed)
        logger.info("Profile saved → %s", profile_path)
        logger.info("=" * 60)
        print(f"\nProfile saved: {profile_path}")


# ===========================================================================
# generate command
# ===========================================================================

def cmd_setup_twitter(username: str, password: str, email: str,
                       email_password: str | None,
                       cookies: str | None = None,
                       channel_cfg: "config.ChannelConfig | None" = None) -> None:
    from formats.tweets.scraper import setup_account
    setup_account(username, password, email, email_password, cookies)
    print(f"Twitter account @{username} added successfully.")


def cmd_generate(fmt: str, profile_path: str | None, count: int, thread: bool,
                 scrape: bool = False, min_likes: int = 500,
                 channel_cfg: "config.ChannelConfig | None" = None,
                 from_backlog: bool = False) -> None:
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

    produced: list[str] = []

    if fmt == "storytelling":
        if from_backlog:
            produced = _generate_storytelling_from_backlog(count, channel_cfg)
        else:
            produced = _generate_storytelling(count, profile, profile_path)
    elif fmt == "tweets":
        if scrape:
            produced = _scrape_tweets(count, min_likes)
        else:
            produced = _generate_tweets(count, profile, profile_path, thread)

    print(f"\nGenerated {len(produced)}/{count} videos:")
    for p in produced:
        print(f"  {p}")


# ---------------------------------------------------------------------------
# Storytelling pipeline
# ---------------------------------------------------------------------------

def _generate_storytelling(
    count: int, profile: dict, profile_path: str
) -> list[str]:
    from formats.storytelling.generator import generate_story
    from formats.storytelling.quality import check_quality

    background = _pick_background()
    produced: list[str] = []

    for i in range(count):
        logger.info("-" * 50)
        logger.info("STORY %d/%d", i + 1, count)

        story = _generate_with_quality(
            generate_fn=lambda: generate_story(profile),
            quality_fn=lambda s: check_quality(s, profile),
            label="story",
        )
        if story is None:
            logger.error("Story %d/%d rejected after all retries, skipping", i + 1, count)
            continue

        video_path = _run_storytelling_pipeline(story["story_text"], background)
        if video_path:
            produced.append(video_path)
            logger.info("Story %d/%d done → %s", i + 1, count, video_path)

    return produced


def _generate_storytelling_from_backlog(
    count: int,
    channel_cfg: "config.ChannelConfig | None",
) -> list[str]:
    """Pull approved Reddit posts from the backlog and produce story videos.

    Adapts each post via adapt_reddit_post(), runs TTS + overlay + assembler,
    and marks each used story with mark_story_used() after successful video production.

    Args:
        count:       Maximum number of videos to produce.
        channel_cfg: Channel configuration; slug and optional style_profile path used.

    Returns:
        List of video file paths produced.
    """
    from analysis.db import get_connection
    from pipeline.backlog import get_approved_stories, mark_story_used
    from formats.storytelling.generator import adapt_reddit_post
    from formats.storytelling.quality import check_quality

    slug = channel_cfg.slug if channel_cfg else ""

    # Load style profile if configured
    profile: dict | None = None
    if channel_cfg and channel_cfg.style_profile:
        profile_path = Path(channel_cfg.style_profile)
        if profile_path.exists():
            try:
                profile = json.loads(profile_path.read_text())
                logger.info("Loaded style profile: %s", profile_path)
            except Exception as e:
                logger.warning("Failed to load style profile %s: %s — continuing without profile", profile_path, e)
        else:
            logger.warning("style_profile path not found: %s — continuing without profile", profile_path)

    conn = get_connection()
    try:
        rows = get_approved_stories(conn, slug)
        if not rows:
            logger.warning("No approved stories in backlog for [%s]", slug)
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
                "title": row["title"],
                "body": row["body"],
                "subreddit": row["subreddit"],
                "score": row["score"],
            }

            story = _generate_with_quality(
                generate_fn=lambda p=post: adapt_reddit_post(p, slug, profile),
                quality_fn=lambda s: check_quality(s, profile) if profile else {"passed": True, "overall": 10.0},
                label="story-from-backlog",
            )
            if story is None:
                logger.error("Backlog story %d rejected after all retries, skipping", i + 1)
                continue

            video_path = _run_storytelling_pipeline(story["story_text"], background)
            if video_path:
                mark_story_used(conn, row["id"])
                conn.commit()
                produced.append(video_path)
                logger.info("Backlog story %d done → %s", len(produced), video_path)

        return produced
    finally:
        conn.close()


def _run_storytelling_pipeline(story_text: str, background: str) -> str | None:
    run_id  = int(time.time())
    workdir = config.OUTPUT_DIR / str(run_id)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("[1/3] TTS…")
        tts = generate_tts(story_text, str(workdir))

        logger.info("[2/3] Subtitles…")
        subs = generate_ass(tts["timestamps_path"], str(workdir / "subtitles.ass"))

        logger.info("[3/3] Assembling…")
        out = assemble_video(
            background_path=background,
            audio_path=tts["audio_path"],
            subtitles_path=subs,
            output_path=str(workdir / "final.mp4"),
            duration_seconds=tts["duration_seconds"],
        )
        return out
    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Tweet pipeline
# ---------------------------------------------------------------------------

def _generate_tweets(
    count: int, profile: dict, profile_path: str, thread: bool
) -> list[str]:
    from formats.tweets.generator import generate_tweet, generate_thread
    from formats.tweets.quality import check_quality
    from formats.tweets.renderer import render_tweet
    from formats.tweets.assembler import assemble_tweet_video

    produced: list[str] = []

    if thread:
        # generate_thread returns list-of-threads; each thread → one video
        from formats.tweets.generator import generate_thread as gen_thread
        threads = gen_thread(count, profile_path)
        for i, tweet_list in enumerate(threads, 1):
            logger.info("-" * 50)
            logger.info("THREAD %d/%d (%d tweets)", i, count, len(tweet_list))
            # Use the first tweet as the main one for rendering / TTS
            tweet = tweet_list[0]
            video = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            if video:
                produced.append(video)
    else:
        for i in range(count):
            logger.info("-" * 50)
            logger.info("TWEET %d/%d", i + 1, count)

            tweet = _generate_with_quality(
                generate_fn=lambda: generate_tweet(profile),
                quality_fn=lambda t: check_quality(t, profile),
                label="tweet",
            )
            if tweet is None:
                logger.error("Tweet %d/%d rejected, skipping", i + 1, count)
                continue

            video = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            if video:
                produced.append(video)
                logger.info("Tweet %d/%d done → %s", i + 1, count, video)

    return produced


def _run_tweet_pipeline(tweet: dict, render_fn, assemble_fn) -> str | None:
    run_id  = int(time.time())
    workdir = config.OUTPUT_DIR / str(run_id)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("[1/3] Rendering tweet image…")
        img_path = render_fn(tweet, str(workdir / "tweet.png"))

        logger.info("[2/3] TTS…")
        tts = generate_tts(tweet["tweet_text"], str(workdir))

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


# ---------------------------------------------------------------------------
# Scrape pipeline (real tweets)
# ---------------------------------------------------------------------------

def _scrape_tweets(count: int, min_likes: int) -> list[str]:
    from formats.tweets.scraper import scrape_top_tweets
    from formats.tweets.renderer import render_tweet
    from formats.tweets.assembler import assemble_tweet_video

    logger.info("Scraping top tweets (need %d, min_likes=%d)…", count, min_likes)
    tweets = scrape_top_tweets(n=count * 3, min_likes=min_likes)
    if not tweets:
        logger.error("No tweets scraped — have you run setup-twitter?")
        return []

    produced: list[str] = []
    for tweet in tweets:
        if len(produced) >= count:
            break

        logger.info("-" * 50)
        logger.info("TWEET %d/%d — @%s (%d likes)",
                    len(produced) + 1, count, tweet["username"], tweet["likes"])

        run_id  = int(time.time())
        workdir = config.OUTPUT_DIR / str(run_id)
        workdir.mkdir(parents=True, exist_ok=True)

        try:
            logger.info("[1/3] Rendering tweet…")
            img_path = render_tweet(tweet, str(workdir / "tweet.png"))

            logger.info("[2/3] TTS…")
            tts = generate_tts(tweet["text"], str(workdir))

            logger.info("[3/3] Assembling…")
            out = assemble_tweet_video(
                image_path=img_path,
                audio_path=tts["audio_path"],
                output_path=str(workdir / "final.mp4"),
                duration_seconds=tts["duration_seconds"],
            )
            produced.append(out)
            logger.info("Done → %s", out)
        except Exception as e:
            logger.error("Scrape pipeline failed for %s: %s", tweet["url"], e)

    return produced


# ---------------------------------------------------------------------------
# Quality retry wrapper
# ---------------------------------------------------------------------------

def _generate_with_quality(generate_fn, quality_fn, label: str):
    """Generate content, quality-check it, retry up to MAX_QUALITY_RETRIES times."""
    for attempt in range(1, _MAX_QUALITY_RETRIES + 1):
        try:
            content = generate_fn()
            quality = quality_fn(content)
            logger.info(
                "%s attempt %d/%d: overall=%.1f passed=%s",
                label, attempt, _MAX_QUALITY_RETRIES,
                quality.get("overall", 0), quality.get("passed"),
            )
            if quality.get("passed"):
                return content
            logger.info("Rejected (%s), retrying…", quality.get("reason", "")[:80])
        except Exception as e:
            logger.warning("%s generation attempt %d failed: %s", label, attempt, e)
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_background() -> str:
    bg_dir = config.ASSETS_DIR / "backgrounds"
    clips  = [p for p in bg_dir.glob("*.mp4") if "test" not in p.name]
    if not clips:
        clips = list(bg_dir.glob("*.mp4"))
    if not clips:
        logger.error("No background clips found in %s", bg_dir)
        sys.exit(1)
    return str(clips[0])


def cmd_setup_youtube(channel_cfg: "config.ChannelConfig") -> None:
    """Run YouTube OAuth 2.0 desktop flow and save token for the given channel.

    Requires youtube_client_id and youtube_client_secret to be set in channels.yaml.
    Token is saved to data/channels/{slug}/youtube_token.json.

    Args:
        channel_cfg: Channel configuration with OAuth client credentials.
    """
    from pipeline.upload import setup_youtube_oauth

    token_path = Path(config.CHANNELS_DIR) / channel_cfg.slug / "youtube_token.json"

    if token_path.exists():
        confirm = input(
            f"A YouTube token already exists at {token_path}.\n"
            "Overwrite? (y/N): "
        ).strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    if not channel_cfg.youtube_client_id or not channel_cfg.youtube_client_secret:
        print(
            "ERROR: youtube_client_id and youtube_client_secret must be set in channels.yaml "
            f"for channel '{channel_cfg.slug}'.\n"
            "Create an OAuth 2.0 Client ID (Desktop app type) in Google Cloud Console → "
            "APIs & Services → Credentials, then add the values to channels.yaml."
        )
        sys.exit(1)

    setup_youtube_oauth(channel_cfg, token_path)
    print(f"\nYouTube token saved → {token_path}")
    print(
        "\nNOTE: YouTube API projects created after July 2020 may have uploads locked to "
        "private until the GCP project passes a compliance audit.\n"
        "See: https://support.google.com/youtube/contact/yt_api_form"
    )


def cmd_setup_instagram(
    channel_cfg: "config.ChannelConfig",
    token: str | None = None,
) -> None:
    """Exchange an Instagram short-lived token for a long-lived token and save it.

    Fetches the numeric Instagram user ID and saves the token to
    data/channels/{slug}/instagram_token.json.

    Args:
        channel_cfg: Channel configuration (slug used for token path).
        token:       Short-lived access token. If None, prompts the user.
    """
    import datetime
    import requests

    token_path = Path(config.CHANNELS_DIR) / channel_cfg.slug / "instagram_token.json"

    if token is None:
        print(
            "\nTo get a short-lived Instagram access token:\n"
            "  1. Go to https://developers.facebook.com/tools/explorer/\n"
            "  2. Select your Meta App and click 'Generate Access Token'.\n"
            "  3. Grant instagram_content_publish and instagram_basic permissions.\n"
            "  4. Copy the generated token.\n"
        )
        try:
            token = input("Paste your short-lived Instagram access token: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return
        if not token:
            print("ERROR: No token provided.")
            sys.exit(1)

    # Exchange short-lived token for long-lived token
    app_secret = channel_cfg.instagram_access_token  # used as app_secret placeholder
    # Note: the exchange endpoint requires the Meta App Secret (not the access token).
    # We prompt for it if not available on the channel config.
    meta_app_secret = app_secret or ""
    if not meta_app_secret:
        try:
            meta_app_secret = input(
                "Enter your Meta App Secret (from developers.facebook.com → Your App → Settings → Basic): "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return
        if not meta_app_secret:
            print("ERROR: Meta App Secret is required for token exchange.")
            sys.exit(1)

    exchange_url = (
        "https://graph.instagram.com/access_token"
        f"?grant_type=ig_exchange_token"
        f"&client_secret={meta_app_secret}"
        f"&access_token={token}"
    )

    long_lived_token: str | None = None
    expires_in: int = 0
    for attempt in range(1, 4):
        try:
            resp = requests.get(exchange_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            long_lived_token = data["access_token"]
            expires_in = data.get("expires_in", 5183944)  # ~60 days default
            break
        except Exception as exc:
            logger.warning("Instagram token exchange attempt %d/3 failed: %s", attempt, exc)
            if attempt == 3:
                print(f"ERROR: Token exchange failed after 3 attempts: {exc}")
                sys.exit(1)
            time.sleep(2 ** attempt)

    # Fetch numeric user ID and username
    me_url = f"https://graph.instagram.com/me?fields=id,username&access_token={long_lived_token}"
    ig_user_id: str = ""
    ig_username: str = ""
    for attempt in range(1, 4):
        try:
            resp = requests.get(me_url, timeout=10)
            resp.raise_for_status()
            me = resp.json()
            ig_user_id = me.get("id", "")
            ig_username = me.get("username", "")
            break
        except Exception as exc:
            logger.warning("Instagram /me fetch attempt %d/3 failed: %s", attempt, exc)
            if attempt == 3:
                print(f"ERROR: Could not fetch Instagram user info: {exc}")
                sys.exit(1)
            time.sleep(2 ** attempt)

    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=expires_in)
    ).isoformat()

    token_data = {
        "access_token": long_lived_token,
        "user_id": ig_user_id,
        "expires_at": expires_at,
    }

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")

    print(f"\nInstagram token saved → {token_path}")
    print(f"Username: @{ig_username}  |  User ID: {ig_user_id}")
    print(
        "\nReminder: Ensure your Instagram account is a Business or Creator account "
        "connected to a Facebook Page."
    )


def cmd_scrape(fmt: str, window: str,
               channel_cfg: "config.ChannelConfig") -> None:
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


def cmd_review(channel_cfg: "config.ChannelConfig") -> None:
    """Interactive review of pending backlog items for one channel."""
    from analysis.db import get_connection
    from pipeline.backlog import (
        get_pending_stories, get_pending_tweets,
        approve_item, reject_item, get_probation_remaining,
    )
    conn = get_connection()
    try:
        probation_left = get_probation_remaining(conn, channel_cfg.slug)
        if probation_left > 0:
            print(f"\n[{channel_cfg.slug}] Auto-approve activates after "
                  f"{probation_left} more manual review(s).")
        else:
            print(f"\n[{channel_cfg.slug}] Auto-approve is ACTIVE.")

        if channel_cfg.format == "tweets":
            items = get_pending_tweets(conn, channel_cfg.slug)
            source_label = "Twitter"
            table = "backlog_tweets"
            id_key = "tweet_id"
        else:
            items = get_pending_stories(conn, channel_cfg.slug)
            source_label = "Reddit"
            table = "backlog_stories"
            id_key = "id"

        if not items:
            print(f"No pending {source_label} items for [{channel_cfg.slug}].")
            return

        print(f"\nReviewing {len(items)} pending {source_label} item(s) for [{channel_cfg.slug}]")
        print("Commands: y=approve  n=reject  s=skip\n")

        for item in items:
            item_id = item[id_key]
            if source_label == "Reddit":
                print(f"--- Reddit | r/{item['subreddit']} ---")
                print(f"Score: {item['score']:,}  Words: {item['word_count']}")
                print(f"\n{item['title']}\n\n{item['body'][:500]}{'...' if len(item['body']) > 500 else ''}")
            else:
                print(f"--- Twitter | @{item['username']} ---")
                print(f"Likes: {item['likes']:,}  Retweets: {item['retweets']:,}")
                print(f"\n{item['tweet_text']}")

            try:
                choice = input("\nApprove? (y/n/skip): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nReview session ended.")
                break

            if choice == "y":
                approve_item(conn, table, item_id, channel_cfg.slug)
                conn.commit()
                print("  Approved.")
            elif choice == "n":
                reject_item(conn, table, item_id, channel_cfg.slug)
                conn.commit()
                print("  Rejected.")
            else:
                print("  Skipped.")
    finally:
        conn.close()


def cmd_backlog_status(channel_cfg: "config.ChannelConfig | None" = None) -> None:
    """Print backlog counts. channel_cfg=None means all channels."""
    from analysis.db import get_connection
    from pipeline.backlog import get_status_counts
    conn = get_connection()
    try:
        if channel_cfg is not None:
            channels_to_show = [channel_cfg.slug]
        else:
            channels_to_show = list(config.CHANNELS.keys())

        print(f"\n{'Channel':<30} {'Pending':>8} {'Approved':>9} {'Used':>6} {'Rejected':>9}")
        print("-" * 66)
        for slug in channels_to_show:
            counts = get_status_counts(conn, slug)
            ch = counts.get(slug, {"pending": 0, "approved": 0, "used": 0, "rejected": 0})
            print(f"{slug:<30} {ch['pending']:>8} {ch['approved']:>9} {ch['used']:>6} {ch['rejected']:>9}")
    finally:
        conn.close()


def cmd_run_cycle(channel_cfg: "config.ChannelConfig") -> None:
    """Orchestrate one posting cycle for a channel.

    Flow:
      1. Check enabled flag — skip if False.
      2. Pull highest-scored approved item from backlog.
      3. If backlog is empty, run scrape fallback once then re-query.
      4. Generate a video from the item.
      5. Generate upload metadata (title + hashtags) via Claude Haiku.
      6. Upload to YouTube (skip if token missing).
      7. Upload to Instagram (skip if user_id empty or token missing).
      8. Mark item as used in the DB.
      9. Log summary.

    Args:
        channel_cfg: Channel configuration with enabled, format, hashtags,
                     youtube_client_id/secret, instagram_user_id, and slug.
    """
    import os

    slug = channel_cfg.slug

    if not channel_cfg.enabled:
        logger.info("Channel %s is disabled, skipping", slug)
        return

    from analysis.db import get_connection
    from pipeline.backlog import (
        get_approved_stories, get_approved_tweets,
        mark_story_used, mark_used,
    )
    from pipeline.upload import (
        upload_to_youtube, upload_to_instagram,
        generate_upload_metadata, init_upload_table, log_upload,
        refresh_instagram_token_if_needed,
    )

    conn = get_connection()
    try:
        init_upload_table(conn)

        fmt = channel_cfg.format

        # ---------------------------------------------------------------
        # Step 1: Pick best item from backlog
        # ---------------------------------------------------------------
        if fmt == "storytelling":
            rows = get_approved_stories(conn, slug)
            if not rows:
                logger.info("Backlog empty for [%s] — running scrape fallback", slug)
                cmd_scrape("reddit", "week", channel_cfg)
                rows = get_approved_stories(conn, slug)
            if not rows:
                logger.warning(
                    "No approved items for %s after scrape fallback — aborting run-cycle", slug
                )
                return
        else:
            rows = get_approved_tweets(conn, slug)
            if not rows:
                logger.info("Backlog empty for [%s] — running scrape fallback", slug)
                cmd_scrape("tweets", "week", channel_cfg)
                rows = get_approved_tweets(conn, slug)
            if not rows:
                logger.warning(
                    "No approved items for %s after scrape fallback — aborting run-cycle", slug
                )
                return

        row = rows[0]

        # ---------------------------------------------------------------
        # Step 2: Generate video
        # ---------------------------------------------------------------
        video_path: str | None = None

        if fmt == "storytelling":
            from formats.storytelling.generator import adapt_reddit_post
            from formats.storytelling.quality import check_quality

            profile: dict | None = None
            if channel_cfg.style_profile:
                profile_path = Path(channel_cfg.style_profile)
                if profile_path.exists():
                    try:
                        profile = json.loads(profile_path.read_text())
                    except Exception as exc:
                        logger.warning("Failed to load style profile %s: %s", profile_path, exc)

            post = {
                "title": row["title"],
                "body": row["body"],
                "subreddit": row["subreddit"],
                "score": row["score"],
            }

            story = _generate_with_quality(
                generate_fn=lambda p=post: adapt_reddit_post(p, slug, profile),
                quality_fn=lambda s: check_quality(s, profile) if profile else {"passed": True, "overall": 10.0},
                label="run-cycle-story",
            )
            if story is None:
                logger.error("run-cycle: story generation failed for %s — aborting", slug)
                return

            background = _pick_background()
            video_path = _run_storytelling_pipeline(story["story_text"], background)
            content_text = story["story_text"]

        else:  # tweets
            from formats.tweets.renderer import render_tweet
            from formats.tweets.assembler import assemble_tweet_video

            tweet = {
                "tweet_id": row["tweet_id"],
                "tweet_text": row["tweet_text"],
                "username": row["username"],
                "likes": row["likes"],
                "retweets": row["retweets"],
            }
            video_path = _run_tweet_pipeline(tweet, render_tweet, assemble_tweet_video)
            content_text = row["tweet_text"]

        if not video_path:
            logger.error("run-cycle: video generation failed for %s — aborting", slug)
            return

        # ---------------------------------------------------------------
        # Step 3: Generate upload metadata
        # ---------------------------------------------------------------
        metadata = generate_upload_metadata(content_text, channel_cfg.hashtags, fmt)
        title = metadata["title"]
        hashtags = metadata["hashtags"]
        description = f"{title}\n\n#{'  #'.join(hashtags)}" if hashtags else title

        # ---------------------------------------------------------------
        # Step 4: Upload to YouTube
        # ---------------------------------------------------------------
        yt_token_path = Path(config.CHANNELS_DIR) / slug / "youtube_token.json"
        yt_status = "skipped"

        if not yt_token_path.exists():
            logger.warning(
                "No YouTube token for %s — skipping YouTube upload", slug
            )
        else:
            try:
                video_id = upload_to_youtube(
                    video_path,
                    title,
                    description,
                    hashtags,
                    yt_token_path,
                    channel_cfg.youtube_client_id,
                    channel_cfg.youtube_client_secret,
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
        ig_status = "skipped"

        if not channel_cfg.instagram_user_id or not ig_token_path.exists():
            logger.info("Instagram not configured for %s — skipping", slug)
        else:
            public_base_url = os.environ.get("INSTAGRAM_PUBLIC_BASE_URL", "")
            if not public_base_url:
                logger.warning(
                    "INSTAGRAM_PUBLIC_BASE_URL not set — skipping Instagram upload for %s", slug
                )
            else:
                import os.path as osp
                video_url = f"{public_base_url.rstrip('/')}/{osp.basename(video_path)}"
                caption = f"{title}\n\n#{'  #'.join(hashtags)}" if hashtags else title

                try:
                    access_token = refresh_instagram_token_if_needed(ig_token_path)
                    media_id = upload_to_instagram(
                        video_url,
                        caption,
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
        # Step 6: Mark item as used
        # ---------------------------------------------------------------
        if fmt == "storytelling":
            mark_story_used(conn, row["id"])
        else:
            mark_used(conn, "backlog_tweets", row["tweet_id"])
        conn.commit()

        logger.info(
            "Run cycle complete for %s: YouTube=%s, Instagram=%s",
            slug, yt_status, ig_status,
        )

    finally:
        conn.close()


def cmd_upload_history(
    channel_cfg: "config.ChannelConfig",
    limit: int = 20,
) -> None:
    """Print a formatted table of recent uploads for the given channel.

    Args:
        channel_cfg: Channel configuration; slug used to filter records.
        limit:       Maximum number of records to display.
    """
    from analysis.db import get_connection
    from pipeline.upload import get_upload_history

    conn = get_connection()
    try:
        records = get_upload_history(conn, channel_cfg.slug, limit)
    finally:
        conn.close()

    if not records:
        print(f"No upload records found for [{channel_cfg.slug}].")
        return

    # Table header
    print(f"\n{'Date':<28} {'Platform':<12} {'Video ID':<18} {'Status':<9} {'Title'}")
    print("-" * 100)
    for rec in records:
        date = rec.get("uploaded_at", "")[:19].replace("T", " ")
        platform = rec.get("platform", "")
        video_id = rec.get("video_id", "")[:16]
        status = rec.get("status", "")
        title = rec.get("title", "")[:40]
        print(f"{date:<28} {platform:<12} {video_id:<18} {status:<9} {title}")


def _dispatch_command(args: argparse.Namespace, channel_cfg: "config.ChannelConfig") -> None:
    """Route the parsed command to the correct handler for a single channel."""
    if args.command == "analyze":
        cmd_analyze(args.channels, args.visual, args.max_videos, channel_cfg=channel_cfg)
    elif args.command == "generate":
        scrape = getattr(args, "scrape", False)
        from_backlog = getattr(args, "from_backlog", False)
        if not scrape and not from_backlog and not args.profile:
            logger.error("--profile is required unless --scrape or --from-backlog is set")
            sys.exit(1)
        cmd_generate(
            args.format, args.profile, args.count,
            getattr(args, "thread", False),
            scrape=scrape,
            min_likes=getattr(args, "min_likes", 500),
            channel_cfg=channel_cfg,
            from_backlog=from_backlog,
        )
    elif args.command == "setup-twitter":
        cmd_setup_twitter(
            args.username, args.password, args.email,
            getattr(args, "email_password", None),
            getattr(args, "cookies", None),
            channel_cfg=channel_cfg,
        )
    elif args.command == "scrape":
        cmd_scrape(args.format, args.window, channel_cfg)
    elif args.command == "review":
        cmd_review(channel_cfg)
    elif args.command == "backlog-status":
        cmd_backlog_status(channel_cfg)
    elif args.command == "setup-youtube":
        cmd_setup_youtube(channel_cfg)
    elif args.command == "setup-instagram":
        cmd_setup_instagram(channel_cfg, getattr(args, "token", None))
    elif args.command == "run-cycle":
        cmd_run_cycle(channel_cfg)
    elif args.command == "upload-history":
        cmd_upload_history(channel_cfg, getattr(args, "limit", 20))


if __name__ == "__main__":
    main()
