"""B1 (CHIMERA defect backlog): `retry_deferred` must not claim a recovery that wrote no link.

Before the fix a deferred case whose re-gating said LINK was removed from the queue and counted as "recovered" while
no mention was linked: resolution was overstated and `unresolved` (= queue length) understated. Now, by default, such
a case stays queued and is only tallied in `regated_link_not_applied`; with `apply_deferred_links=True` the link is
really written to the group's mentions. Synthetic strings only; the regating step is stubbed so the test controls
the decision.
"""

from __future__ import annotations

import pytest

from echotales.core.enums import AliasType, BlockType, Decision, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Candidate, Chapter, Mention
from echotales.core.store import Store
from echotales.pipeline.resolve import runner as runner_mod
from echotales.pipeline.resolve.gate import DeferredCase, GateDecision
from echotales.pipeline.resolve.runner import GlobalResolver


def _store_with_one_unresolved_mention() -> Store:
    s = Store(":memory:")
    s.add_novel("t", "T", "x.epub", "generic")
    s.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="1.html",
                          blocks=[Block(index=0, block_type=BlockType.PROSE, text="Zorrin waited by the gate.")]))
    s.add_mentions([Mention(id="m1", novel_id="t", segment_id="s", chapter=1.0, offset=0, text="Zorrin",
                            alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                            reference_mode=ReferenceMode.PRESENT, block_index=0, local_group_id="g1")])
    s.conn.commit()
    return s


def _resolver(store: Store, *, apply: bool, monkeypatch: pytest.MonkeyPatch) -> GlobalResolver:
    r = GlobalResolver("t", store, apply_deferred_links=apply)
    cand = Candidate(target_kind=TargetKind.SELF, target_id="t:self:z", label="Zorrin", retrieval_score=0.9)
    # class-level patches: these collaborators are slotted, so instance attributes are read-only
    monkeypatch.setattr(type(r.retriever), "retrieve", lambda self, surface, context: [cand.model_copy()])
    monkeypatch.setattr(runner_mod, "score_evidence", lambda *a, **k: cand.evidence)
    monkeypatch.setattr(type(r.model), "score_candidates", lambda self, cs: cs)
    monkeypatch.setattr(type(r.gate), "decide", lambda self, cs: GateDecision(Decision.LINK, cs[0], "stubbed"))
    r.queue.add(DeferredCase(group_id="g1", chapter=1.0, surface="Zorrin", context="Zorrin waited by the gate."))
    return r


def test_default_does_not_claim_a_recovery_and_keeps_the_case_queued(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _store_with_one_unresolved_mention()
    r = _resolver(s, apply=False, monkeypatch=monkeypatch)
    assert r.retry_deferred() == 0
    assert r.report.recovered_from_deferral == 0
    assert r.report.regated_link_not_applied == 1
    assert r.report.by_method.get("DEFERRED_RERESOLVED", 0) == 0
    assert len(r.queue) == 1                                  # unresolved stays honest
    assert s.get_mentions("t", 1.0)[0].target_id is None      # nothing was linked


def test_opt_in_writes_the_link_and_only_then_counts_it(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _store_with_one_unresolved_mention()
    r = _resolver(s, apply=True, monkeypatch=monkeypatch)
    monkeypatch.setattr(GlobalResolver, "_bind_alias", lambda *a, **k: None)
    assert r.retry_deferred() == 1
    assert r.report.recovered_from_deferral == 1
    assert r.report.by_method.get("DEFERRED_RERESOLVED", 0) == 1
    assert len(r.queue) == 0
    m = s.get_mentions("t", 1.0)[0]
    assert m.target_id == "t:self:z" and m.method.value == "DEFERRED_RERESOLVED"


def test_opt_in_with_no_matching_unresolved_mentions_counts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _store_with_one_unresolved_mention()
    r = _resolver(s, apply=True, monkeypatch=monkeypatch)
    r.queue.add(DeferredCase(group_id="ghost", chapter=1.0, surface="Nobody", context=""))
    monkeypatch.setattr(GlobalResolver, "_bind_alias", lambda *a, **k: None)
    r.retry_deferred()
    assert r.report.regated_link_not_applied == 1   # the ghost group has no mentions to link
    assert len(r.queue) == 1
