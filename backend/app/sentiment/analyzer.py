"""Scores headlines and reduces them to one number per region.

Two engines behind one interface. VADER is the default because it is rule-based,
loads instantly, needs no model download, and was built for short informal text —
which is what a headline is. The transformer engine exists to show the tradeoff,
not because it is obviously better here (see docs/methodology.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app import config
from app.fetchers.base import RawHeadline
from app.mapping.weather_mapper import condition_for_score
from app.models import Confidence, Headline, WeatherCondition

# Below this many headlines the mean is dominated by whichever story happened to
# be loud that hour. We still serve the score, but flagged, and the UI dims it.
MIN_HEADLINES_FOR_CONFIDENCE = 15

# Google News appends " - Publisher" to titles and NewsAPI often does the same.
# Left in place it gets scored as part of the sentence, so "Reuters" and "The Sun"
# quietly become part of the mood of the region.
#
# Matching anything after the last dash is too greedy — it swallows real clauses
# like "rent rises - and no end in sight". Publisher names look different from
# sentence fragments: at most four tokens, each either capitalised or one of a
# handful of lowercase connectives. That shape is what's matched here. It still
# misfires on titles ending in a short proper noun ("... - Mayor Delighted"),
# which is an acceptable loss for a token or two of scored text.
_PUBLISHER_TOKEN = r"(?:[A-Z0-9][\w.&'’-]*|of|the|de|and|en|für|und)"
_TRAILING_SOURCE = re.compile(
    rf"\s+[-–—|]\s+{_PUBLISHER_TOKEN}(?:\s+{_PUBLISHER_TOKEN}){{0,3}}\s*$"
)


class SentimentEngine(Protocol):
    """Anything that can turn a string into a compound score in [-1, 1]."""

    name: str

    def score(self, text: str) -> float: ...


class VaderEngine:
    """Rule-based scoring. Fast enough to run inline on every request."""

    name = "vader"

    def __init__(self) -> None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        self._analyzer = SentimentIntensityAnalyzer()

    def score(self, text: str) -> float:
        return self._analyzer.polarity_scores(text)["compound"]


class TransformerEngine:
    """DistilBERT fine-tuned on SST-2, behind HIGH_ACCURACY_MODE.

    The model is binary, so its output is folded into the same [-1, 1] axis by
    signing the confidence. Worth knowing: it is far more polarised than VADER —
    it rarely reports anything between -0.9 and 0.9 — so the thresholds in
    weather_mapper, which were tuned against VADER, produce a stormier and
    sunnier map in this mode. Documented rather than fudged.
    """

    name = "distilbert-sst2"
    MODEL = "distilbert-base-uncased-finetuned-sst-2-english"

    def __init__(self) -> None:
        # Imported here, not at module top, so that a deployment running the
        # default VADER path never pays the transformers import cost.
        from transformers import pipeline

        self._pipe = pipeline("sentiment-analysis", model=self.MODEL, truncation=True)

    def score(self, text: str) -> float:
        result = self._pipe(text)[0]
        signed = result["score"] if result["label"] == "POSITIVE" else -result["score"]
        return float(signed)


@lru_cache(maxsize=1)
def get_engine() -> SentimentEngine:
    """The process-wide engine. Cached because both engines are costly to build
    and neither holds per-request state."""
    return TransformerEngine() if config.HIGH_ACCURACY_MODE else VaderEngine()


@dataclass(frozen=True)
class RegionSentiment:
    """The complete verdict for one region."""

    score: float
    condition: WeatherCondition
    confidence: Confidence
    headlines: list[Headline]


def clean_headline(title: str) -> str:
    """Strip the publisher suffix and collapse whitespace before scoring."""
    return _TRAILING_SOURCE.sub("", title).strip()


def analyse(raw: list[RawHeadline]) -> RegionSentiment:
    """Score every headline and average them into one regional reading.

    A flat mean, not a weighted one: weighting by recency or outlet reach would
    need data the free tiers don't reliably give, and inventing weights would
    make the number look more authoritative than it is.
    """
    if not raw:
        return RegionSentiment(
            score=0.0,
            condition=WeatherCondition.NO_DATA,
            confidence=Confidence.NONE,
            headlines=[],
        )

    engine = get_engine()
    scored = [
        Headline(
            title=item.title,
            source=item.source,
            url=item.url,
            score=round(engine.score(clean_headline(item.title)), 4),
        )
        for item in raw
    ]

    mean = sum(h.score for h in scored) / len(scored)
    confidence = (
        Confidence.HIGH if len(scored) >= MIN_HEADLINES_FOR_CONFIDENCE else Confidence.LOW
    )

    return RegionSentiment(
        score=round(mean, 4),
        condition=condition_for_score(mean),
        confidence=confidence,
        headlines=scored,
    )


def most_influential(headlines: list[Headline], limit: int = 5) -> list[Headline]:
    """The headlines pulling the average furthest from neutral.

    "Top headlines driving the score" means the ones doing the most work, not the
    most positive ones — a region can be rainy because of one furious story among
    twenty bland ones, and that story is what the panel should surface.
    """
    return sorted(headlines, key=lambda h: abs(h.score), reverse=True)[:limit]
