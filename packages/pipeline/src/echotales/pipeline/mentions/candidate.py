"""Explicit stage hand-off types for the hybrid mention detector (decisions D69).

Detect -> merge -> route used to be one function passing bare `NerSpan`s, which lost who said what: a span that two
encoders and the gazetteer agreed on looked identical to one a single 0.4-scored vote produced. These types keep
every vote through the stages so the route that accepted a span, and the models that voted for it, can be stored on
the `Mention` and audited later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from echotales.pipeline.ingest.normalize import comparison_key

Route = Literal["accept", "classifier", "reject"]


@dataclass(frozen=True, slots=True)
class Vote:
    """One source's opinion that a span is a name.

    `source` is "gliner", "spacy", "gazetteer" or "seed". Gazetteer and seed votes carry no model; their score is a
    fixed rule-based value (see `hybrid.py`), not a calibrated probability.
    """

    source: str
    label: str
    score: float
    model_id: str | None = None
    model_version: str | None = None


@dataclass(frozen=True, slots=True)
class NameCandidate:
    """A span plus every vote that overlapped it.

    `search_key` is `comparison_key(surface)`, used for lookup only. Normalisation never merges entities: two
    candidates sharing a key are candidates for the same entity, and whether they ARE is decided by resolve's gate
    (non-negotiable 9, precision over recall in local resolution), never here.
    """

    surface: str
    start: int
    end: int
    search_key: str
    votes: tuple[Vote, ...]

    @classmethod
    def build(cls, surface: str, start: int, end: int, votes: tuple[Vote, ...]) -> NameCandidate:
        return cls(surface, start, end, comparison_key(surface), votes)

    @property
    def sources(self) -> frozenset[str]:
        return frozenset(v.source for v in self.votes)

    @property
    def max_score(self) -> float:
        return max((v.score for v in self.votes), default=0.0)


@dataclass(frozen=True, slots=True)
class ClassifiedCandidate:
    """A candidate after routing: its final label, whether it enters the vocabulary, and why."""

    candidate: NameCandidate
    label: str
    accepted: bool
    route: Route
    evidence: str
