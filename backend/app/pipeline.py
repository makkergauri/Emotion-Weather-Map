"""Wiring between the cache, the fetchers, the analyser and the response models.

This layer exists so main.py stays a routing table. Everything about *when* to
call an external source, and what to do when that call fails, lives here.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

import httpx

from app import config
from app.cache import store
from app.fetchers.base import FetchError, RawHeadline
from app.fetchers.news_api import fetch_country_headlines
from app.fetchers.rss_fetcher import fetch_rss_headlines
from app.mapping.weather_mapper import condition_for_score
from app.models import (
    CityDetail,
    CityRef,
    CitySummary,
    Confidence,
    CountryDetail,
    CountrySummary,
    ForecastPoint,
    GlobalSummary,
    Headline,
    Source,
    WeatherCondition,
)
from app.regions import City, Country
from app.sentiment.analyzer import MIN_HEADLINES_FOR_CONFIDENCE, analyse, most_influential

log = logging.getLogger(__name__)

# When a source fails we don't persist the failure — a cached NO_DATA row would
# blank the region for the whole 4-hour TTL over what is usually a blip. Instead
# the region is held down in memory just long enough to stop a page refresh from
# hammering an API that has already said no.
FAILURE_COOLDOWN = timedelta(minutes=10)
_cooldowns: dict[str, datetime] = {}

_PUNCTUATION = re.compile(r"[^\w\s]")


def _in_cooldown(key: str, now: datetime) -> bool:
    until = _cooldowns.get(key)
    return until is not None and now < until


def _start_cooldown(key: str, now: datetime) -> None:
    _cooldowns[key] = now + FAILURE_COOLDOWN


def dedupe(headlines: list[RawHeadline]) -> list[RawHeadline]:
    """Drop repeats of the same story.

    Syndication means one wire story can appear a dozen times across a feed with
    only the publisher differing. Left in, it gets a dozen votes in the average.
    Matching on normalised text catches the identical reprints, which is most of
    them; genuinely reworded duplicates get through and that's accepted.
    """
    seen: set[str] = set()
    unique: list[RawHeadline] = []
    for item in headlines:
        key = _PUNCTUATION.sub("", item.title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def confidence_for(condition: WeatherCondition, headline_count: int) -> Confidence:
    if condition is WeatherCondition.NO_DATA:
        return Confidence.NONE
    return Confidence.HIGH if headline_count >= MIN_HEADLINES_FOR_CONFIDENCE else Confidence.LOW


def _no_data() -> store.CachedRegion:
    """A fresh unreachable-region reading. Rebuilt each call so `fetched_at`
    reflects the failed attempt rather than process start."""
    return store.CachedRegion(
        score=0.0,
        condition=WeatherCondition.NO_DATA,
        headlines=[],
        fetched_at=store.utc_now(),
    )


async def country_reading(
    country: Country,
    *,
    force: bool = False,
    client: httpx.AsyncClient | None = None,
) -> store.CachedRegion:
    """Current reading for a country, from cache when it's still fresh."""
    now = store.utc_now()
    cached = store.get_country(country.code)

    if cached and not force and store.is_fresh(cached.fetched_at, now):
        return cached
    if cached and _in_cooldown(country.code, now):
        # The upstream call just failed. Rather than retry immediately, serve the
        # last good reading — it is inside the cooldown window, so it is minutes
        # stale at worst, which is a better answer than a grey pin.
        return cached
    if _in_cooldown(country.code, now):
        return _no_data()

    raw, source = await _fetch_country_headlines_with_fallback(country, client)

    if not raw:
        log.warning("Country '%s' produced no headlines from any source", country.code)
        _start_cooldown(country.code, now)
        return cached if cached else _no_data()

    result = analyse(dedupe(raw))
    if result.condition is WeatherCondition.NO_DATA:
        # The request succeeded but came back empty. Nothing worth caching.
        return _no_data()

    store.save_country(
        country.code, result.score, result.condition, result.headlines, now, source
    )
    store.record_daily_snapshot(country.code, result.score, result.condition, now)
    return store.CachedRegion(
        score=result.score,
        condition=result.condition,
        headlines=result.headlines,
        fetched_at=now,
        source=source,
    )


async def _fetch_country_headlines_with_fallback(
    country: Country,
    client: httpx.AsyncClient | None,
) -> tuple[list[RawHeadline], Source | None]:
    """Try NewsAPI, fall back to an RSS search for the country.

    NewsAPI is preferred because a country's top-headlines feed is an editorial
    front page rather than a keyword match. But its non-US coverage has thinned
    out, and it now answers `status: ok` with an empty article list for several
    supported countries — a success response carrying no news.

    Rather than leave those countries permanently grey, they fall through to the
    same RSS search the city tier uses. That reading is weaker, so which source
    was used is recorded and shown in the UI instead of being hidden.

    A happy side effect: the map fills in completely for someone who clones the
    repo and never gets a key at all.
    """
    try:
        raw = await fetch_country_headlines(country.code, client=client)
        if raw:
            return raw, Source.NEWS_API
        log.info("NewsAPI had no headlines for '%s'; falling back to RSS", country.code)
    except FetchError as exc:
        log.warning("NewsAPI unavailable for '%s' (%s); falling back to RSS", country.code, exc)

    try:
        raw = await fetch_rss_headlines(country.query, client=client)
        return raw, Source.RSS if raw else None
    except FetchError as exc:
        log.warning("RSS fallback also failed for '%s': %s", country.code, exc)
        return [], None


async def city_reading(
    city: City,
    *,
    force: bool = False,
    client: httpx.AsyncClient | None = None,
) -> store.CachedRegion:
    """Current reading for a city. Same contract as country_reading."""
    now = store.utc_now()
    key = f"{city.country_code}:{city.name}"
    cached = store.get_city(city.name, city.country_code)

    if cached and not force and store.is_fresh(cached.fetched_at, now):
        return cached
    if cached and _in_cooldown(key, now):
        return cached
    if _in_cooldown(key, now):
        return _no_data()

    try:
        raw = await fetch_rss_headlines(city.query, client=client)
    except FetchError as exc:
        log.warning("City '%s' unavailable: %s", city.name, exc)
        _start_cooldown(key, now)
        return cached if cached else _no_data()

    result = analyse(dedupe(raw))
    if result.condition is WeatherCondition.NO_DATA:
        return _no_data()

    store.save_city(
        city.name,
        city.country_code,
        result.score,
        result.condition,
        result.headlines,
        now,
        Source.RSS,
    )
    return store.CachedRegion(
        score=result.score,
        condition=result.condition,
        headlines=result.headlines,
        fetched_at=now,
        source=Source.RSS,
    )


def to_country_summary(country: Country, reading: store.CachedRegion) -> CountrySummary:
    return CountrySummary(
        code=country.code,
        name=country.name,
        lat=country.lat,
        lng=country.lng,
        score=reading.score,
        condition=reading.condition,
        headline_count=len(reading.headlines),
        confidence=confidence_for(reading.condition, len(reading.headlines)),
        source=reading.source,
        updated_at=reading.fetched_at,
    )


def to_country_detail(country: Country, reading: store.CachedRegion) -> CountryDetail:
    return CountryDetail(
        **to_country_summary(country, reading).model_dump(),
        bounds=country.bounds,
        headlines=most_influential(reading.headlines),
        forecast=forecast_for(country.code),
        cities=[CityRef(name=c.name, lat=c.lat, lng=c.lng) for c in country.cities],
    )


def to_city_summary(city: City, reading: store.CachedRegion) -> CitySummary:
    return CitySummary(
        name=city.name,
        country_code=city.country_code,
        lat=city.lat,
        lng=city.lng,
        score=reading.score,
        condition=reading.condition,
        headline_count=len(reading.headlines),
        confidence=confidence_for(reading.condition, len(reading.headlines)),
        source=reading.source,
        updated_at=reading.fetched_at,
    )


def to_city_detail(city: City, reading: store.CachedRegion) -> CityDetail:
    return CityDetail(
        **to_city_summary(city, reading).model_dump(),
        country_name=city.country_name,
        headlines=most_influential(reading.headlines),
    )


def forecast_for(country_code: str) -> list[ForecastPoint]:
    """The trailing 7-day strip.

    Only days we actually recorded are returned — gaps are not backfilled with
    neutral placeholders, because a flat grey square is indistinguishable from a
    genuinely neutral day. A new install shows a short strip that fills in.
    """
    return [
        ForecastPoint(
            date=row["day"],
            score=row["score"],
            condition=WeatherCondition(row["weather_condition"]),
        )
        for row in store.get_daily_snapshots(country_code)
    ]


def build_global_summary(summaries: list[CountrySummary]) -> GlobalSummary:
    """Planet mood: the mean of every country currently reporting.

    Unweighted by population on purpose. Weighting would turn "the average
    country's news is grim" into "the average person's news is grim", which is a
    much stronger claim than headline sentiment can support.
    """
    reporting = [s for s in summaries if s.condition is not WeatherCondition.NO_DATA]
    if not reporting:
        return GlobalSummary(
            score=0.0,
            condition=WeatherCondition.NO_DATA,
            countries_reporting=0,
            countries_total=len(summaries),
        )

    mean = round(sum(s.score for s in reporting) / len(reporting), 4)
    return GlobalSummary(
        score=mean,
        condition=condition_for_score(mean),
        countries_reporting=len(reporting),
        countries_total=len(summaries),
        brightest=max(reporting, key=lambda s: s.score).name,
        stormiest=min(reporting, key=lambda s: s.score).name,
        updated_at=max((s.updated_at for s in reporting if s.updated_at), default=None),
    )


async def warm_cache(countries: list[Country], force: bool = False) -> None:
    """Fill an empty cache one country at a time.

    Sequential with a delay, not gathered: twelve simultaneous requests is
    exactly the pattern that gets a free-tier key throttled, and nobody is
    waiting on this — it runs in the background while the server serves whatever
    it already has.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        for index, country in enumerate(countries):
            try:
                await country_reading(country, force=force, client=client)
            except Exception:  # noqa: BLE001 - warm-up must never kill the task
                log.exception("Warm-up failed for '%s'", country.code)
            if index < len(countries) - 1:
                await asyncio.sleep(config.FETCH_DELAY_SECONDS)
    log.info("Cache warm-up finished for %d countries", len(countries))
