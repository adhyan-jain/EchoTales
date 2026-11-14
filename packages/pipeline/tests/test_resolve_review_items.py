"""Non-negotiable 7: a mention group the gate cannot decide ends as a review item, never as silence.

Before this, the deferred queue was discarded at the end of the run: 13 / 23 / 12 named groups on three deterministic
builds were left unlinked with no trace, and `adjudicate_remaining` dropped the LLM's verdict without applying it.
The gate is stubbed so each test controls the decision; strings are synthetic.
"""

from __future__ import annotations

import pytest
from echotales.core.enums import (
    AliasType,
    BlockType,
    Decision,
    ReferenceMode,
    ResolutionMethod,
    SpanType,
    TargetKind,
)
from echotales.core.models import (
    Block,
    Candidate,
    Chapter,
    DiscoursePosition,
    Mention,
    ResolutionOutcome,
    Self,
)
from echotales.core.store import Store
from echotales.pipeline import flow
from echotales.pipeline.resolve import review
from echotales.pipeline.resolve import runner as runner_mod
from echotales.pipeline.resolve.gate import GateDecision
from echotales.pipeline.resolve.runner import GlobalResolver

TEXT = "Zorrin waited by the gate."


def _mention(mid: str, gid: str, alias: AliasType = AliasType.RIGID_NAME, text: str = "Zorrin") -> Mention:
    return Mention(id=mid, novel_id="t", segment_id="s", chapter=1.0, offset=0, text=text, alias_type=alias,
                   span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT, block_index=0,
                   local_group_id=gid)


def _store(*mentions: Mention) -> Store:
    s = Store(":memory:")
    s.add_novel("t", "T", "x.epub", "generic")
    s.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="1.html",
                          blocks=[Block(index=0, block_type=BlockType.PROSE, text=TEXT)]))
    s.add_mentions(list(mentions))
    s.conn.commit()
    return s


def _cands(*probs: float) -> list[Candidate]:
    return [Candidate(target_kind=TargetKind.SELF, target_id=f"t:self:{i}", label=f"Cand{i}",
                      retrieval_score=0.5, probability=p) for i, p in enumerate(probs)]


def _resolver(store: Store, monkeypatch: pytest.MonkeyPatch, decision: GateDecision, cands: list[Candidate],
              **kw: object) -> GlobalResolver:
    r = GlobalResolver("t", store, **kw)
    monkeypatch.setattr(type(r.retriever), "retrieve", lambda self, surface, context: [c.model_copy() for c in cands])
    monkeypatch.setattr(runner_mod, "score_evidence", lambda *a, **k: cands[0].evidence)
    monkeypatch.setattr(type(r.model), "score_candidates", lambda self, cs: cs)
    monkeypatch.setattr(type(r.gate), "decide", lambda self, cs: decision)
    monkeypatch.setattr(GlobalResolver, "_bind_alias", lambda *a, **k: None)
    return r


def _defer(store: Store, monkeypatch: pytest.MonkeyPatch, reason: str = "p=0.300 in deferred band") -> GlobalResolver:
    cands = _cands(0.30, 0.10)
    r = _resolver(store, monkeypatch, GateDecision(Decision.DEFER, cands[0], reason), cands)
    for gid in sorted({m.local_group_id for m in store.get_mentions("t", 1.0)}):
        group = [m for m in store.get_mentions("t", 1.0) if m.local_group_id == gid]
        r.resolve_group(group, TEXT)
        r.report.groups += 1
    return r


def _items(store: Store) -> list:
    return store.list_review_items("t")


def test_deferred_named_group_gives_exactly_one_item_with_candidates_and_reason(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"), _mention("m2", "g1"))
    r = _defer(s, monkeypatch)
    r.record_deferrals()
    (item,) = _items(s)
    group, *cands = item.candidates
    assert item.kind == "resolve_deferred" and item.chapter == 1.0 and not item.resolved
    assert group["surfaces"] == ["Zorrin"] and group["mention_ids"] == ["m1", "m2"]
    assert group["reason_kind"] == "below_link_above_new" and "deferred band" in group["reason"]
    assert [c["target_id"] for c in cands] == ["t:self:0", "t:self:1"] and cands[0]["probability"] == 0.3
    assert r.report.escalated == 1 and r.report.deliberately_deferred == 0


def test_tie_margin_reason_is_named(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"))
    r = _defer(s, monkeypatch, reason="top two candidates within 0.010")
    r.record_deferrals()
    assert _items(s)[0].candidates[0]["reason_kind"] == "tie_margin"


def test_deictic_only_group_is_deliberate_not_a_review_item(monkeypatch) -> None:
    s = _store(_mention("m1", "g1", AliasType.RELATIONAL_DEICTIC, "Grandpa"))
    r = _defer(s, monkeypatch)  # deferred by the gate, but nothing in it can found an entity
    r.record_deferrals()
    assert _items(s) == [] and r.report.escalated == 0 and r.report.deliberately_deferred == 1


def test_rerun_neither_duplicates_nor_reopens_a_resolved_item(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"))
    _defer(s, monkeypatch).record_deferrals()
    (first,) = _items(s)
    _defer(s, monkeypatch).record_deferrals()
    (again,) = _items(s)
    assert again.id == first.id and again.created_at == first.created_at

    s.resolve_review_item(first.id, "reviewer: not a character")
    _defer(s, monkeypatch).record_deferrals()
    (kept,) = _items(s)
    assert kept.resolved and kept.resolution == "reviewer: not a character"


def test_changed_evidence_reopens_a_resolved_item(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"))
    _defer(s, monkeypatch).record_deferrals()
    (first,) = _items(s)
    s.resolve_review_item(first.id, "reviewer: undecided")
    _defer(s, monkeypatch, reason="top two candidates within 0.010").record_deferrals()
    assert not _items(s)[0].resolved


def test_case_that_links_on_a_later_run_closes_its_item_with_a_machine_note(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"))
    _defer(s, monkeypatch).record_deferrals()
    s.conn.execute("UPDATE mention SET target_id='t:self:0', target_kind='SELF'")
    r = GlobalResolver("t", s)  # a fresh run: empty queue
    r.record_deferrals()
    (item,) = _items(s)
    assert item.resolved and item.resolution == review.AUTO_CLOSED and r.report.review_items_closed == 1
    # ...and a machine-closed item is reopened if the case comes back.
    s.conn.execute("UPDATE mention SET target_id=NULL, target_kind=NULL")
    _defer(s, monkeypatch).record_deferrals()
    assert not _items(s)[0].resolved and len(_items(s)) == 1


class _FakeRouter:
    pass


def _adjudicating(s: Store, monkeypatch, outcome: ResolutionOutcome | Exception) -> GlobalResolver:
    r = _defer(s, monkeypatch)
    r.router = _FakeRouter()  # type: ignore[assignment]
    r.queue.max_attempts = 0  # every case is exhausted

    def fake(request, router, profiles, model, *, novel_id=""):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(runner_mod, "adjudicate", fake)
    return r


def test_adjudicated_link_is_applied_and_recorded(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"), _mention("m2", "g1"))
    out = ResolutionOutcome(group_id="g1", decision=Decision.LINK, target_id="t:self:0",
                            method=ResolutionMethod.LLM_ADJUDICATED, rationale="same speaker")
    r = _adjudicating(s, monkeypatch, out)
    assert r.adjudicate_remaining() == 1
    ms = s.get_mentions("t", 1.0)
    assert {m.target_id for m in ms} == {"t:self:0"} and {m.method for m in ms} == {ResolutionMethod.LLM_ADJUDICATED}
    assert r.report.by_method["LLM_ADJUDICATED"] == 1 and len(r.queue) == 0
    r.record_deferrals()
    assert _items(s) == []


def test_adjudicator_defer_or_failure_escalates_with_its_note(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"))
    out = ResolutionOutcome(group_id="g1", decision=Decision.DEFER, rationale="model was uncertain")
    r = _adjudicating(s, monkeypatch, out)
    r.adjudicate_remaining()
    r.record_deferrals()
    (item,) = _items(s)
    assert item.candidates[0]["adjudication"] == "model was uncertain"

    s2 = _store(_mention("m1", "g1"))
    r2 = _adjudicating(s2, monkeypatch, RuntimeError("server down"))
    assert r2.adjudicate_remaining() == 0
    r2.record_deferrals()
    assert "server down" in _items(s2)[0].candidates[0]["adjudication"]
    assert s2.get_mentions("t", 1.0)[0].target_id is None


def test_report_carries_counts_and_rate(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"), _mention("m2", "g2", AliasType.RELATIONAL_DEICTIC, "Grandpa"))
    r = _defer(s, monkeypatch)
    r.record_deferrals()
    assert (r.report.groups, r.report.escalated, r.report.deliberately_deferred) == (2, 1, 1)
    assert r.report.escalation_rate == 0.5
    assert "1 escalated to review (50.00%)" in r.report.summary()


def test_review_items_do_not_change_which_mentions_link(monkeypatch) -> None:
    def build(record: bool) -> list[tuple[str, str | None]]:
        s = _store(_mention("m1", "g1"), _mention("m2", "g2", text="Other"))
        r = _defer(s, monkeypatch)
        if record:
            r.record_deferrals()
        return [(m.id, m.target_id) for m in s.get_mentions("t", 1.0)]

    assert build(True) == build(False)




def test_auditor_passes_recorded_deferral_and_fails_an_unrecorded_one(monkeypatch) -> None:
    s = _store(_mention("m1", "g1"))
    s.add_self(Self(id='t:self:0', novel_id='t', canonical_label='Cand0', first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    check = flow.check_resolve_outcome
    unrecorded = check(s, "t", None)
    assert unrecorded.status is flow.Status.FAIL and unrecorded.stats["deferred_groups_unrecorded"] == 1
    _defer(s, monkeypatch).record_deferrals()
    ok = check(s, "t", None)
    assert ok.status is flow.Status.PASS and ok.stats["deferred_groups_recorded"] == 1
    # A machine-closed item no longer accounts for an unlinked mention.
    s.resolve_review_item(_items(s)[0].id, review.AUTO_CLOSED)
    assert check(s, "t", None).status is flow.Status.FAIL


def test_auditor_survives_a_database_without_the_review_table() -> None:
    s = _store(_mention("m1", "g1"))
    s.add_self(Self(id='t:self:0', novel_id='t', canonical_label='Cand0', first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    s.conn.execute("DROP TABLE review_item")
    assert flow.check_resolve_outcome(s, "t", None).status is flow.Status.FAIL


def test_same_local_group_id_in_two_chapters_is_two_cases() -> None:
    from echotales.pipeline.resolve.gate import DeferredCase, DeferredQueue

    q = DeferredQueue()
    a = DeferredCase(group_id="g19", chapter=3.0, surface="A", context="")
    b = DeferredCase(group_id="g19", chapter=48.0, surface="B", context="")
    q.add(a)
    q.add(b)
    assert len(q) == 2
    q.remove(a)
    assert q.cases() == [b]
