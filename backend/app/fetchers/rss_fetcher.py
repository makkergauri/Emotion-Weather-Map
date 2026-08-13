"""Headlines from Google News RSS search.

No key, no quota, and it will search any string. That makes it the only way to
reach city granularity — no free news API offers a city parameter — and it also
makes it a usable safety net at country level when NewsAPI has no coverage.

The tradeoff either way is that a search feed is noisier than a curated front
page: it returns stories about a place, datelined there, and occasionally ones
that merely mention it. See docs/methodology.md.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote_plus

import feedparser
import httpx

from app.fetchers.base import FetchError, RawHeadline

log = logging.getLogger(__name__)

RSS_BASE_URL = "https://news.google.com/rss/search"
REQUEST_TIMEOUT_SECONDS = 12.0
MAX_ENTRIES = 30

# Google serves a stripped feed to clients that look automated. A plain browser
# UA is enough to get the normal one.
USER_AGENT = "Mozilla/5.0 (compatible; EmotionWeatherMap/1.0; +https://example.com)"


def build_feed_url(query: str) -> str:
    return f"{RSS_BASE_URL}?q={quote_plus(query)}&hl=en"


async def fetch_rss_headlines(
    query: str,
    client: httpx.AsyncClient | None = None,
) -> list[RawHeadline]:
    """Headlines matching a search query.

    Fetches over httpx rather than letting feedparser do its own networking, so
    the timeout, the user agent and the error handling match the other fetcher.
    """
    url = build_feed_url(query)

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        response = await client.get(
            url, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise FetchError(f"RSS request for '{query}' failed: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code != 200:
        raise FetchError(f"RSS feed for '{query}' returned HTTP {response.status_code}")

    # feedparser is synchronous and does real parsing work, so it goes to a
    # thread — twelve of these run back to back during a warm-up and blocking the
    # event loop each time would stall every other request.
    return await asyncio.to_thread(parse_feed, response.content, query)


def parse_feed(raw_xml: bytes | str, query: str = "") -> list[RawHeadline]:
    """Extract headlines from RSS XML.

    Separate from the fetch so it can be tested against a saved feed without a
    network call — which is also why it takes bytes rather than a response.
    """
    parsed = feedparser.parse(raw_xml)

    # feedparser is forgiving to a fault: hand it Google's HTML rate-limit page
    # and it returns a perfectly valid-looking result with no entries and no
    # error. An empty `version` is what actually distinguishes "this was never a
    # feed" from "this is a feed with nothing in it today".
    if not parsed.entries and not parsed.version:
        raise FetchError(
            f"RSS feed for '{query}' could not be parsed: the response was not a feed"
        )

    # bozo means the XML wasn't strictly well-formed. feedparser usually recovers
    # anyway, so it is only fatal when it also found nothing.
    if parsed.bozo and not parsed.entries:
        raise FetchError(
            f"RSS feed for '{query}' could not be parsed: {parsed.get('bozo_exception')}"
        )

    headlines: list[RawHeadline] = []
    for entry in parsed.entries[:MAX_ENTRIES]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        headlines.append(
            RawHeadline(title=title, source=_extract_source(entry), url=entry.get("link"))
        )

    if not headlines:
        log.info("RSS feed for '%s' contained no entries", query)
    return headlines


def _extract_source(entry) -> str:
    """Get the publisher name.

    Google puts it in a <source> element, but that element goes missing on some
    entries, in which case the " - Publisher" suffix on the title is the fallback.
    """
    source = entry.get("source")
    if isinstance(source, dict) and source.get("title"):
        return source["title"].strip()

    title = entry.get("title") or ""
    if " - " in title:
        return title.rsplit(" - ", 1)[1].strip()
    return "Google News"
