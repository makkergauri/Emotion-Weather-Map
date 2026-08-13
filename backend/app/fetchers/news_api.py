"""Country-level headlines from NewsAPI.org (or a GNews-compatible mirror).

Country granularity is the one thing this source does that RSS search can't: it
resolves "what is the front page in Japan right now" without us having to guess
which Japanese outlets to ask.
"""

from __future__ import annotations

import logging

import httpx

from app import config
from app.fetchers.base import FetchError, RawHeadline

log = logging.getLogger(__name__)

# NewsAPI caps pageSize at 100. Forty is comfortably above the 15-20 needed for a
# stable mean while leaving headroom for the ones we drop as unusable below.
PAGE_SIZE = 40
REQUEST_TIMEOUT_SECONDS = 12.0

# NewsAPI substitutes this for articles it has pulled. They arrive with no usable
# text at all, so they'd otherwise be scored as neutral filler.
REMOVED_MARKER = "[Removed]"


async def fetch_country_headlines(
    country_code: str,
    client: httpx.AsyncClient | None = None,
) -> list[RawHeadline]:
    """Top headlines for one country.

    Raises FetchError for anything the caller can't fix — the pipeline turns that
    into a "no data" marker rather than letting one unreachable country take the
    whole map down.
    """
    if not config.NEWS_API_KEY:
        raise FetchError("NEWS_API_KEY is not set; copy .env.example to .env and add a key")

    params = {"country": country_code.lower(), "pageSize": PAGE_SIZE}
    # Header auth rather than an apiKey query param, so keys don't end up in
    # proxy logs or in the exception messages below.
    headers = {"X-Api-Key": config.NEWS_API_KEY}
    url = f"{config.NEWS_API_BASE_URL}/top-headlines"

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise FetchError(f"NewsAPI request for '{country_code}' failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 429:
        raise FetchError(f"NewsAPI rate limit hit while fetching '{country_code}'")
    if response.status_code != 200:
        raise FetchError(
            f"NewsAPI returned HTTP {response.status_code} for '{country_code}'"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise FetchError(f"NewsAPI sent a non-JSON body for '{country_code}'") from exc

    # NewsAPI can return HTTP 200 with an error envelope, so status is checked
    # separately from the HTTP code.
    if payload.get("status") != "ok":
        raise FetchError(
            f"NewsAPI error for '{country_code}': {payload.get('message', 'unknown')}"
        )

    return _parse_articles(payload.get("articles", []))


def _parse_articles(articles: list[dict]) -> list[RawHeadline]:
    headlines: list[RawHeadline] = []
    for article in articles:
        title = (article.get("title") or "").strip()
        if not title or REMOVED_MARKER in title:
            continue
        source = (article.get("source") or {}).get("name") or "Unknown source"
        headlines.append(
            RawHeadline(title=title, source=source, url=article.get("url"))
        )

    if not headlines:
        log.warning("NewsAPI returned %d articles but none were usable", len(articles))
    return headlines
