"""SQLite cache sitting between the API and the news sources.

Why a cache at all: the free NewsAPI tier is 100 requests a day, and a portfolio
site that anyone can click through would burn that in an afternoon of demos. The
cache means external calls scale with time, not with traffic.

Every timestamp in here is timezone-aware UTC. SQLite has no date type and will
happily store a naive string that later compares wrong against an aware one, so
the conversion happens at both boundaries rather than being assumed.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

from app import config
from app.models import Headline, Source, WeatherCondition

SCHEMA = """
CREATE TABLE IF NOT EXISTS country_sentiment (
    country_code      TEXT PRIMARY KEY,
    score             REAL NOT NULL,
    weather_condition TEXT NOT NULL,
    headlines_json    TEXT NOT NULL,
    fetched_at        TEXT NOT NULL,
    source            TEXT
);

CREATE TABLE IF NOT EXISTS city_sentiment (
    city_name         TEXT NOT NULL,
    country_code      TEXT NOT NULL,
    score             REAL NOT NULL,
    weather_condition TEXT NOT NULL,
    headlines_json    TEXT NOT NULL,
    fetched_at        TEXT NOT NULL,
    source            TEXT,
    PRIMARY KEY (city_name, country_code)
);

-- The two tables above only ever hold the current reading, because a stale row
-- is overwritten on refresh. The 7-day strip needs history that survives that,
-- so it gets its own table keyed by day.
CREATE TABLE IF NOT EXISTS daily_snapshot (
    country_code      TEXT NOT NULL,
    day               TEXT NOT NULL,
    score             REAL NOT NULL,
    weather_condition TEXT NOT NULL,
    PRIMARY KEY (country_code, day)
);
"""

FORECAST_DAYS = 7


@dataclass(frozen=True)
class CachedRegion:
    """One row, decoded."""

    score: float
    condition: WeatherCondition
    headlines: list[Headline]
    fetched_at: datetime
    source: Source | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Short-lived connection per operation.

    A single shared connection would need locking to be safe across the thread
    pool FastAPI uses; these queries are single-row and sub-millisecond, so
    opening one each time is cheaper than the machinery to avoid it.
    """
    config.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the first release. CREATE TABLE IF NOT EXISTS won't add a
# column to a table that already exists, so an existing cache.db needs them
# bolted on — otherwise upgrading means deleting the database and losing the
# snapshot history the forecast strip is built from.
LATE_COLUMNS = {
    "country_sentiment": {"source": "TEXT"},
    "city_sentiment": {"source": "TEXT"},
}


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)

        for table, columns in LATE_COLUMNS.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, sql_type in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


def is_fresh(
    fetched_at: datetime | None,
    now: datetime | None = None,
    ttl_hours: int | None = None,
) -> bool:
    """Is this row still inside its TTL?

    `now` is an argument rather than a call to the clock inside the function so
    the refresh threshold can be tested without waiting four hours or patching
    datetime globally.
    """
    if fetched_at is None:
        return False
    now = now or utc_now()
    ttl = timedelta(hours=ttl_hours if ttl_hours is not None else config.CACHE_TTL_HOURS)
    return (now - fetched_at) < ttl


def _decode(row: sqlite3.Row) -> CachedRegion:
    # Rows written before the source column existed read back as NULL, which is
    # honest: we genuinely don't know where they came from.
    raw_source = row["source"] if "source" in row.keys() else None
    return CachedRegion(
        score=row["score"],
        condition=WeatherCondition(row["weather_condition"]),
        headlines=[Headline(**h) for h in json.loads(row["headlines_json"])],
        fetched_at=_parse_timestamp(row["fetched_at"]),
        source=Source(raw_source) if raw_source else None,
    )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    # Rows written by an older build (or by hand) may be naive. Treating them as
    # UTC is right, because that is the only thing this app ever writes.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _encode_headlines(headlines: list[Headline]) -> str:
    return json.dumps([h.model_dump() for h in headlines])


def get_country(country_code: str) -> CachedRegion | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM country_sentiment WHERE country_code = ?", (country_code.lower(),)
        ).fetchone()
    return _decode(row) if row else None


def save_country(
    country_code: str,
    score: float,
    condition: WeatherCondition,
    headlines: list[Headline],
    now: datetime | None = None,
    source: Source | None = None,
) -> None:
    now = now or utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO country_sentiment
                (country_code, score, weather_condition, headlines_json, fetched_at, source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(country_code) DO UPDATE SET
                score = excluded.score,
                weather_condition = excluded.weather_condition,
                headlines_json = excluded.headlines_json,
                fetched_at = excluded.fetched_at,
                source = excluded.source
            """,
            (
                country_code.lower(),
                score,
                condition.value,
                _encode_headlines(headlines),
                now.isoformat(),
                source.value if source else None,
            ),
        )


def get_city(city_name: str, country_code: str) -> CachedRegion | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM city_sentiment WHERE city_name = ? AND country_code = ?",
            (city_name, country_code.lower()),
        ).fetchone()
    return _decode(row) if row else None


def save_city(
    city_name: str,
    country_code: str,
    score: float,
    condition: WeatherCondition,
    headlines: list[Headline],
    now: datetime | None = None,
    source: Source | None = None,
) -> None:
    now = now or utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO city_sentiment
                (city_name, country_code, score, weather_condition, headlines_json,
                 fetched_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(city_name, country_code) DO UPDATE SET
                score = excluded.score,
                weather_condition = excluded.weather_condition,
                headlines_json = excluded.headlines_json,
                fetched_at = excluded.fetched_at,
                source = excluded.source
            """,
            (
                city_name,
                country_code.lower(),
                score,
                condition.value,
                _encode_headlines(headlines),
                now.isoformat(),
                source.value if source else None,
            ),
        )


def record_daily_snapshot(
    country_code: str,
    score: float,
    condition: WeatherCondition,
    now: datetime | None = None,
) -> None:
    """Write today's reading for the forecast strip.

    Last write of the day wins. With a 4-hour TTL that means the strip shows the
    evening mood for past days — imprecise, but a day only gets one square, and
    the alternative (averaging every refresh) hides swings the strip exists to show.
    """
    now = now or utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_snapshot (country_code, day, score, weather_condition)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(country_code, day) DO UPDATE SET
                score = excluded.score,
                weather_condition = excluded.weather_condition
            """,
            (country_code.lower(), now.date().isoformat(), score, condition.value),
        )


def get_daily_snapshots(country_code: str, days: int = FORECAST_DAYS) -> list[sqlite3.Row]:
    """Most recent days first from SQLite, returned oldest first for the UI."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT day, score, weather_condition
            FROM daily_snapshot
            WHERE country_code = ?
            ORDER BY day DESC
            LIMIT ?
            """,
            (country_code.lower(), days),
        ).fetchall()
    return list(reversed(rows))


def all_countries() -> dict[str, CachedRegion]:
    """Every cached country in one query — the world map needs all of them."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM country_sentiment").fetchall()
    return {row["country_code"]: _decode(row) for row in rows}


def clear() -> None:
    """Wipe the cache. Used by tests and by the /api/admin/refresh path."""
    with connect() as conn:
        conn.executescript(
            "DELETE FROM country_sentiment; DELETE FROM city_sentiment; "
            "DELETE FROM daily_snapshot;"
        )
