"""Name keys are retrieval signals; the evidence gate decides identity (owner rule 2026-11-26).

Measured basis: scripts/eval/key_collision_audit.py -> data/eval/ner/key_collisions.json (model-drafted silver gold).
"""

from __future__ import annotations

from echotales.core.enums import AliasType, Decision, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Mention
from echotales.pipeline.ingest.normalize import comparison_key, romanization_skeleton, token_set_key
from echotales.pipeline.resolve.evidence import EvidenceContext, score_evidence
from echotales.pipeline.resolve.gate import ConformalGate
from echotales.pipeline.resolve.retrieve import CandidateRetriever
from echotales.pipeline.resolve.score import ScoringModel


def _mention(text: str, alias_type: AliasType = AliasType.RIGID_NAME) -> Mention:
    return Mention(
        id="m", novel_id="t", segment_id="s", chapter=1, offset=0, text=text, alias_type=alias_type,
        span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT, block_index=0,
    )


def _decide(retriever: CandidateRetriever, mention: Mention, gate: ConformalGate | None = None):
    candidates = retriever.retrieve(mention.text, "")
    ctx = EvidenceContext(shared_alias_keys=retriever.shared_alias_keys())
    for c in candidates:
        c.evidence = score_evidence(mention, c, retriever.profiles.get(c.target_id), ctx)
    candidates = ScoringModel().score_candidates(candidates)
    return candidates, (gate or ConformalGate()).decide(candidates)


def test_token_set_key_is_order_insensitive_but_not_the_comparison_key() -> None:
    assert token_set_key("Gojo Satoru") == token_set_key("Satoru Gojo") == token_set_key("Mr. Satoru Gojo")
    assert comparison_key("Gojo Satoru") != comparison_key("Satoru Gojo")  # unchanged: no silent order merge


def test_skeleton_catches_alternate_romanisations_and_honestly_not_all() -> None:
    caught = [("Yoo Joonghyuk", "Yu Jung-hyeok"), ("Xiao Yan", "Hsiao Yen"), ("Jung Hyeok", "Chung Hyuk")]
    for a, b in caught:
        assert romanization_skeleton(a) == romanization_skeleton(b) != "", (a, b)
    # Not caught by design: too short to carry signal, and a vowel-change that alters the consonant frame.
    assert romanization_skeleton("Li") == ""
    assert romanization_skeleton("Satoru Gojo") != romanization_skeleton("Gojo Satoru")  # order: token_set_key's job
    assert romanization_skeleton("Yu Jung-hyeok") != romanization_skeleton("Yoo Joon Hyuk Min")
    # Lossy by design: a different person with the same consonant frame collides, hence retrieval-only.
    assert romanization_skeleton("Wen Lin") == romanization_skeleton("Wan Lin")


def test_two_clan_heads_are_not_merged_by_key() -> None:
    retriever = CandidateRetriever()
    retriever.observe("a", "Gu Yue Mo Bei", "clan", 1.0)
    retriever.observe("a", "the clan head", "clan", 1.0)
    retriever.observe("b", "Bai Ning Bing", "clan", 1.0)
    retriever.observe("b", "the clan head", "clan", 1.0)
    assert "clanhead" in retriever.shared_alias_keys()
    candidates, gated = _decide(retriever, _mention("the clan head", AliasType.TRANSFERABLE_TITLE))
    assert all(c.evidence.gazetteer_exact_match == 0.0 for c in candidates)
    assert gated.decision is not Decision.LINK or "exact match" not in gated.rationale


def test_title_alias_type_never_takes_the_exact_match_prefilter_even_with_one_owner() -> None:
    retriever = CandidateRetriever()
    retriever.observe("a", "the clan head", "clan", 1.0)
    candidates, gated = _decide(retriever, _mention("the clan head", AliasType.TRANSFERABLE_TITLE))
    assert candidates and candidates[0].evidence.gazetteer_exact_match == 0.0
    assert "exact match" not in gated.rationale


def test_rigid_unique_exact_match_still_links() -> None:
    retriever = CandidateRetriever()
    retriever.observe("a", "Fang Yuan", "ctx", 1.0)
    _, gated = _decide(retriever, _mention("Fang Yuan's"))
    assert gated.decision is Decision.LINK and "exact match" in gated.rationale


def test_variant_match_alone_never_links() -> None:
    retriever = CandidateRetriever()
    retriever.observe("a", "Yoo Joonghyuk", "ctx", 1.0, target_kind=TargetKind.SELF)
    retriever.observe("b", "Kim Dokja", "ctx", 1.0)
    candidates, gated = _decide(retriever, _mention("Yu Jung-hyeok"))
    assert "romanization_variant_match" in retriever.last_variant_features["a"]
    assert next(c.target_id for c in candidates) == "a"  # retrieved so it can be scored ...
    assert gated.decision is not Decision.LINK  # ... but the gate does not link on the name signal alone

    retriever.observe("c", "Satoru Gojo", "ctx", 1.0)
    candidates, gated = _decide(retriever, _mention("Gojo Satoru"))
    assert "name_order_match" in retriever.last_variant_features["c"]
    assert gated.decision is not Decision.LINK
