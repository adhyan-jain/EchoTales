"""Property tests for the fuzzy interval algebra.

The three-valued containment result is the load-bearing piece: a resolver that
cannot answer PLAUSIBLE is forced to fabricate precision the text never
provided.
"""

from __future__ import annotations

import math

import pytest
from echotales.core.interval import NEG_INF, POS_INF, Certainty, FuzzyInterval
from hypothesis import given
from hypothesis import strategies as st

finite = st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)


@st.composite
def intervals(draw: st.DrawFn) -> FuzzyInterval:
    """Generate a well-formed interval: from_lb <= from_ub, to_lb <= to_ub, to_ub >= from_lb."""
    from_lb = draw(finite)
    from_ub = draw(st.floats(min_value=from_lb, max_value=from_lb + 500, allow_nan=False))
    to_lb = draw(st.floats(min_value=from_lb, max_value=from_lb + 1000, allow_nan=False))
    to_ub = draw(st.floats(min_value=to_lb, max_value=to_lb + 500, allow_nan=False))
    return FuzzyInterval(from_lb=from_lb, from_ub=from_ub, to_lb=to_lb, to_ub=to_ub)


class TestConstruction:
    def test_rejects_inverted_start_bounds(self) -> None:
        with pytest.raises(ValueError, match="from_lb"):
            FuzzyInterval(from_lb=10, from_ub=5, to_lb=20, to_ub=20)

    def test_rejects_inverted_end_bounds(self) -> None:
        with pytest.raises(ValueError, match="to_lb"):
            FuzzyInterval(from_lb=0, from_ub=0, to_lb=20, to_ub=10)

    def test_rejects_interval_that_can_never_be_nonempty(self) -> None:
        with pytest.raises(ValueError, match="never be non-empty"):
            FuzzyInterval(from_lb=100, from_ub=100, to_lb=5, to_ub=50)

    def test_point_known_reports_both_endpoints_known(self) -> None:
        iv = FuzzyInterval.point_known(10, 20)
        assert iv.is_start_known
        assert iv.is_end_known
        assert not iv.is_open

    def test_open_ended_has_no_attested_end(self) -> None:
        iv = FuzzyInterval.open_ended(10)
        assert iv.is_start_known
        assert iv.is_open
        assert iv.to_ub == POS_INF

    def test_since_before_allows_unbounded_past_start(self) -> None:
        """The reveal case: attested at ch 200, true since before the story began."""
        iv = FuzzyInterval.since_before(200)
        assert iv.from_lb == NEG_INF
        assert iv.contains(3).is_possible
        assert iv.contains(500).is_possible


class TestContainment:
    def test_certain_inside_narrow_extent(self) -> None:
        iv = FuzzyInterval(from_lb=0, from_ub=10, to_lb=90, to_ub=100)
        assert iv.contains(50) is Certainty.CERTAIN

    def test_plausible_in_the_ambiguous_start_band(self) -> None:
        iv = FuzzyInterval(from_lb=0, from_ub=10, to_lb=90, to_ub=100)
        assert iv.contains(5) is Certainty.PLAUSIBLE

    def test_plausible_in_the_ambiguous_end_band(self) -> None:
        iv = FuzzyInterval(from_lb=0, from_ub=10, to_lb=90, to_ub=100)
        assert iv.contains(95) is Certainty.PLAUSIBLE

    def test_excluded_before_and_after_widest_extent(self) -> None:
        iv = FuzzyInterval(from_lb=0, from_ub=10, to_lb=90, to_ub=100)
        assert iv.contains(-1) is Certainty.EXCLUDED
        assert iv.contains(100) is Certainty.EXCLUDED

    def test_open_interval_decays_to_plausible_past_last_evidence(self) -> None:
        """Absence of an attested end is not evidence the fact still holds.

        A sect master attested at chapter 10 and never mentioned again is only
        PLAUSIBLY sect master at chapter 10,000 -- in this genre the title has
        very likely changed hands. Reporting CERTAIN here would be exactly the
        fabricated precision the fuzzy model exists to prevent.
        """
        iv = FuzzyInterval.open_ended(10)
        assert iv.contains(10_000) is Certainty.PLAUSIBLE

    def test_open_interval_is_certain_up_to_last_evidence(self) -> None:
        iv = FuzzyInterval.open_ended(10, last_evidence=500)
        assert iv.contains(400) is Certainty.CERTAIN
        assert iv.contains(600) is Certainty.PLAUSIBLE

    def test_reattestation_grows_the_certain_zone(self) -> None:
        iv = FuzzyInterval.open_ended(10)
        assert iv.contains(300) is Certainty.PLAUSIBLE
        assert iv.with_evidence_through(500).contains(300) is Certainty.CERTAIN

    def test_evidence_never_moves_backwards(self) -> None:
        iv = FuzzyInterval.open_ended(10, last_evidence=500)
        assert iv.with_evidence_through(100) == iv

    def test_unbounded_contains_everything(self) -> None:
        iv = FuzzyInterval.unbounded()
        for pos in (-1e6, 0, 1e6):
            assert iv.contains(pos) is Certainty.CERTAIN

    @given(intervals(), finite)
    def test_containment_is_total(self, iv: FuzzyInterval, pos: float) -> None:
        assert iv.contains(pos) in set(Certainty)

    @given(intervals(), finite)
    def test_certain_implies_within_widest_extent(self, iv: FuzzyInterval, pos: float) -> None:
        if iv.contains(pos) is Certainty.CERTAIN:
            assert iv.from_lb <= pos < iv.to_ub

    @given(intervals(), finite)
    def test_widening_bounds_never_strengthens_certainty(
        self, iv: FuzzyInterval, pos: float
    ) -> None:
        """More uncertainty about endpoints must not produce more confidence."""
        rank = {Certainty.EXCLUDED: 0, Certainty.PLAUSIBLE: 1, Certainty.CERTAIN: 2}
        wider = FuzzyInterval(
            from_lb=iv.from_lb - 5, from_ub=iv.from_ub, to_lb=iv.to_lb, to_ub=iv.to_ub + 5
        )
        if rank[iv.contains(pos)] == 2:
            assert rank[wider.contains(pos)] <= 2


class TestOverlap:
    def test_disjoint_intervals_are_excluded(self) -> None:
        a = FuzzyInterval.point_known(0, 10)
        b = FuzzyInterval.point_known(20, 30)
        assert a.overlaps(b) is Certainty.EXCLUDED

    def test_clearly_nested_intervals_certainly_overlap(self) -> None:
        a = FuzzyInterval.point_known(0, 100)
        b = FuzzyInterval.point_known(40, 60)
        assert a.overlaps(b) is Certainty.CERTAIN

    def test_touching_bounds_are_only_plausible(self) -> None:
        a = FuzzyInterval(from_lb=0, from_ub=0, to_lb=10, to_ub=20)
        b = FuzzyInterval(from_lb=15, from_ub=25, to_lb=30, to_ub=30)
        assert a.overlaps(b) is Certainty.PLAUSIBLE

    @given(intervals(), intervals())
    def test_overlap_is_symmetric(self, a: FuzzyInterval, b: FuzzyInterval) -> None:
        assert a.overlaps(b) == b.overlaps(a)

    def test_open_bindings_only_plausibly_overlap_without_shared_evidence(self) -> None:
        """The clone / sustained-disguise case, before corroboration.

        Two personas each attested once say nothing definite about whether they
        were active at the same moment, so the co-presence signal must stay
        soft rather than hard-splitting the entities.
        """
        a = FuzzyInterval.open_ended(10)
        b = FuzzyInterval.open_ended(50)
        assert a.overlaps(b) is Certainty.PLAUSIBLE

    def test_open_bindings_certainly_overlap_once_evidence_spans_both(self) -> None:
        """Once both personas are attested across a shared window, concurrency is certain."""
        a = FuzzyInterval.open_ended(10, last_evidence=100)
        b = FuzzyInterval.open_ended(50, last_evidence=100)
        assert a.overlaps(b) is Certainty.CERTAIN


class TestCloseInterval:
    def test_with_end_closes_an_open_interval(self) -> None:
        iv = FuzzyInterval.open_ended(10)
        closed = iv.with_end(80)
        assert not closed.is_open
        assert closed.contains(90) is Certainty.EXCLUDED
        assert closed.contains(50) is Certainty.CERTAIN

    def test_with_end_preserves_start_bounds(self) -> None:
        iv = FuzzyInterval(from_lb=0, from_ub=10, to_lb=10, to_ub=POS_INF)
        closed = iv.with_end(80, 90)
        assert (closed.from_lb, closed.from_ub) == (0, 10)
        assert (closed.to_lb, closed.to_ub) == (80, 90)

    def test_fuzzy_end_creates_a_plausible_band(self) -> None:
        """A title transfer with an unstated handover date."""
        iv = FuzzyInterval.point_known(0, 0).with_end(80, 120)
        assert iv.contains(70) is Certainty.CERTAIN
        assert iv.contains(100) is Certainty.PLAUSIBLE
        assert iv.contains(130) is Certainty.EXCLUDED


class TestCertaintyConjunction:
    def test_excluded_dominates(self) -> None:
        assert Certainty.CERTAIN & Certainty.EXCLUDED is Certainty.EXCLUDED
        assert Certainty.PLAUSIBLE & Certainty.EXCLUDED is Certainty.EXCLUDED

    def test_plausible_weakens_certain(self) -> None:
        assert Certainty.CERTAIN & Certainty.PLAUSIBLE is Certainty.PLAUSIBLE

    def test_certain_is_the_identity(self) -> None:
        for c in Certainty:
            assert Certainty.CERTAIN & c is c

    @given(st.sampled_from(list(Certainty)), st.sampled_from(list(Certainty)))
    def test_conjunction_is_commutative(self, a: Certainty, b: Certainty) -> None:
        assert (a & b) == (b & a)

    def test_is_possible_excludes_only_excluded(self) -> None:
        assert Certainty.CERTAIN.is_possible
        assert Certainty.PLAUSIBLE.is_possible
        assert not Certainty.EXCLUDED.is_possible


def test_repr_renders_infinities_readably() -> None:
    assert "+inf" in str(FuzzyInterval.open_ended(10))
    assert "-inf" in str(FuzzyInterval.since_before(200))


def test_infinite_bounds_survive_a_round_trip() -> None:
    iv = FuzzyInterval.open_ended(10)
    again = FuzzyInterval.model_validate(iv.model_dump())
    assert math.isinf(again.to_ub)
    assert again == iv
