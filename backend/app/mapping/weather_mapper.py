"""Turns a sentiment score into a weather condition.

Pure functions only — no I/O, no clock, no config. That is what makes this the
one module in the backend that can be tested exhaustively, and it is why the
thresholds live here rather than being sprinkled through the pipeline.

The reasoning behind the specific cut-points is in docs/methodology.md.
"""

from __future__ import annotations

import math

from app.models import WeatherCondition

# Lower bound of each band, walked from brightest to darkest. Named rather than
# inlined so that retuning the scale is a one-line change here and the tests
# read as prose ("just below SUNNY_MIN is partly cloudy").
SUNNY_MIN = 0.5
PARTLY_CLOUDY_MIN = 0.15
OVERCAST_MIN = -0.15
RAINY_MIN = -0.5

# VADER compound scores are bounded to [-1, 1], and so is any mean of them.
# A value outside that range means something upstream is broken, so we reject it
# instead of quietly mapping it — but we allow a hair of slack, because summing
# and dividing a few dozen floats can land on 1.0000000000000002.
SCORE_EPSILON = 1e-6


def condition_for_score(score: float) -> WeatherCondition:
    """Map a mean sentiment score in [-1, 1] to the weather it looks like.

    Bands are lower-inclusive, upper-exclusive, so a score sitting exactly on a
    boundary always resolves to the brighter side. Arbitrary, but consistent —
    and the alternative leaves 0.15 undefined.
    """
    if math.isnan(score):
        raise ValueError("Sentiment score is NaN; the caller averaged an empty set")
    if not -1 - SCORE_EPSILON <= score <= 1 + SCORE_EPSILON:
        raise ValueError(f"Sentiment score {score} is outside the valid range [-1, 1]")

    if score >= SUNNY_MIN:
        return WeatherCondition.SUNNY
    if score >= PARTLY_CLOUDY_MIN:
        return WeatherCondition.PARTLY_CLOUDY
    if score >= OVERCAST_MIN:
        return WeatherCondition.OVERCAST
    if score >= RAINY_MIN:
        return WeatherCondition.RAINY
    return WeatherCondition.THUNDERSTORM


def intensity_for_score(score: float) -> float:
    """How hard the weather is coming down, as 0..1.

    Feeds marker glow on the map: a -0.9 thunderstorm should read as visibly
    angrier than a -0.55 one, which the five discrete conditions alone can't
    express. Distance from neutral, normalised — mild scores stay near zero.
    """
    return min(abs(score), 1.0)
