"""Settings, read once from the environment at import time.

Plain module-level values rather than pydantic-settings: there are eight of them
and adding a dependency to parse eight strings isn't a trade worth making.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Loaded before anything else reads os.environ. override=False so a real shell
# variable (Docker, CI) always beats a stale .env someone forgot to update.
load_dotenv(BACKEND_ROOT / ".env", override=False)


def _int_env(name: str, default: int) -> int:
    """Read an int, falling back if the variable is missing or garbage.

    Refusing to boot because someone typed CACHE_TTL_HOURS=four is not the
    behaviour you want from a portfolio demo at 2am.
    """
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


_raw_key = os.getenv("NEWS_API_KEY", "").strip()

# The placeholder shipped in .env.example is treated as no key at all. Otherwise
# /api/health cheerfully reports a key is present while every country 403s, which
# is exactly the wrong signal at the moment someone is debugging a grey map.
NEWS_API_KEY = "" if _raw_key in {"", "your_key_here"} else _raw_key
NEWS_API_BASE_URL = os.getenv("NEWS_API_BASE_URL", "https://newsapi.org/v2").rstrip("/")

# How long a cached region stays fresh. The free NewsAPI tier allows 100 requests
# a day; 12 countries every 4 hours is 72, which leaves room for manual refreshes.
CACHE_TTL_HOURS = _int_env("CACHE_TTL_HOURS", 4)

# Politeness delay between sequential upstream calls during a full warm-up.
FETCH_DELAY_SECONDS = float(os.getenv("FETCH_DELAY_SECONDS", "1.5"))

# Swaps VADER for a DistilBERT pipeline. Off by default: the model is a ~250MB
# download and roughly 40x slower per headline. See the README for measurements.
HIGH_ACCURACY_MODE = os.getenv("HIGH_ACCURACY_MODE", "false").lower() in {"1", "true", "yes"}

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(BACKEND_ROOT / "data" / "cache.db")))
REGIONS_PATH = Path(os.getenv("REGIONS_PATH", str(BACKEND_ROOT / "data" / "regions.json")))

# Comma-separated ISO codes. Trimming the list is the quickest way to stay inside
# a rate limit, so it's config rather than a constant.
_raw_countries = os.getenv("SUPPORTED_COUNTRIES", "").strip()
SUPPORTED_COUNTRIES = [c.strip().lower() for c in _raw_countries.split(",") if c.strip()]

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
