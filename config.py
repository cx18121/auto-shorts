"""
config.py — Load environment variables and define shared paths/constants.
"""

import logging
import os
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
