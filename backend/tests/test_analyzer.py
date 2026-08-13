"""Tests for the aggregation rules around the sentiment engine.

The engine itself (VADER) is a third-party library and isn't retested here. What
is tested is everything we put around it: cleaning, averaging, the low-confidence
threshold, dedupe, and which headlines get surfaced as "driving the score".
"""

import pytest

from app.fetchers.base import RawHeadline
from app.models import Confidence, Headline, WeatherCondition
from app.pipeline import confidence_for, dedupe
from app.sentiment.analyzer import (
    MIN_HEADLINES_FOR_CONFIDENCE,
    analyse,
    clean_headline,
    most_influential,
)


def raw(title: str, source: str = "Wire") -> RawHeadline:
    return RawHeadline(title=title, source=source)


# --- cleaning ----------------------------------------------------------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Bridge reopens after repairs - Reuters", "Bridge reopens after repairs"),
        ("Markets rally on new data | Bloomberg", "Markets rally on new data"),
        ("Storm warning issued – BBC News", "Storm warning issued"),
        ("Council approves budget", "Council approves budget"),
    ],
)
def test_strips_the_publisher_suffix(title, expected):
    """Otherwise the outlet's name gets scored as part of the sentence."""
    assert clean_headline(title) == expected


def test_leaves_hyphenated_headlines_alone():
    """A mid-sentence dash isn't a publisher suffix and must survive."""
    assert clean_headline("Anger over rent rises - and no end in sight to the shortage") == (
        "Anger over rent rises - and no end in sight to the shortage"
    )


# --- aggregation -------------------------------------------------------------


def test_empty_input_reports_no_data_rather_than_neutral():
    """Zero headlines is not a calm day — the distinction drives the grey pin."""
    result = analyse([])
    assert result.condition is WeatherCondition.NO_DATA
    assert result.confidence is Confidence.NONE
    assert result.score == 0.0


def test_positive_headlines_produce_bright_weather():
    result = analyse([raw("Wonderful news: city wins award, residents delighted")] * 1)
    assert result.score > 0
    assert result.condition in {WeatherCondition.SUNNY, WeatherCondition.PARTLY_CLOUDY}


def test_negative_headlines_produce_dark_weather():
    result = analyse([raw("Deadly attack kills dozens in horrific tragedy")])
    assert result.score < 0
    assert result.condition in {WeatherCondition.RAINY, WeatherCondition.THUNDERSTORM}


def test_score_is_the_mean_of_its_headlines():
    result = analyse(
        [raw("Terrible disaster kills many"), raw("Wonderful celebration delights crowds")]
    )
    assert result.score == pytest.approx(
        sum(h.score for h in result.headlines) / len(result.headlines), abs=1e-4
    )


def test_score_stays_in_range_for_extreme_input():
    result = analyse([raw("Horrific brutal deadly catastrophic tragedy")] * 3)
    assert -1.0 <= result.score <= 1.0


def test_every_input_headline_comes_back_scored():
    titles = ["One good thing happened", "One bad thing happened", "A thing happened"]
    result = analyse([raw(t) for t in titles])
    assert [h.title for h in result.headlines] == titles


# --- confidence --------------------------------------------------------------


def test_thin_coverage_is_flagged_low_confidence():
    result = analyse([raw(f"Something happened number {i}") for i in range(5)])
    assert result.confidence is Confidence.LOW


def test_enough_coverage_is_high_confidence():
    result = analyse(
        [raw(f"Something happened number {i}") for i in range(MIN_HEADLINES_FOR_CONFIDENCE)]
    )
    assert result.confidence is Confidence.HIGH


@pytest.mark.parametrize(
    "condition,count,expected",
    [
        (WeatherCondition.NO_DATA, 0, Confidence.NONE),
        (WeatherCondition.NO_DATA, 40, Confidence.NONE),
        (WeatherCondition.SUNNY, MIN_HEADLINES_FOR_CONFIDENCE - 1, Confidence.LOW),
        (WeatherCondition.SUNNY, MIN_HEADLINES_FOR_CONFIDENCE, Confidence.HIGH),
    ],
)
def test_confidence_rules(condition, count, expected):
    assert confidence_for(condition, count) is expected


# --- dedupe and ranking ------------------------------------------------------


def test_dedupe_drops_syndicated_repeats():
    """One wire story reprinted three times should get one vote, not three."""
    items = [
        raw("Rail strike enters second week", "The Guardian"),
        raw("Rail strike enters second week!", "Metro"),
        raw("rail strike enters second week", "Sky News"),
        raw("Unrelated story about badgers", "Local Post"),
    ]
    assert len(dedupe(items)) == 2


def test_dedupe_keeps_the_first_occurrence():
    items = [raw("Same story", "First"), raw("Same story", "Second")]
    assert dedupe(items)[0].source == "First"


def test_dedupe_preserves_order():
    items = [raw("A"), raw("B"), raw("A"), raw("C")]
    assert [h.title for h in dedupe(items)] == ["A", "B", "C"]


def test_most_influential_surfaces_the_strongest_signal_either_way():
    """The story driving a region's weather can be the angriest one, not the
    most positive — ranking is by distance from neutral."""
    headlines = [
        Headline(title="mild", source="a", score=0.05),
        Headline(title="furious", source="b", score=-0.88),
        Headline(title="cheerful", source="c", score=0.42),
    ]
    assert [h.title for h in most_influential(headlines, limit=2)] == ["furious", "cheerful"]


def test_most_influential_caps_the_list():
    headlines = [Headline(title=str(i), source="a", score=i / 10) for i in range(10)]
    assert len(most_influential(headlines)) == 5
