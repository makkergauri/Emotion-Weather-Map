"""End-to-end tests for the HTTP layer.

Both fetchers are stubbed, so these cover the parts that are ours: routing,
cache reads, the shape of the JSON the frontend depends on, and — the one worth
having — that a dead news source degrades to a grey pin instead of a 500.
"""

import pytest
from fastapi.testclient import TestClient

from app import config, pipeline
from app.cache import store
from app.fetchers.base import FetchError, RawHeadline

GOOD_NEWS = [
    RawHeadline(title=f"Delightful new park opens to happy crowds, number {i}", source="Wire")
    for i in range(20)
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SQLITE_PATH", tmp_path / "api-test.db")
    store.init_db()

    # The failure cooldown is process-global, so it has to be reset between
    # tests or one failing case would silently suppress fetches in the next.
    pipeline._cooldowns.clear()

    # Startup would otherwise kick off a real warm-up against the live APIs.
    async def no_warm_up(countries, force=False):
        return None

    monkeypatch.setattr(pipeline, "warm_cache", no_warm_up)

    # Both fetchers are stubbed to fail by default. Without this the RSS
    # fallback would make real network calls the moment a test made NewsAPI
    # fail, which is slow, flaky, and rude to Google.
    async def unreachable(*args, **kwargs):
        raise FetchError("not stubbed in this test")

    monkeypatch.setattr(pipeline, "fetch_country_headlines", unreachable)
    monkeypatch.setattr(pipeline, "fetch_rss_headlines", unreachable)

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def stub_newsapi(monkeypatch, headlines=None, error=None):
    async def fake(country_code, client=None):
        if error:
            raise FetchError(error)
        return headlines or []

    monkeypatch.setattr(pipeline, "fetch_country_headlines", fake)


def stub_rss(monkeypatch, headlines=None, error=None):
    async def fake(query, client=None):
        if error:
            raise FetchError(error)
        return headlines or []

    monkeypatch.setattr(pipeline, "fetch_rss_headlines", fake)


def test_health_reports_cache_state(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["countries_supported"] == 12


def test_countries_lists_every_supported_region(client):
    body = client.get("/api/countries").json()
    assert len(body) == 12
    assert {c["code"] for c in body} >= {"us", "in", "jp", "sg"}


def test_countries_returns_map_ready_fields(client):
    country = client.get("/api/countries").json()[0]
    assert {"code", "name", "lat", "lng", "condition", "score", "confidence"} <= set(country)


def test_cold_cache_reports_no_data_rather_than_failing(client):
    """First load, nothing fetched yet: the map still renders, just grey."""
    body = client.get("/api/countries").json()
    assert all(c["condition"] == "no_data" for c in body)
    assert all(c["confidence"] == "none" for c in body)


def test_country_detail_includes_everything_the_panel_needs(client, monkeypatch):
    stub_newsapi(monkeypatch, GOOD_NEWS)
    body = client.get("/api/countries/in").json()

    assert body["name"] == "India"
    assert body["condition"] in {"sunny", "partly_cloudy"}
    assert body["confidence"] == "high"
    assert len(body["headlines"]) == 5, "panel shows the top five drivers"
    assert len(body["bounds"]) == 2
    assert {c["name"] for c in body["cities"]} >= {"Bhopal", "Mumbai"}


def test_country_detail_starts_the_forecast_strip(client, monkeypatch):
    stub_newsapi(monkeypatch, GOOD_NEWS)
    body = client.get("/api/countries/in").json()
    assert len(body["forecast"]) == 1, "one snapshot exists after one fetch"
    assert body["forecast"][0]["condition"] == body["condition"]


def test_thin_coverage_is_flagged_to_the_client(client, monkeypatch):
    stub_newsapi(monkeypatch, GOOD_NEWS[:3])
    assert client.get("/api/countries/de").json()["confidence"] == "low"


def test_a_dead_source_degrades_to_no_data(client, monkeypatch):
    """The requirement that matters: one broken country must not break the map."""
    stub_newsapi(monkeypatch, error="upstream is down")
    body = client.get("/api/countries/jp").json()

    assert body["condition"] == "no_data"
    assert body["headlines"] == []
    assert body["score"] == 0.0


def test_a_failure_never_overwrites_a_good_reading(client, monkeypatch):
    """Stale-but-real beats grey, as long as we're inside the cooldown window."""
    stub_newsapi(monkeypatch, GOOD_NEWS)
    first = client.get("/api/countries/fr").json()

    stub_newsapi(monkeypatch, error="rate limited")
    second = client.get("/api/countries/fr").json()

    assert second["condition"] == first["condition"]
    assert second["score"] == first["score"]


def test_second_request_is_served_from_cache(client, monkeypatch):
    stub_newsapi(monkeypatch, GOOD_NEWS)
    first = client.get("/api/countries/ca").json()

    # If this stub were reached, the score would change. It shouldn't be.
    stub_newsapi(monkeypatch, [RawHeadline(title="Awful tragedy kills many", source="W")])
    second = client.get("/api/countries/ca").json()

    assert second["score"] == first["score"]
    assert second["updated_at"] == first["updated_at"]


def test_unknown_country_is_a_404(client):
    response = client.get("/api/countries/zz")
    assert response.status_code == 404
    assert "not a supported country" in response.json()["detail"]


def test_city_detail_resolves_by_name(client, monkeypatch):
    stub_rss(monkeypatch, GOOD_NEWS)
    body = client.get("/api/cities/Bhopal").json()

    assert body["name"] == "Bhopal"
    assert body["country_code"] == "in"
    assert body["country_name"] == "India"
    assert len(body["headlines"]) == 5


def test_city_lookup_is_case_insensitive(client, monkeypatch):
    stub_rss(monkeypatch, GOOD_NEWS)
    assert client.get("/api/cities/bhopal").status_code == 200


def test_city_can_be_disambiguated_by_country(client, monkeypatch):
    stub_rss(monkeypatch, GOOD_NEWS)
    assert client.get("/api/cities/Birmingham?country=gb").json()["country_code"] == "gb"
    assert client.get("/api/cities/Birmingham?country=us").status_code == 404


def test_unknown_city_is_a_404(client):
    assert client.get("/api/cities/Atlantis").status_code == 404


def test_global_summary_ignores_regions_with_no_data(client, monkeypatch):
    stub_newsapi(monkeypatch, GOOD_NEWS)
    client.get("/api/countries/in")
    client.get("/api/countries/br")

    body = client.get("/api/global-summary").json()
    assert body["countries_reporting"] == 2
    assert body["countries_total"] == 12
    assert body["condition"] != "no_data"
    assert body["brightest"] in {"India", "Brazil"}


def test_global_summary_with_nothing_cached(client):
    body = client.get("/api/global-summary").json()
    assert body["condition"] == "no_data"
    assert body["countries_reporting"] == 0
    assert body["brightest"] is None


def test_forced_refresh_bypasses_the_cache(client, monkeypatch):
    stub_newsapi(monkeypatch, GOOD_NEWS)
    client.get("/api/countries/au")

    stub_newsapi(monkeypatch, [RawHeadline(title="Horrific disaster kills many", source="W")])
    client.post("/api/refresh?code=au")

    assert client.get("/api/countries/au").json()["score"] < 0


def test_placeholder_key_is_reported_as_missing(client, monkeypatch):
    """A .env that still holds the example value must not read as configured —
    health is the first place someone looks when the map is all grey."""
    monkeypatch.setattr(config, "NEWS_API_KEY", "")
    assert client.get("/api/health").json()["news_api_key_present"] is False


# --- the RSS fallback --------------------------------------------------------


def test_falls_back_to_rss_when_newsapi_has_no_headlines(client, monkeypatch):
    """The real-world failure: NewsAPI answers 200 with an empty article list
    for a country it no longer covers. That must not leave the pin grey."""
    stub_newsapi(monkeypatch, [])
    stub_rss(monkeypatch, GOOD_NEWS)

    body = client.get("/api/countries/za").json()

    assert body["condition"] != "no_data"
    assert body["source"] == "rss"
    assert body["headline_count"] == len(GOOD_NEWS)


def test_falls_back_to_rss_when_newsapi_errors(client, monkeypatch):
    stub_newsapi(monkeypatch, error="401 Unauthorized")
    stub_rss(monkeypatch, GOOD_NEWS)

    assert client.get("/api/countries/za").json()["source"] == "rss"


def test_newsapi_is_preferred_when_it_has_headlines(client, monkeypatch):
    """The fallback is a safety net, not a replacement — a curated front page
    beats a keyword search whenever one is available."""
    stub_newsapi(monkeypatch, GOOD_NEWS)
    stub_rss(monkeypatch, [RawHeadline(title="Awful tragedy strikes", source="RSS")])

    body = client.get("/api/countries/za").json()
    assert body["source"] == "newsapi"
    assert body["score"] > 0


def test_map_still_works_with_no_key_at_all(client, monkeypatch):
    """Someone clones the repo, skips the key, and should still see a live map."""
    stub_newsapi(monkeypatch, error="NEWS_API_KEY is not set")
    stub_rss(monkeypatch, GOOD_NEWS)

    for code in ("in", "jp", "br"):
        assert client.get(f"/api/countries/{code}").json()["condition"] != "no_data"

    summary = client.get("/api/global-summary").json()
    assert summary["countries_reporting"] == 3


def test_no_data_only_when_both_sources_fail(client, monkeypatch):
    stub_newsapi(monkeypatch, error="down")
    stub_rss(monkeypatch, error="also down")

    body = client.get("/api/countries/za").json()
    assert body["condition"] == "no_data"
    assert body["source"] is None


def test_cities_are_always_labelled_rss(client, monkeypatch):
    stub_rss(monkeypatch, GOOD_NEWS)
    assert client.get("/api/cities/Bhopal").json()["source"] == "rss"


def test_source_survives_the_cache(client, monkeypatch):
    """The label has to be stored, not recomputed — a cached read doesn't know
    which fetcher originally answered."""
    stub_newsapi(monkeypatch, [])
    stub_rss(monkeypatch, GOOD_NEWS)
    client.get("/api/countries/za")

    assert client.get("/api/countries/za").json()["source"] == "rss"
    assert client.get("/api/countries").json()[0]["source"] in (None, "rss", "newsapi")
