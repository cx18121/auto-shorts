"""
config.py — Load environment variables and define shared paths/constants.
"""

from __future__ import annotations

import logging
import os
import re
import yaml
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")
YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

# Optional: path to a Netscape-format YouTube cookies file (exported from browser)
# This bypasses IP bans on transcript fetching. Takes priority over proxy.
# Export from Chrome using the "Get cookies.txt LOCALLY" extension.
YOUTUBE_COOKIES_PATH: str = os.getenv("YOUTUBE_COOKIES_PATH", "")

# Path to Netscape-format X.com cookies for Playwright-based tweet scraping.
# Export from Chrome using the "Get cookies.txt LOCALLY" extension while logged in.
TWITTER_COOKIES_PATH: Path = Path(os.getenv("TWITTER_COOKIES_PATH", "data/x.com_cookies.txt"))

# Optional Webshare proxy for youtube-transcript-api (fallback if no cookies)
WEBSHARE_PROXY_USERNAME: str = os.getenv("WEBSHARE_PROXY_USERNAME", "")
WEBSHARE_PROXY_PASSWORD: str = os.getenv("WEBSHARE_PROXY_PASSWORD", "")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).parent
OUTPUT_DIR: Path = BASE_DIR / "output"
ASSETS_DIR: Path = BASE_DIR / "assets"
DATA_DIR: Path = BASE_DIR / "data"
STYLE_PROFILES_DIR: Path = BASE_DIR / "style_profiles"
LOGS_DIR: Path = BASE_DIR / "logs"

for _d in [OUTPUT_DIR, DATA_DIR, STYLE_PROFILES_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging — console + rotating file
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "pipeline.log"),
    ],
)

# ---------------------------------------------------------------------------
# Channel configuration
# ---------------------------------------------------------------------------

CHANNELS_PATH: Path = BASE_DIR / "channels.yaml"
CHANNELS_DIR: Path = DATA_DIR / "channels"

VALID_FORMATS: frozenset = frozenset({"storytelling", "tweets"})
_VALID_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


@dataclass
class ChannelConfig:
    """Per-niche channel configuration loaded from channels.yaml."""

    slug: str
    name: str
    format: str
    voice_id: str
    subreddits: list
    twitter_accounts: list
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    instagram_access_token: str = ""

    def __post_init__(self) -> None:
        if not _VALID_SLUG_RE.fullmatch(self.slug):
            raise ValueError(
                f"Channel slug '{self.slug}' must be lowercase hyphenated (a-z, 0-9, -). "
                f"Use hyphens, not underscores."
            )
        if self.format not in VALID_FORMATS:
            raise ValueError(
                f"Channel '{self.slug}': format must be one of {sorted(VALID_FORMATS)}, "
                f"got '{self.format}'"
            )
        if not self.subreddits:
            raise ValueError(
                f"Channel '{self.slug}': subreddits list must not be empty"
            )
        if not self.voice_id:
            raise ValueError(
                f"Channel '{self.slug}': voice_id must not be empty"
            )


def load_channels() -> dict[str, ChannelConfig]:
    """Load and validate channels.yaml, create per-channel data dirs, return config dict."""
    if not CHANNELS_PATH.exists():
        raise SystemExit(
            f"\nERROR: channels.yaml not found at {CHANNELS_PATH}\n"
            f"Copy the example and fill in your ElevenLabs voice IDs:\n"
            f"  cp channels.yaml.example channels.yaml\n"
        )
    raw = yaml.safe_load(CHANNELS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            "channels.yaml must be a YAML mapping at the top level "
            "(got None or non-dict — is the file empty?)"
        )
    channels: dict[str, ChannelConfig] = {}
    for slug, data in raw.items():
        if not isinstance(data, dict):
            raise ValueError(f"Channel '{slug}' in channels.yaml must be a YAML mapping")
        try:
            cfg = ChannelConfig(slug=slug, **data)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid config for channel '{slug}': {exc}") from exc
        # Create isolated per-channel data directory
        channel_dir = CHANNELS_DIR / slug
        channel_dir.mkdir(parents=True, exist_ok=True)
        channels[slug] = cfg
    return channels


CHANNELS: dict[str, ChannelConfig] = load_channels()


def get_channel(slug: str) -> ChannelConfig:
    """Return ChannelConfig for the given slug, or raise SystemExit with a clear message."""
    if slug not in CHANNELS:
        available = ", ".join(sorted(CHANNELS.keys()))
        raise SystemExit(
            f"\nERROR: Unknown channel '{slug}'.\n"
            f"Available channels: {available}\n"
        )
    return CHANNELS[slug]
