"""Response models for the public API.

These are the contract the frontend codes against, so they deliberately stay
flatter than the internal shapes — the map component wants `lat`/`lng`/
`condition` on one object, not a nested geometry blob it has to unpack.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class WeatherCondition(str, Enum):
    """The five real conditions, plus a sixth for regions we couldn't reach.

    NO_DATA is not something the sentiment mapper can ever produce — it is set
    by the pipeline when a fetch fails, so a broken NewsAPI response shows up on
    the map as an honest grey marker instead of a misleading "overcast" one.
    """

    SUNNY = "sunny"
    PARTLY_CLOUDY = "partly_cloudy"
    OVERCAST = "overcast"
    RAINY = "rainy"
    THUNDERSTORM = "thunderstorm"
    NO_DATA = "no_data"


class Confidence(str, Enum):
    """How much weight to put on a region's score.

    Averaging sentiment over four headlines is noise; over twenty it starts to
    mean something. The frontend dims low-confidence markers rather than hiding
    them, so the distinction has to survive the trip over the wire.
    """

    HIGH = "high"
    LOW = "low"
    NONE = "none"


class Source(str, Enum):
    """Which feed a reading came from.

    Surfaced to the client because a country served by the RSS fallback is a
    weaker reading than one from a curated front page, and the panel should be
    able to say so rather than presenting both as equivalent.
    """

    NEWS_API = "newsapi"
    RSS = "rss"


class Headline(BaseModel):
    """One scored headline. Title and source only — see the no-scraping rule."""

    title: str
    source: str
    url: str | None = None
    score: float = Field(description="Compound sentiment for this headline, -1..1")


class ForecastPoint(BaseModel):
    """One day of the trailing 7-day strip."""

    date: str = Field(description="ISO date, YYYY-MM-DD, in UTC")
    score: float
    condition: WeatherCondition


class CityRef(BaseModel):
    """A drill-down target advertised on the country detail response."""

    name: str
    lat: float
    lng: float


class RegionWeather(BaseModel):
    """Fields every region shares, whatever its granularity."""

    score: float = Field(description="Mean compound sentiment, -1..1")
    condition: WeatherCondition
    headline_count: int
    confidence: Confidence
    source: Source | None = None
    updated_at: datetime | None = None


class CountrySummary(RegionWeather):
    """One pin on the world map."""

    code: str
    name: str
    lat: float
    lng: float


class CountryDetail(CountrySummary):
    """Everything the side panel needs for a country, in one request."""

    bounds: list[list[float]] = Field(
        description="[[south, west], [north, east]] — passed straight to Leaflet"
    )
    headlines: list[Headline] = []
    forecast: list[ForecastPoint] = []
    cities: list[CityRef] = []


class CitySummary(RegionWeather):
    """One pin in the drill-down view."""

    name: str
    country_code: str
    lat: float
    lng: float


class CityDetail(CitySummary):
    """City panel payload. No forecast strip — see docs/methodology.md."""

    country_name: str
    headlines: list[Headline] = []


class GlobalSummary(BaseModel):
    """The planet mood readout in the header."""

    score: float
    condition: WeatherCondition
    countries_reporting: int
    countries_total: int
    brightest: str | None = Field(default=None, description="Sunniest country name")
    stormiest: str | None = Field(default=None, description="Darkest country name")
    updated_at: datetime | None = None
