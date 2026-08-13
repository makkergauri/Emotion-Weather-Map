"""Loads regions.json and exposes it as lookups the rest of the app can use.

Two reasons this isn't just `json.load` at the call site: the file is read once
per process instead of once per request, and city names arrive from the URL path
in whatever case the user typed, so lookups need to be case-insensitive in one
place rather than five.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from app import config


@dataclass(frozen=True)
class City:
    name: str
    query: str
    lat: float
    lng: float
    country_code: str
    country_name: str


@dataclass(frozen=True)
class Country:
    code: str
    name: str
    #: Search string for the RSS fallback, used only when NewsAPI has nothing.
    query: str
    lat: float
    lng: float
    bounds: list[list[float]]
    cities: list[City]


@dataclass(frozen=True)
class Catalogue:
    countries: list[Country]

    @property
    def codes(self) -> list[str]:
        return [c.code for c in self.countries]

    def country(self, code: str) -> Country | None:
        code = code.lower()
        return next((c for c in self.countries if c.code == code), None)

    def city(self, name: str, country_code: str | None = None) -> City | None:
        """Find a city by name, optionally disambiguated by country.

        City names are unique across the current catalogue, but that's luck
        rather than design — the moment someone adds a second Springfield the
        country_code argument is what keeps /api/cities/{name} honest.
        """
        target = name.strip().lower()
        for country in self.countries:
            if country_code and country.code != country_code.lower():
                continue
            for city in country.cities:
                if city.name.lower() == target:
                    return city
        return None

    @property
    def all_cities(self) -> list[City]:
        return [city for country in self.countries for city in country.cities]


@lru_cache(maxsize=1)
def load_catalogue() -> Catalogue:
    raw = json.loads(config.REGIONS_PATH.read_text(encoding="utf-8"))

    countries: list[Country] = []
    for entry in raw["countries"]:
        code = entry["code"].lower()

        # SUPPORTED_COUNTRIES lets an operator shrink the map without editing
        # the catalogue; an empty setting means "everything in the file".
        if config.SUPPORTED_COUNTRIES and code not in config.SUPPORTED_COUNTRIES:
            continue

        cities = [
            City(
                name=c["name"],
                query=c.get("query", f"{c['name']} {entry['name']}"),
                lat=c["lat"],
                lng=c["lng"],
                country_code=code,
                country_name=entry["name"],
            )
            for c in entry.get("cities", [])
        ]
        countries.append(
            Country(
                code=code,
                name=entry["name"],
                query=entry.get("query", f"{entry['name']} news"),
                lat=entry["lat"],
                lng=entry["lng"],
                bounds=entry["bounds"],
                cities=cities,
            )
        )

    if not countries:
        raise RuntimeError(
            "No countries loaded. Check regions.json and the SUPPORTED_COUNTRIES setting."
        )
    return Catalogue(countries=countries)
