"""`by_method` has to say which rung of the ladder settled each link.

Until 2026-09-23 (EVOLUTION 4.77) `resolve/runner.py` stamped
`ResolutionMethod.SCORED` at both `_apply_link` call sites regardless of how
the decision was actually reached, so `ResolveReport.by_method` read ~100%
SCORED on every run by construction. The project's headline "% resolved by
gazetteer vs declaration vs scorer" claim was unmeasurable from its own
output, and the gazetteer-compounding claim rests on exactly that split.
"""

from __future__ import annotations

from echotales.core.enums import Decision, ResolutionMethod
from echotales.core.models import Candidate, EvidenceVector
from echotales.pipeline.resolve.gate import ConformalGate, GateDecision
from echotales.pipeline.resolve.score import (
    NAME_CONTAINMENT_FLOOR,
    PrefilterVerdict,
    prefilter,
)


def _candidate(**evidence: float) -> Candidate:
    return Candidate(
        target_kind="SELF",
        target_id="ri:e1",
        label="Fang Yuan",
        retrieval_score=0.5,
        evidence=EvidenceVector(**evidence),
    )


class TestPrefilterReportsItsMethod:
    def test_declaration(self) -> None:
        result = prefilter(EvidenceVector(declaration_match=1.0))
        assert result.verdict is PrefilterVerdict.FORCE_LINK
        assert result.method is ResolutionMethod.DECLARATION

    def test_gazetteer_exact(self) -> None:
        result = prefilter(EvidenceVector(gazetteer_exact_match=1.0))
        assert result.method is ResolutionMethod.GAZETTEER_EXACT

    def test_name_containment(self) -> None:
        result = prefilter(EvidenceVector(name_containment=NAME_CONTAINMENT_FLOOR))
        assert result.method is ResolutionMethod.NAME_CONTAINMENT

    def test_relational_copresence(self) -> None:
        result = prefilter(EvidenceVector(relationship_deictic_resolution=1.0))
        assert result.method is ResolutionMethod.RELATIONAL_COPRESENCE

    def test_falling_through_to_the_scorer_stays_scored(self) -> None:
        """The default has to be SCORED, not None -- a path that really did
        reach the scorer must not be reported as a pre-filter hit either."""
        result = prefilter(EvidenceVector())
        assert result.verdict is PrefilterVerdict.SCORE
        assert result.method is ResolutionMethod.SCORED

    def test_a_blocker_beats_a_force_link(self) -> None:
        """Unchanged behaviour, pinned here because the method plumbing runs
        through the same branch order: a co-present pair that also matches a
        declaration is a detector error, not an identity."""
        result = prefilter(
            EvidenceVector(co_presence_violation=1.0, declaration_match=1.0)
        )
        assert result.verdict is PrefilterVerdict.BLOCK


class TestGateCarriesTheMethodOut:
    def test_a_gazetteer_hit_is_not_reported_as_scored(self) -> None:
        """The defect in one assertion: this link never reaches the scorer."""
        gate = ConformalGate()
        decided = gate.decide([_candidate(gazetteer_exact_match=1.0)])
        assert decided.decision is Decision.LINK
        assert decided.method is ResolutionMethod.GAZETTEER_EXACT

    def test_a_scored_link_is_reported_as_scored(self) -> None:
        gate = ConformalGate(link_threshold=0.1, new_threshold=0.01)
        candidate = _candidate(surface_similarity=1.0)
        candidate.probability = 0.9
        decided = gate.decide([candidate])
        assert decided.decision is Decision.LINK
        assert decided.method is ResolutionMethod.SCORED

    def test_no_candidates_is_a_new_entity_not_a_prefilter_hit(self) -> None:
        decided = ConformalGate().decide([])
        assert decided.decision is Decision.NEW
        assert decided.method is ResolutionMethod.SCORED
        assert decided.candidate is None

    def test_defer_keeps_the_runner_up_for_the_queue(self) -> None:
        gate = ConformalGate(link_threshold=0.9, new_threshold=0.1)
        candidate = _candidate(surface_similarity=0.5)
        candidate.probability = 0.5
        decided = gate.decide([candidate])
        assert decided.decision is Decision.DEFER
        assert decided.candidate is candidate

    def test_gate_decision_defaults_to_scored(self) -> None:
        assert GateDecision(Decision.NEW, None, "x").method is ResolutionMethod.SCORED


class TestEscalationSummary:
    """`router.report()` computed the escalation rate and had zero callers.

    `docs/design/architecture.md` Section 7 names it a claimed contribution and
    non-negotiable #7 calls it "a reported metric, not a failure mode", yet it
    appeared in no output anywhere (COMPLETION_PLAN Track 2 item 8,
    EVOLUTION 4.79). Read off the persisted `llm_call` table rather than a
    router's in-process counters, because `eval` runs in a separate process
    that makes no LLM calls and would truthfully report zero.
    """

    def test_an_empty_table_is_zero_not_a_division_error(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from echotales.core.store import Store

        store = Store(str(tmp_path / "e.db"))
        try:
            summary = store.escalation_summary()
            assert summary["calls"] == 0
            assert summary["escalation_rate"] == 0.0
            assert summary["by_stage"] == []
        finally:
            store.close()

    def test_the_rate_is_escalations_over_calls(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from echotales.core.store import Store

        store = Store(str(tmp_path / "e.db"))
        try:
            store.conn.executemany(
                "INSERT INTO llm_call(novel_id, stage, tier, model, escalated,"
                " prompt_tokens, completion_tokens, latency_ms)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [
                    ("ri", "ner", "local", "qwen2.5:7b", 0, 100, 10, 1900),
                    ("ri", "ner", "local", "qwen2.5:7b", 1, 100, 10, 2100),
                    ("ri", "persona_split", "local", "qwen2.5:7b", 0, 50, 5, 1000),
                    ("ri", "persona_split", "local", "qwen2.5:7b", 0, 50, 5, 1000),
                ],
            )
            store.conn.commit()
            summary = store.escalation_summary()
            assert summary["calls"] == 4
            assert summary["escalations"] == 1
            assert summary["escalation_rate"] == 0.25
            assert summary["tokens"] == 330  # (100+10)*2 + (50+5)*2
            assert {row["stage"] for row in summary["by_stage"]} == {"ner", "persona_split"}
        finally:
            store.close()
