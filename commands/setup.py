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
    """Set up Instagram upload using a Facebook Page access token.

    Uses a Facebook Page token (EAAG...) to:
      1. Find the Instagram Business account linked to the Page
      2. Extend the token to long-lived if needed
      3. Save token + Instagram user ID to instagram_token.json
    """
    import datetime
    import requests

    token_path = Path(config.CHANNELS_DIR) / channel_cfg.slug / "instagram_token.json"

    if token is None:
        print(
            "\nTo get a Facebook Page access token:\n"
            "  1. Go to https://developers.facebook.com/tools/explorer/\n"
            "  2. Select your Meta App.\n"
            "  3. Add permission: instagram_content_publish\n"
            "  4. Click 'Generate Access Token' — authorize with Facebook.\n"
            "  5. Copy the token (starts with EAAG).\n"
        )
        try:
            token = input("Paste your Facebook Page access token: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return
        if not token:
            print("ERROR: No token provided.")
            sys.exit(1)

    access_token = token

    # Step 1: Get the Instagram account linked to the Facebook Page
    # First find the user's pages to get the page ID
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            pages_url = (
                "https://graph.facebook.com/v19.0/me/accounts"
                f"?access_token={access_token}"
            )
            resp = requests.get(pages_url, timeout=10)
            resp.raise_for_status()
            pages_data = resp.json()
            pages = pages_data.get("data", [])
            if not pages:
                print("ERROR: No Facebook Pages found for this token.")
                print("Make sure your Facebook Page is created and the token has manage_pages permission.")
                sys.exit(1)
            break
        except Exception as exc:
            logger.warning("Facebook pages fetch attempt %d/3 failed: %s", attempt, exc)
            if attempt == _MAX_RETRIES:
                print(f"ERROR: Could not fetch Facebook Pages: {exc}")
                sys.exit(1)
            time.sleep(2 ** attempt)

    # Find the Instagram business account from each page
    ig_user_id: str = ""
    ig_username: str = ""
    page_token: str = ""
    for page in pages:
        page_id = page.get("id", "")
        page_token = page.get("access_token", "")
        try:
            ig_url = (
                f"https://graph.facebook.com/v19.0/{page_id}"
                f"?fields=instagram_business_account{{id,username}}"
                f"&access_token={page_token}"
            )
            resp = requests.get(ig_url, timeout=10)
            resp.raise_for_status()
            ig_data = resp.json()
            ig_biz = ig_data.get("instagram_business_account", {})
            if ig_biz.get("id"):
                ig_user_id = ig_biz["id"]
                ig_username = ig_biz.get("username", "")
                access_token = page_token  # Use the page-specific token
                break
        except Exception:
            continue

    if not ig_user_id:
        print(
            "ERROR: Could not find an Instagram Business account linked to your Facebook Page.\n"
            "Make sure your Instagram account is a Business or Creator account "
            "connected to a Facebook Page in Facebook Settings."
        )
        sys.exit(1)

    # Step 2: Extend to long-lived token (60 days)
    expires_in = 5183944  # ~60 days
    try:
        extend_url = (
            "https://graph.facebook.com/v19.0/oauth/access_token"
            f"?grant_type=fb_exchange_token"
            f"&client_id={channel_cfg.youtube_client_id}"
            f"&client_secret={channel_cfg.instagram_access_token}"
            f"&fb_exchange_token={access_token}"
        )
        resp = requests.get(extend_url, timeout=10)
        resp.raise_for_status()
        extend_data = resp.json()
        if extend_data.get("access_token"):
            access_token = extend_data["access_token"]
            expires_in = extend_data.get("expires_in", expires_in)
    except Exception as exc:
        logger.warning("Token extension failed (using original): %s", exc)

    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=expires_in)
    ).isoformat()

    token_data = {
        "access_token": access_token,
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
