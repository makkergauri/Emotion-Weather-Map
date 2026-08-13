"""FastAPI entrypoint.

Routing and HTTP concerns only. Anything that decides when to call an external
source lives in pipeline.py.

The read endpoints never block on a full refresh. /api/countries answers from the
cache and schedules any stale work in the background, so the map paints in
milliseconds even on a cold start and fills in as data lands. Single-region
endpoints do fetch inline, because that's one request and the user is looking
directly at the thing they're waiting for.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import config, pipeline
from app.cache import store
from app.models import (
    CityDetail,
    CountryDetail,
    CountrySummary,
    GlobalSummary,
    WeatherCondition,
)
from app.regions import Country, load_catalogue

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("emotion-weather-map")

# One background refresh at a time. Without this guard, a dozen page loads
# against a cold cache would each start their own warm-up and multiply our
# request count by twelve.
_refresh_task: asyncio.Task | None = None


def _schedule_refresh(countries: list[Country], force: bool = False) -> None:
    global _refresh_task
    if not countries:
        return
    if _refresh_task and not _refresh_task.done():
        return
    log.info("Scheduling background refresh for: %s", ", ".join(c.code for c in countries))
    _refresh_task = asyncio.create_task(pipeline.warm_cache(countries, force=force))


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    catalogue = load_catalogue()
    log.info("Serving %d countries", len(catalogue.countries))

    # Warm-up is scheduled, not awaited: uvicorn should be accepting connections
    # immediately, and a cold start otherwise takes 12 x FETCH_DELAY_SECONDS.
    _schedule_refresh(_stale_countries(catalogue.countries))
    yield


app = FastAPI(
    title="Emotion Weather Map",
    description="News-headline sentiment, served as weather.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _stale_countries(countries: list[Country]) -> list[Country]:
    cached = store.all_countries()
    return [
        country
        for country in countries
        if not (
            country.code in cached and store.is_fresh(cached[country.code].fetched_at)
        )
    ]


@app.get("/api/health")
async def health() -> dict:
    """Enough detail to debug a blank map without opening the database."""
    cached = store.all_countries()
    return {
        "status": "ok",
        "countries_cached": len(cached),
        "countries_supported": len(load_catalogue().countries),
        "high_accuracy_mode": config.HIGH_ACCURACY_MODE,
        "news_api_key_present": bool(config.NEWS_API_KEY),
        "cache_ttl_hours": config.CACHE_TTL_HOURS,
    }


@app.get("/api/countries", response_model=list[CountrySummary])
async def list_countries() -> list[CountrySummary]:
    """Every supported country with its current condition — one call, one map."""
    catalogue = load_catalogue()
    cached = store.all_countries()

    summaries = [
        pipeline.to_country_summary(
            country,
            cached.get(country.code)
            or store.CachedRegion(
                score=0.0,
                condition=WeatherCondition.NO_DATA,
                headlines=[],
                fetched_at=store.utc_now(),
            ),
        )
        for country in catalogue.countries
    ]

    _schedule_refresh(_stale_countries(catalogue.countries))
    return summaries


@app.get("/api/countries/{code}", response_model=CountryDetail)
async def country_detail(code: str) -> CountryDetail:
    country = load_catalogue().country(code)
    if not country:
        raise HTTPException(status_code=404, detail=f"'{code}' is not a supported country")

    reading = await pipeline.country_reading(country)
    return pipeline.to_country_detail(country, reading)


@app.get("/api/cities/{city_name}", response_model=CityDetail)
async def city_detail(
    city_name: str,
    country: str | None = Query(
        default=None,
        description="ISO country code. Disambiguates cities that share a name.",
    ),
) -> CityDetail:
    city = load_catalogue().city(city_name, country)
    if not city:
        raise HTTPException(status_code=404, detail=f"'{city_name}' is not a supported city")

    reading = await pipeline.city_reading(city)
    return pipeline.to_city_detail(city, reading)


@app.get("/api/global-summary", response_model=GlobalSummary)
async def global_summary() -> GlobalSummary:
    """Aggregate mood across everything currently reporting."""
    catalogue = load_catalogue()
    cached = store.all_countries()

    summaries = [
        pipeline.to_country_summary(
            country,
            cached.get(country.code)
            or store.CachedRegion(
                score=0.0,
                condition=WeatherCondition.NO_DATA,
                headlines=[],
                fetched_at=store.utc_now(),
            ),
        )
        for country in catalogue.countries
    ]
    return pipeline.build_global_summary(summaries)


@app.post("/api/refresh")
async def force_refresh(
    code: str | None = Query(default=None, description="Refresh one country only"),
) -> dict:
    """Ignore the TTL and re-fetch.

    Exists for demos: a portfolio walkthrough shouldn't be at the mercy of a
    4-hour cache. Deliberately unauthenticated because nothing here is private
    and the endpoint costs a handful of upstream calls — put it behind auth
    before this ever runs somewhere public.
    """
    catalogue = load_catalogue()

    if code:
        country = catalogue.country(code)
        if not country:
            raise HTTPException(status_code=404, detail=f"'{code}' is not supported")
        async with httpx.AsyncClient(timeout=15.0) as client:
            reading = await pipeline.country_reading(country, force=True, client=client)
        return {"refreshed": [country.code], "condition": reading.condition.value}

    _schedule_refresh(catalogue.countries, force=True)
    return {"refreshed": catalogue.codes, "status": "running in background"}
