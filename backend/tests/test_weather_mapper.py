"""Tests for the score -> condition mapping.

This is pure logic over a bounded input range, so it gets tested exhaustively
rather than representatively. Boundary cases get their own tests because "which
side does exactly 0.15 fall on" is the question most likely to be broken by a
well-meaning later edit.
"""

import math

import pytest

from app.mapping.weather_mapper import (
    OVERCAST_MIN,
    PARTLY_CLOUDY_MIN,
    RAINY_MIN,
    SUNNY_MIN,
    condition_for_score,
    intensity_for_score,
)
from app.models import WeatherCondition


@pytest.mark.parametrize(
    "score,expected",
    [
        (1.0, WeatherCondition.SUNNY),
        (0.82, WeatherCondition.SUNNY),
        (0.5, WeatherCondition.SUNNY),
        (0.49, WeatherCondition.PARTLY_CLOUDY),
        (0.3, WeatherCondition.PARTLY_CLOUDY),
        (0.15, WeatherCondition.PARTLY_CLOUDY),
        (0.14, WeatherCondition.OVERCAST),
        (0.0, WeatherCondition.OVERCAST),
        (-0.15, WeatherCondition.OVERCAST),
        (-0.16, WeatherCondition.RAINY),
        (-0.4, WeatherCondition.RAINY),
        (-0.5, WeatherCondition.RAINY),
        (-0.51, WeatherCondition.THUNDERSTORM),
        (-1.0, WeatherCondition.THUNDERSTORM),
    ],
)
def test_maps_score_to_expected_condition(score, expected):
    assert condition_for_score(score) == expected


@pytest.mark.parametrize(
    "boundary,expected",
    [
        (SUNNY_MIN, WeatherCondition.SUNNY),
        (PARTLY_CLOUDY_MIN, WeatherCondition.PARTLY_CLOUDY),
        (OVERCAST_MIN, WeatherCondition.OVERCAST),
        (RAINY_MIN, WeatherCondition.RAINY),
    ],
)
def test_boundaries_resolve_to_the_brighter_band(boundary, expected):
    """A score sitting exactly on a threshold belongs to the band above it."""
    assert condition_for_score(boundary) == expected


@pytest.mark.parametrize(
    "boundary,expected",
    [
        (SUNNY_MIN, WeatherCondition.PARTLY_CLOUDY),
        (PARTLY_CLOUDY_MIN, WeatherCondition.OVERCAST),
        (OVERCAST_MIN, WeatherCondition.RAINY),
        (RAINY_MIN, WeatherCondition.THUNDERSTORM),
    ],
)
def test_just_below_a_boundary_drops_one_band(boundary, expected):
    assert condition_for_score(boundary - 0.0001) == expected


def test_every_score_in_range_maps_to_something():
    """Walk the whole domain in small steps — no gaps, no exceptions."""
    for step in range(-1000, 1001):
        assert condition_for_score(step / 1000) in WeatherCondition


def test_no_valid_score_ever_maps_to_no_data():
    """NO_DATA means "we couldn't reach the source", never "the news was dull"."""
    for step in range(-1000, 1001):
        assert condition_for_score(step / 1000) is not WeatherCondition.NO_DATA


def test_bands_are_monotonic():
    """Brighter scores never produce darker weather."""
    severity = [
        WeatherCondition.THUNDERSTORM,
        WeatherCondition.RAINY,
        WeatherCondition.OVERCAST,
        WeatherCondition.PARTLY_CLOUDY,
        WeatherCondition.SUNNY,
    ]
    ranks = [severity.index(condition_for_score(s / 100)) for s in range(-100, 101)]
    assert ranks == sorted(ranks)


@pytest.mark.parametrize("score", [1.5, -1.5, 2.0, -100.0])
def test_rejects_scores_outside_the_valid_range(score):
    with pytest.raises(ValueError, match="outside the valid range"):
        condition_for_score(score)


def test_tolerates_floating_point_overshoot():
    """Averaging floats can land a hair past 1.0; that shouldn't be an error."""
    assert condition_for_score(1.0000000000000002) is WeatherCondition.SUNNY


def test_rejects_nan():
    with pytest.raises(ValueError, match="NaN"):
        condition_for_score(float("nan"))


@pytest.mark.parametrize(
    "score,expected",
    [(0.0, 0.0), (-0.5, 0.5), (0.75, 0.75), (-1.0, 1.0)],
)
def test_intensity_is_distance_from_neutral(score, expected):
    assert math.isclose(intensity_for_score(score), expected)
