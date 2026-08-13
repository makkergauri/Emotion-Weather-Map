"""Tests for RSS parsing, run against a saved feed rather than the network.

Google News is the least controlled input in the system: entries arrive with and
without a <source> element, titles come wrapped in CDATA, and empty items show
up. All of that is captured in fixtures/sample_feed.xml.
"""

from pathlib import Path

import pytest

from app.fetchers.base import FetchError
from app.fetchers.rss_fetcher import build_feed_url, parse_feed

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"


@pytest.fixture
def sample_feed() -> bytes:
    return FIXTURE.read_bytes()


def test_parses_every_usable_entry(sample_feed):
    """Five items in, four out — the one with an empty title is dropped."""
    headlines = parse_feed(sample_feed, "Bhopal")
    assert len(headlines) == 4


def test_keeps_the_headline_text_intact(sample_feed):
    headlines = parse_feed(sample_feed, "Bhopal")
    assert headlines[0].title.startswith("Bhopal metro trial run draws cheering crowds")


def test_reads_the_publisher_from_the_source_element(sample_feed):
    headlines = parse_feed(sample_feed, "Bhopal")
    assert headlines[0].source == "The Times of India"
    assert headlines[1].source == "Hindustan Times"


def test_falls_back_to_the_title_suffix_when_source_is_missing(sample_feed):
    """Third item has no <source>, so the publisher comes off the title."""
    headlines = parse_feed(sample_feed, "Bhopal")
    library_story = next(h for h in headlines if "library" in h.title)
    assert library_story.source == "Free Press Journal"


def test_handles_cdata_and_entities(sample_feed):
    headlines = parse_feed(sample_feed, "Bhopal")
    protest = next(h for h in headlines if "compensation" in h.title)
    assert "&" in protest.title
    # No <source> and no " - Publisher" suffix either, so it lands on the default.
    assert protest.source == "The Hindu"


def test_keeps_the_link(sample_feed):
    headlines = parse_feed(sample_feed, "Bhopal")
    assert all(h.url and h.url.startswith("https://news.google.com") for h in headlines)


def test_never_carries_article_bodies(sample_feed):
    """The no-scraping constraint, enforced by the shape of RawHeadline itself."""
    headlines = parse_feed(sample_feed, "Bhopal")
    assert all(set(vars(h)) == {"title", "source", "url"} for h in headlines)


def test_empty_but_well_formed_feed_yields_nothing():
    """A city with no coverage is a legitimate outcome, not a failure."""
    empty = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
    assert parse_feed(empty, "Nowhere") == []


def test_unparseable_response_raises_fetch_error():
    """An HTML error page where XML was expected — the common real-world failure."""
    with pytest.raises(FetchError, match="could not be parsed"):
        parse_feed(b"<html><body>429 Too Many Requests</body></html>", "Delhi")


def test_respects_the_entry_cap(monkeypatch, sample_feed):
    monkeypatch.setattr("app.fetchers.rss_fetcher.MAX_ENTRIES", 2)
    assert len(parse_feed(sample_feed, "Bhopal")) == 2


@pytest.mark.parametrize(
    "query,expected_fragment",
    [
        ("Bhopal", "q=Bhopal"),
        ("New York City", "q=New+York+City"),
        ("Sao Paulo Brazil", "q=Sao+Paulo+Brazil"),
    ],
)
def test_builds_an_encoded_query_url(query, expected_fragment):
    url = build_feed_url(query)
    assert expected_fragment in url
    assert url.endswith("&hl=en")
