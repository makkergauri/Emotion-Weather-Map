"""Tests for the SQLite cache.

The freshness rule is the one piece of logic here that costs real money to get
wrong — too eager and the free-tier key is exhausted by lunchtime — so the clock
is supplied by the test rather than patched globally.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import config
from app.cache import store
from app.models import Headline, Source, WeatherCondition

NOON = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the store at a throwaway database for every test."""
    monkeypatch.setattr(config, "SQLITE_PATH", tmp_path / "test-cache.db")
    store.init_db()
    yield


@pytest.fixture
def headlines():
    return [
        Headline(title="Rail link opens early", source="The Times", url="https://x", score=0.62),
        Headline(title="Flooding closes two roads", source="Local Wire", score=-0.55),
    ]


# --- freshness ---------------------------------------------------------------


def test_a_row_written_now_is_fresh():
    assert store.is_fresh(NOON, now=NOON, ttl_hours=4)


@pytest.mark.parametrize("hours", [0.5, 1, 3, 3.99])
def test_rows_inside_the_ttl_are_fresh(hours):
    assert store.is_fresh(NOON - timedelta(hours=hours), now=NOON, ttl_hours=4)


@pytest.mark.parametrize("hours", [4, 4.01, 12, 240])
def test_rows_at_or_past_the_ttl_are_stale(hours):
    """Exactly 4 hours old counts as stale — the window is exclusive at the top."""
    assert not store.is_fresh(NOON - timedelta(hours=hours), now=NOON, ttl_hours=4)


def test_missing_timestamp_is_never_fresh():
    assert not store.is_fresh(None, now=NOON)


def test_ttl_is_configurable():
    two_hours_old = NOON - timedelta(hours=2)
    assert store.is_fresh(two_hours_old, now=NOON, ttl_hours=4)
    assert not store.is_fresh(two_hours_old, now=NOON, ttl_hours=1)


def test_ttl_falls_back_to_config(monkeypatch):
    monkeypatch.setattr(config, "CACHE_TTL_HOURS", 6)
    assert store.is_fresh(NOON - timedelta(hours=5), now=NOON)
    assert not store.is_fresh(NOON - timedelta(hours=7), now=NOON)


def test_a_row_goes_stale_as_the_clock_advances(headlines):
    """The scenario the TTL actually exists for, walked end to end."""
    store.save_country("in", -0.2, WeatherCondition.RAINY, headlines, now=NOON)
    cached = store.get_country("in")

    assert store.is_fresh(cached.fetched_at, now=NOON + timedelta(hours=3, minutes=59))
    assert not store.is_fresh(cached.fetched_at, now=NOON + timedelta(hours=4, minutes=1))


# --- round trips -------------------------------------------------------------


def test_country_round_trip_preserves_everything(headlines):
    store.save_country("gb", 0.31, WeatherCondition.PARTLY_CLOUDY, headlines, now=NOON)
    cached = store.get_country("gb")

    assert cached.score == pytest.approx(0.31)
    assert cached.condition is WeatherCondition.PARTLY_CLOUDY
    assert cached.fetched_at == NOON
    assert [h.title for h in cached.headlines] == [h.title for h in headlines]
    assert cached.headlines[0].url == "https://x"


def test_country_codes_are_case_insensitive(headlines):
    store.save_country("JP", 0.1, WeatherCondition.OVERCAST, headlines, now=NOON)
    assert store.get_country("jp") is not None
    assert store.get_country("Jp") is not None


def test_unknown_country_returns_none():
    assert store.get_country("zz") is None


def test_saving_twice_updates_rather_than_duplicates(headlines):
    store.save_country("us", -0.9, WeatherCondition.THUNDERSTORM, headlines, now=NOON)
    later = NOON + timedelta(hours=5)
    store.save_country("us", 0.7, WeatherCondition.SUNNY, [], now=later)

    cached = store.get_country("us")
    assert cached.condition is WeatherCondition.SUNNY
    assert cached.headlines == []
    assert cached.fetched_at == later
    assert len(store.all_countries()) == 1


def test_cities_with_the_same_name_in_different_countries_stay_separate(headlines):
    store.save_city("Birmingham", "gb", 0.2, WeatherCondition.PARTLY_CLOUDY, headlines, now=NOON)
    store.save_city("Birmingham", "us", -0.6, WeatherCondition.THUNDERSTORM, [], now=NOON)

    assert store.get_city("Birmingham", "gb").score == pytest.approx(0.2)
    assert store.get_city("Birmingham", "us").score == pytest.approx(-0.6)


def test_naive_timestamps_are_read_back_as_utc(headlines):
    """Guards the boundary where a hand-edited row would otherwise blow up
    comparisons between naive and aware datetimes."""
    store.save_country("fr", 0.0, WeatherCondition.OVERCAST, headlines, now=NOON)
    with store.connect() as conn:
        conn.execute(
            "UPDATE country_sentiment SET fetched_at = ? WHERE country_code = 'fr'",
            ("2026-08-11T12:00:00",),
        )

    cached = store.get_country("fr")
    assert cached.fetched_at == NOON
    assert store.is_fresh(cached.fetched_at, now=NOON + timedelta(hours=1))


# --- daily snapshots ---------------------------------------------------------


def test_snapshots_build_a_seven_day_history():
    for offset in range(7):
        day = NOON - timedelta(days=6 - offset)
        store.record_daily_snapshot("de", offset / 10, WeatherCondition.SUNNY, now=day)

    snapshots = store.get_daily_snapshots("de")
    assert len(snapshots) == 7
    assert snapshots[0]["day"] == "2026-08-05"
    assert snapshots[-1]["day"] == "2026-08-11"


def test_snapshots_are_returned_oldest_first():
    for offset in range(3):
        store.record_daily_snapshot(
            "ca", 0.1, WeatherCondition.OVERCAST, now=NOON - timedelta(days=offset)
        )
    days = [row["day"] for row in store.get_daily_snapshots("ca")]
    assert days == sorted(days)


def test_repeat_snapshots_on_one_day_overwrite():
    """Four refreshes a day, one square on the strip — the last one wins."""
    store.record_daily_snapshot("au", -0.8, WeatherCondition.THUNDERSTORM, now=NOON)
    store.record_daily_snapshot(
        "au", 0.6, WeatherCondition.SUNNY, now=NOON + timedelta(hours=6)
    )

    snapshots = store.get_daily_snapshots("au")
    assert len(snapshots) == 1
    assert snapshots[0]["score"] == pytest.approx(0.6)


def test_snapshot_history_is_capped_at_the_window():
    for offset in range(20):
        store.record_daily_snapshot(
            "br", 0.0, WeatherCondition.OVERCAST, now=NOON - timedelta(days=offset)
        )
    assert len(store.get_daily_snapshots("br")) == store.FORECAST_DAYS


def test_clear_empties_every_table(headlines):
    store.save_country("sg", 0.4, WeatherCondition.PARTLY_CLOUDY, headlines, now=NOON)
    store.save_city("Jurong", "sg", 0.4, WeatherCondition.PARTLY_CLOUDY, headlines, now=NOON)
    store.record_daily_snapshot("sg", 0.4, WeatherCondition.PARTLY_CLOUDY, now=NOON)

    store.clear()

    assert store.all_countries() == {}
    assert store.get_city("Jurong", "sg") is None
    assert store.get_daily_snapshots("sg") == []


# --- source labelling --------------------------------------------------------


def test_source_round_trips(headlines):
    store.save_country(
        "za", 0.1, WeatherCondition.OVERCAST, headlines, now=NOON, source=Source.RSS
    )
    assert store.get_country("za").source is Source.RSS


def test_source_defaults_to_unknown(headlines):
    """Not every write knows its origin, and guessing would be worse."""
    store.save_country("za", 0.1, WeatherCondition.OVERCAST, headlines, now=NOON)
    assert store.get_country("za").source is None


def test_init_db_adds_the_source_column_to_an_older_database(tmp_path, monkeypatch):
    """Upgrading must not mean deleting cache.db and losing snapshot history."""
    legacy = tmp_path / "legacy.db"
    monkeypatch.setattr(config, "SQLITE_PATH", legacy)

    # Build the pre-source schema by hand, then put a row in it.
    with store.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE country_sentiment (
                country_code TEXT PRIMARY KEY, score REAL NOT NULL,
                weather_condition TEXT NOT NULL, headlines_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE city_sentiment (
                city_name TEXT NOT NULL, country_code TEXT NOT NULL, score REAL NOT NULL,
                weather_condition TEXT NOT NULL, headlines_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL, PRIMARY KEY (city_name, country_code)
            );
            """
        )
        conn.execute(
            "INSERT INTO country_sentiment VALUES ('in', -0.2, 'rainy', '[]', ?)",
            (NOON.isoformat(),),
        )

    store.init_db()

    migrated = store.get_country("in")
    assert migrated is not None, "the existing row survived the migration"
    assert migrated.source is None
    assert migrated.score == pytest.approx(-0.2)

    # And the new column is now writable.
    store.save_country("in", 0.3, WeatherCondition.PARTLY_CLOUDY, [], now=NOON, source=Source.RSS)
    assert store.get_country("in").source is Source.RSS


def test_init_db_is_safe_to_run_repeatedly(headlines):
    store.save_country("in", 0.1, WeatherCondition.OVERCAST, headlines, now=NOON)
    store.init_db()
    store.init_db()
    assert store.get_country("in") is not None
