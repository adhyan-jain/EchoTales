"""Fuzzy temporal intervals (plans.md Section 2.5).

Web novels almost never state when a binding *stopped* holding. A new sect
master is introduced; the text does not say the previous one ceased to be sect
master, and often never says it at all. Modelling an interval as a crisp
``[from, to]`` therefore forces a guess on nearly every fact.

Instead each endpoint becomes a bounded pair, and containment queries return
three values rather than two:

    CERTAIN   -- holds under every consistent reading of the endpoints
    PLAUSIBLE -- holds under some but not all readings
    EXCLUDED  -- holds under no reading

A resolver that cannot say "plausible" is forced to fabricate precision, which
is exactly the failure mode this project exists to avoid.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

# Story positions are floats so an unknown upper bound can be +inf and so that
# a segment can interpolate positions between two attested points.
StoryPos = float

NEG_INF: StoryPos = -math.inf
POS_INF: StoryPos = math.inf


class Certainty(StrEnum):
    CERTAIN = "CERTAIN"
    PLAUSIBLE = "PLAUSIBLE"
    EXCLUDED = "EXCLUDED"

    @property
    def is_possible(self) -> bool:
        """True when the fact may hold -- i.e. anything but EXCLUDED."""
        return self is not Certainty.EXCLUDED

    def __and__(self, other: Certainty) -> Certainty:
        """Conjunction: the weaker of two certainties.

        EXCLUDED dominates, then PLAUSIBLE. Used to combine independent
        constraints, e.g. a story-time check AND a knowledge-time check.
        """
        if self is Certainty.EXCLUDED or other is Certainty.EXCLUDED:
            return Certainty.EXCLUDED
        if self is Certainty.PLAUSIBLE or other is Certainty.PLAUSIBLE:
            return Certainty.PLAUSIBLE
        return Certainty.CERTAIN


class FuzzyInterval(BaseModel):
    """A half-open story-time interval with bounded, possibly-unknown endpoints.

    The interval starts somewhere in ``[from_lb, from_ub]`` and ends somewhere
    in ``[to_lb, to_ub]``.

    - Point-known start: ``from_lb == from_ub``
    - Still open at last evidence: ``to_lb = <last evidence>, to_ub = +inf``
    """

    model_config = ConfigDict(frozen=True)

    from_lb: StoryPos
    from_ub: StoryPos
    to_lb: StoryPos
    to_ub: StoryPos

    @model_validator(mode="after")
    def _check_ordering(self) -> Self:
        if self.from_lb > self.from_ub:
            raise ValueError(f"from_lb {self.from_lb} exceeds from_ub {self.from_ub}")
        if self.to_lb > self.to_ub:
            raise ValueError(f"to_lb {self.to_lb} exceeds to_ub {self.to_ub}")
        # The earliest possible end may not precede the earliest possible start:
        # that would describe an interval that can never be non-empty.
        if self.to_ub < self.from_lb:
            raise ValueError(
                f"interval can never be non-empty: to_ub {self.to_ub} < from_lb {self.from_lb}"
            )
        return self

    # ---- constructors -------------------------------------------------

    @classmethod
    def point_known(cls, start: StoryPos, end: StoryPos) -> FuzzyInterval:
        """Both endpoints exactly attested."""
        return cls(from_lb=start, from_ub=start, to_lb=end, to_ub=end)

    @classmethod
    def open_ended(
        cls,
        start: StoryPos,
        *,
        start_ub: StoryPos | None = None,
        last_evidence: StoryPos | None = None,
    ) -> FuzzyInterval:
        """Known (or bounded) start, no attested end -- ``(last_evidence, +inf)``.

        ``last_evidence`` is the latest position at which the fact was still
        observed to hold, and it becomes ``to_lb``: the earliest point at which
        it could have stopped. Everything up to there is CERTAIN; beyond it the
        fact is only PLAUSIBLE, because nothing in the text speaks to it.

        That decay is deliberate. A sect master attested in chapter 20 and
        never mentioned again should not be reported with confidence as sect
        master in chapter 400 -- in this genre the title has very likely
        changed hands. Reaffirming the fact advances ``last_evidence`` and
        grows the certain zone, so confidence tracks evidence instead of
        assumption.

        Defaults to the start itself when no later sighting is known.
        """
        ub = start if start_ub is None else start_ub
        evidence = ub if last_evidence is None else max(ub, last_evidence)
        return cls(from_lb=start, from_ub=ub, to_lb=evidence, to_ub=POS_INF)

    def with_evidence_through(self, position: StoryPos) -> FuzzyInterval:
        """Extend the certain zone: the fact was observed still holding at ``position``.

        Called whenever a binding is re-attested, which is how an open interval
        earns confidence over the course of a novel.
        """
        if position <= self.to_lb:
            return self
        return FuzzyInterval(
            from_lb=self.from_lb,
            from_ub=self.from_ub,
            to_lb=position,
            to_ub=self.to_ub,
        )

    @classmethod
    def since_before(cls, first_evidence: StoryPos) -> FuzzyInterval:
        """Attested at a position, with an unknown earlier true start.

        This is the shape a reveal produces: chapter 200 discloses that Li Wei
        has been the Frost Emperor since before the story began. Modelling the
        start as unbounded-below is what lets a late reveal override the
        first-attestation prior (plans.md Section 4.4) instead of contradicting it.
        """
        return cls(from_lb=NEG_INF, from_ub=first_evidence, to_lb=first_evidence, to_ub=POS_INF)

    @classmethod
    def unbounded(cls) -> FuzzyInterval:
        """Holds at all times; used for facts with no temporal claim at all."""
        return cls(from_lb=NEG_INF, from_ub=NEG_INF, to_lb=POS_INF, to_ub=POS_INF)

    # ---- predicates ---------------------------------------------------

    @property
    def is_start_known(self) -> bool:
        return self.from_lb == self.from_ub

    @property
    def is_end_known(self) -> bool:
        return self.to_lb == self.to_ub

    @property
    def is_open(self) -> bool:
        """No attested end."""
        return self.to_ub == POS_INF

    def contains(self, pos: StoryPos) -> Certainty:
        """Does this interval cover ``pos``?

        CERTAIN when pos is at-or-after every possible start and strictly
        before every possible end; EXCLUDED when it is outside even the most
        generous reading; PLAUSIBLE in the ambiguous band between.
        """
        # Outside the widest possible extent.
        if pos < self.from_lb or pos >= self.to_ub:
            return Certainty.EXCLUDED
        # Inside the narrowest guaranteed extent.
        if pos >= self.from_ub and pos < self.to_lb:
            return Certainty.CERTAIN
        return Certainty.PLAUSIBLE

    def overlaps(self, other: FuzzyInterval) -> Certainty:
        """Could the two intervals be simultaneously active?

        Concurrency drives the co-presence signal in the resolver: two personas
        active at once is evidence they are distinct bodies, and suppressing
        that penalty for clones/avatars depends on this returning PLAUSIBLE
        rather than a hard yes/no.
        """
        # Disjoint under every reading.
        if self.to_ub <= other.from_lb or other.to_ub <= self.from_lb:
            return Certainty.EXCLUDED
        # Guaranteed to share at least one position.
        if self.from_ub < other.to_lb and other.from_ub < self.to_lb:
            return Certainty.CERTAIN
        return Certainty.PLAUSIBLE

    def with_end(self, end_lb: StoryPos, end_ub: StoryPos | None = None) -> FuzzyInterval:
        """Close an open interval.

        This is the ``close_interval`` operation -- the fact *was* true and
        stopped. It is emphatically not retraction; a retracted fact keeps its
        interval and is excluded by ``retracted_at`` instead. See enums.EventType.
        """
        return FuzzyInterval(
            from_lb=self.from_lb,
            from_ub=self.from_ub,
            to_lb=end_lb,
            to_ub=end_lb if end_ub is None else end_ub,
        )

    def __str__(self) -> str:
        def fmt(lb: StoryPos, ub: StoryPos) -> str:
            if lb == ub:
                return "-inf" if lb == NEG_INF else ("+inf" if lb == POS_INF else f"{lb:g}")
            lo = "-inf" if lb == NEG_INF else f"{lb:g}"
            hi = "+inf" if ub == POS_INF else f"{ub:g}"
            return f"[{lo}..{hi}]"

        return f"({fmt(self.from_lb, self.from_ub)} -> {fmt(self.to_lb, self.to_ub)})"
