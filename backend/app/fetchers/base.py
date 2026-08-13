"""Shared vocabulary for the two fetchers.

Both sources return the same shape, which is the whole reason the sentiment and
caching layers don't care whether a region was read from NewsAPI or from RSS.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawHeadline:
    """An unscored headline. Title and source only — no article body, ever."""

    title: str
    source: str
    url: str | None = None


class FetchError(RuntimeError):
    """Raised when a source can't be read.

    Everything that can go wrong upstream — HTTP errors, rate limits, malformed
    XML, an expired key — is funnelled into this one type so the pipeline has a
    single thing to catch and a single response: mark the region as no data.
    """
