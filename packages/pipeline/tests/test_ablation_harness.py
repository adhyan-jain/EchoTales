"""Evidence cache + ablation conditions (COMPLETION_PLAN Track 3 items 13-15).

The docs claimed for months that ablations "cost no additional LLM passes
because they re-score cached evidence vectors" while no such cache existed
(EVOLUTION 4.78). These tests pin the cache's contract and the one property
that makes an ablation of *this* system meaningful at all: the hard
pre-filters, not the five scored weights, are what can actually be switched
off (EVOLUTION 4.77 measured the scorer settling zero of 880 links).
"""

from __future__ import annotations

import pytest
from echotales.core.enums import ResolutionMethod
from echotales.core.models import EvidenceVector
from echotales.core.store import Store
from echotales.pipeline.eval.ablate import (
    CONDITIONS,
    REQUIRES_RERESOLVE,
    run_condition,
)
from echotales.pipeline.eval.evidence_cache import capture_evidence, load_evidence
from echotales.pipeline.resolve.score import (
    NAME_CONTAINMENT_FLOOR,
    PREFILTER_GATES,
    PrefilterVerdict,
    prefilter,
)


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    s = Store(str(tmp_path / "t.db"))
    yield s
    s.close()


class TestDisabledPrefilters:
    def test_disabling_the_gazetteer_gate_lets_the_pair_reach_the_scorer(self) -> None:
        evidence = EvidenceVector(gazetteer_exact_match=1.0)
        assert prefilter(evidence).verdict is PrefilterVerdict.FORCE_LINK
        assert (
            prefilter(
                evidence, disabled_prefilters=frozenset({"gazetteer_exact_match"})
            ).verdict
            is PrefilterVerdict.SCORE
        )

    def test_a_disabled_gate_falls_through_rather_than_erasing_the_evidence(self) -> None:
        """Disabling `gazetteer_exact_match` means "do not short-circuit", not
        "pretend the alias did not match" -- the next gate must still see the
        vector, or the ablation measures the wrong counterfactual."""
        evidence = EvidenceVector(
            gazetteer_exact_match=1.0, name_containment=NAME_CONTAINMENT_FLOOR
        )
        result = prefilter(
            evidence, disabled_prefilters=frozenset({"gazetteer_exact_match"})
        )
        assert result.verdict is PrefilterVerdict.FORCE_LINK
        assert result.method is ResolutionMethod.NAME_CONTAINMENT

    def test_a_blocker_can_be_ablated_too(self) -> None:
        """What the hard negatives buy is a different question from what the
        hard positives buy, and both are worth asking."""
        evidence = EvidenceVector(co_presence_violation=1.0)
        assert prefilter(evidence).verdict is PrefilterVerdict.BLOCK
        assert (
            prefilter(
                evidence, disabled_prefilters=frozenset({"co_presence_violation"})
            ).verdict
            is PrefilterVerdict.SCORE
        )

    def test_disabling_everything_sends_every_pair_to_the_scorer(self) -> None:
        evidence = EvidenceVector(
            declaration_match=1.0, gazetteer_exact_match=1.0, co_presence_violation=1.0
        )
        result = prefilter(evidence, disabled_prefilters=frozenset(PREFILTER_GATES))
        assert result.verdict is PrefilterVerdict.SCORE

    def test_every_condition_names_only_real_gates(self) -> None:
        """A typo in a condition would silently ablate nothing and report a
        difference of zero as a finding."""
        for name, gates in CONDITIONS.items():
            assert set(gates) <= set(PREFILTER_GATES), name


class TestEvidenceCache:
    def test_capture_writes_rows_and_restores_the_patch(self, store) -> None:  # type: ignore[no-untyped-def]
        from echotales.pipeline.resolve import runner as resolve_runner

        before = resolve_runner.score_evidence
        with capture_evidence(store, "ri") as stats:
            assert resolve_runner.score_evidence is not before
            assert stats["captured"] == 0
        assert resolve_runner.score_evidence is before

    def test_the_patch_is_restored_even_when_the_run_dies(self, store) -> None:  # type: ignore[no-untyped-def]
        """A resolve that dies mid-volume must not leave a traced
        `score_evidence` installed for the rest of the process."""
        from echotales.pipeline.resolve import runner as resolve_runner

        before = resolve_runner.score_evidence
        with pytest.raises(RuntimeError), capture_evidence(store, "ri"):
            raise RuntimeError("died at chapter 140")
        assert resolve_runner.score_evidence is before

    def test_rows_round_trip_as_evidence_vectors(self, store) -> None:  # type: ignore[no-untyped-def]
        store.add_scoring_evidence(
            [("ri", "", 1.0, "m1", "Fang Yuan", "ri:e1", "Fang Yuan",
              '{"gazetteer_exact_match": 1.0, "surface_similarity": 0.5}')]
        )
        store.conn.commit()
        loaded = load_evidence(store, "ri")
        assert len(loaded) == 1
        chapter, mention_id, surface, candidate_id, vector = loaded[0]
        assert (chapter, mention_id, surface, candidate_id) == (1.0, "m1", "Fang Yuan", "ri:e1")
        assert vector.gazetteer_exact_match == 1.0
        assert vector.surface_similarity == 0.5

    def test_an_unparseable_row_is_skipped_not_fatal(self, store) -> None:  # type: ignore[no-untyped-def]
        store.add_scoring_evidence(
            [("ri", "", 1.0, "m1", "x", "ri:e1", "x", "{not json"),
             ("ri", "", 2.0, "m2", "y", "ri:e2", "y", '{"surface_similarity": 1.0}')]
        )
        store.conn.commit()
        assert [m for _c, m, *_r in load_evidence(store, "ri")] == ["m2"]

    def test_recapture_replaces_rather_than_doubling(self, store) -> None:  # type: ignore[no-untyped-def]
        """A second capture that appended would make the ablation re-scorer
        read every pair twice as independent observations."""
        store.add_scoring_evidence([("ri", "", 1.0, "m1", "x", "ri:e1", "x", "{}")])
        store.conn.commit()
        assert store.count_scoring_evidence("ri") == 1
        with capture_evidence(store, "ri"):
            pass
        assert store.count_scoring_evidence("ri") == 0

    def test_run_tags_are_independent_captures(self, store) -> None:  # type: ignore[no-untyped-def]
        store.add_scoring_evidence([("ri", "a", 1.0, "m1", "x", "ri:e1", "x", "{}")])
        store.add_scoring_evidence([("ri", "b", 1.0, "m2", "y", "ri:e2", "y", "{}")])
        store.conn.commit()
        with capture_evidence(store, "ri", run_tag="a"):
            pass
        assert store.count_scoring_evidence("ri", "a") == 0
        assert store.count_scoring_evidence("ri", "b") == 1


class TestConditionAccounting:
    def test_every_pair_lands_in_exactly_one_bucket(self) -> None:
        vectors = [
            EvidenceVector(gazetteer_exact_match=1.0),
            EvidenceVector(co_presence_violation=1.0),
            EvidenceVector(surface_similarity=0.4),
        ]
        row = run_condition(vectors, condition="full")
        assert row.pairs == 3
        assert row.force_links + row.blocks + row.scored == row.pairs

    def test_removing_the_gazetteer_moves_pairs_to_the_scorer(self) -> None:
        vectors = [EvidenceVector(gazetteer_exact_match=1.0)] * 5
        full = run_condition(vectors, condition="full")
        ablated = run_condition(vectors, condition="no-gazetteer-compounding")
        assert full.force_links == 5 and full.scored == 0
        assert ablated.force_links == 0 and ablated.scored == 5

    def test_an_unknown_condition_ablates_nothing(self) -> None:
        """Reported honestly as the control rather than silently as a result."""
        vectors = [EvidenceVector(gazetteer_exact_match=1.0)]
        assert run_condition(vectors, condition="typo").force_links == 1

    def test_the_unanswerable_conditions_are_declared(self) -> None:
        """Their absence must be visible, or it reads as 'this axis did not
        matter' rather than 'the cache cannot answer this'."""
        assert set(REQUIRES_RERESOLVE) & {
            "no-alias-typing",
            "no-self-persona-split",
            "no-truth-status",
        }
        assert not set(REQUIRES_RERESOLVE) & set(CONDITIONS)
