import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
DATA_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# --- Free-tier AI (trend keyword normalization) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# --- YouTube Data API (free quota) ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_OAUTH_CLIENT_SECRETS_FILE = os.getenv(
    "YOUTUBE_OAUTH_CLIENT_SECRETS_FILE", str(BASE_DIR / "client_secret.json")
)
YOUTUBE_OAUTH_TOKEN_FILE = os.getenv(
    "YOUTUBE_OAUTH_TOKEN_FILE", str(DATA_DIR / "youtube_oauth_token.json")
)

# YouTube Data API daily quota is 10,000 units by default.
# search.list = 100 units, videos.list = 1 unit, videos.insert = 1600 units.
YOUTUBE_DAILY_QUOTA_BUDGET = int(os.getenv("YOUTUBE_DAILY_QUOTA_BUDGET", "9000"))
MAX_KEYWORDS_PER_RUN = int(os.getenv("MAX_KEYWORDS_PER_RUN", "6"))
MAX_UPLOADS_PER_RUN = int(os.getenv("MAX_UPLOADS_PER_RUN", "2"))  # 1 short + 1 compilation by default

# --- Pipeline behavior ---
# When true, publisher.py logs what it WOULD upload but never calls videos.insert.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("1", "true", "yes")

SHORT_MAX_SECONDS = int(os.getenv("SHORT_MAX_SECONDS", "20"))
COMPILATION_TARGET_SECONDS = int(os.getenv("COMPILATION_TARGET_SECONDS", "300"))
CLIP_SECONDS_PER_SOURCE = int(os.getenv("CLIP_SECONDS_PER_SOURCE", "45"))

# Original source audio is muted by default (a CC license on the video doesn't
# necessarily cover embedded third-party music). Optionally point this at your
# own royalty-free track to overlay instead of silence.
BACKGROUND_MUSIC_PATH = os.getenv("BACKGROUND_MUSIC_PATH", "")

DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "pipeline.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

CHANNEL_BRAND_NAME = os.getenv("CHANNEL_BRAND_NAME", "ReelPulse")

# Start with "private" or "unlisted" while you build trust in the pipeline;
# flip to "public" once you've manually checked a few real uploads.
DEFAULT_PRIVACY_STATUS = os.getenv("DEFAULT_PRIVACY_STATUS", "private")
