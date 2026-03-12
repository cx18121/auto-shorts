"""
pipeline/upload.py — YouTube and Instagram upload helpers.

Currently provides OAuth setup flows for both platforms.
Actual video upload logic will be added in a later plan.
"""

from __future__ import annotations

import json
import logging
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import config as config_module

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YouTube OAuth setup
# ---------------------------------------------------------------------------

_YOUTUBE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_YOUTUBE_TOKEN_URI = "https://oauth2.googleapis.com/token"
_YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

_MAX_RETRIES = 3


def setup_youtube_oauth(
    channel_cfg: "config_module.ChannelConfig",
    token_path: Path,
) -> dict:
    """Run the YouTube OAuth 2.0 device/desktop flow and save the token.

    Opens the user's browser to the Google consent screen. The user
    approves access, then pastes the authorization code back into the
    terminal. The code is exchanged for access + refresh tokens which
    are written to token_path.

    Args:
        channel_cfg: ChannelConfig with youtube_client_id and youtube_client_secret.
        token_path:  Path where the resulting token JSON will be written.

    Returns:
        The token dict that was saved to disk.

    Raises:
        RuntimeError: If the OAuth exchange fails after retries.
    """
    try:
        import requests
    except ImportError as e:
        raise RuntimeError("requests library required: pip install requests") from e

    client_id = channel_cfg.youtube_client_id
    client_secret = channel_cfg.youtube_client_secret
    redirect_uri = "urn:ietf:wg:oauth:2.0:oob"

    # Build authorization URL
    scope = " ".join(_YOUTUBE_SCOPES)
    auth_url = (
        f"{_YOUTUBE_AUTH_URI}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    print("\nOpening browser for YouTube OAuth authorization...")
    print(f"If the browser does not open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    auth_code = input("Paste the authorization code from Google here: ").strip()
    if not auth_code:
        raise RuntimeError("No authorization code provided.")

    # Exchange authorization code for tokens
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.post(
                _YOUTUBE_TOKEN_URI,
                data={
                    "code": auth_code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
            resp.raise_for_status()
            token = resp.json()
            break
        except Exception as exc:
            logger.warning("YouTube token exchange attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"YouTube OAuth exchange failed after {_MAX_RETRIES} attempts: {exc}") from exc
            time.sleep(2 ** attempt)

    # Annotate with expiry timestamp
    token["obtained_at"] = time.time()

    # Ensure parent directory exists
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token, indent=2), encoding="utf-8")
    logger.info("YouTube token saved → %s", token_path)
    return token
