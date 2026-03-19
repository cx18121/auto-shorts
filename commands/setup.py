"""
commands/setup.py — One-time setup commands for Twitter, YouTube, and Instagram OAuth.
"""

import json
import logging
import sys
import time
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


def cmd_setup_twitter(username: str, password: str, email: str,
                      email_password: str | None,
                      cookies: str | None = None,
                      channel_cfg=None) -> None:
    from formats.tweets.scraper import setup_account
    setup_account(username, password, email, email_password, cookies)
    print(f"Twitter account @{username} added successfully.")


def cmd_setup_youtube(channel_cfg) -> None:
    """Run YouTube OAuth 2.0 desktop flow and save token for the given channel."""
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


def cmd_setup_instagram(channel_cfg, token: str | None = None) -> None:
    """Exchange an Instagram short-lived token for a long-lived token and save it."""
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

    # The exchange endpoint requires the Meta App Secret, not the access token.
    meta_app_secret = channel_cfg.instagram_access_token or ""
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
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(exchange_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            long_lived_token = data["access_token"]
            expires_in = data.get("expires_in", 5183944)  # ~60 days default
            break
        except Exception as exc:
            logger.warning("Instagram token exchange attempt %d/3 failed: %s", attempt, exc)
            if attempt == _MAX_RETRIES:
                print(f"ERROR: Token exchange failed after 3 attempts: {exc}")
                sys.exit(1)
            time.sleep(2 ** attempt)

    me_url = f"https://graph.instagram.com/me?fields=id,username&access_token={long_lived_token}"
    ig_user_id: str = ""
    ig_username: str = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(me_url, timeout=10)
            resp.raise_for_status()
            me = resp.json()
            ig_user_id  = me.get("id", "")
            ig_username = me.get("username", "")
            break
        except Exception as exc:
            logger.warning("Instagram /me fetch attempt %d/3 failed: %s", attempt, exc)
            if attempt == _MAX_RETRIES:
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
