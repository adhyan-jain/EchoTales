"""The review gate: ranked speaker queue, character timeline, bible lock, and the render guard (Phase B)."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path

import pytest
from echotales.core.enums import (
    AliasType, AssertedBy, AttributionMethod, BlockType, Prominence, SpanType, TargetKind, TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import AliasBinding, Attribute, Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.pipeline_run import ensure_pipeline_run
from echotales.core.store import Store
from echotales.pipeline import review_gate as rg
from echotales.pipeline.jobs import JobQueue
from echotales.pipeline.version import PIPELINE_VERSION
from echotales.pipeline.webview_server import NovelSource, Registry, make_handler

NOVEL = "n"


def _span(i: int, chapter: float, speaker: str | None, method: AttributionMethod, confidence: float = 0.8,
          span_type: SpanType = SpanType.DIALOGUE) -> Span:
    return Span(id=f"{NOVEL}:{chapter:g}:{i}:0", novel_id=NOVEL, chapter=chapter, block_index=i, start=0, end=10,
                span_type=span_type, text=f"line {i}", speaker_self_id=speaker, attribution_method=method,
                confidence=confidence)


def _world(stamped: bool = True) -> Store:
    store = Store(":memory:")
    store.add_novel(NOVEL, "N", "x", "epub")
    store.add_chapter(Chapter(novel_id=NOVEL, number=1.0, title="T", source_href="a",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text="x")]))
    for sid, name in ((f"{NOVEL}:self:a", "Alice"), (f"{NOVEL}:self:b", "Bob")):
        store.add_self(Self(id=sid, novel_id=NOVEL, canonical_label=name, prominence=Prominence.RECURRING,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    if stamped:
        ensure_pipeline_run(store, novel_id=NOVEL, source_digest="abcdef012345", pipeline_version=PIPELINE_VERSION)
    return store


def test_queue_lists_unnamed_and_role_slots_but_not_settled_or_confident_guesses() -> None:
    store = _world()
    store.add_spans([
        _span(0, 1.0, f"{NOVEL}:self:a", AttributionMethod.EXPLICIT, 1.0),        # settled
        _span(1, 1.0, f"{NOVEL}:self:a", AttributionMethod.CONTEXTUAL_LLM, 0.8),  # a named model guess
        _span(2, 1.0, None, AttributionMethod.UNRESOLVED, 0.0),                    # unnamed
        _span(3, 1.0, None, AttributionMethod.UNRESOLVED, 0.0),                    # unnamed
        _span(4, 1.0, f"{NOVEL}:title:elder", AttributionMethod.EPITHET_SLOT, 0.5),  # role slot
        _span(5, 1.0, f"{NOVEL}:self:b", AttributionMethod.CONTEXTUAL_LLM, 0.4),   # low confidence
    ])
    queue = rg.speaker_queue(store, NOVEL)
    reasons = {i["span_id"].split(":")[2]: i["reason"] for i in queue["items"]}
    assert reasons == {"2": "unnamed", "3": "unnamed", "4": "role_slot", "5": "low_confidence"}
    assert queue["items"][0]["affected"] == 2 and queue["items"][0]["reason"] == "unnamed"  # shared slot ranks first
    audit = rg.speaker_queue(store, NOVEL, include_guesses=True)
    assert audit["total"] == 5 and any(i["reason"] == "model_guess" for i in audit["items"])


def test_queue_filters_by_chapter_and_limit() -> None:
    store = _world()
    store.add_spans([_span(i, 1.0, None, AttributionMethod.UNRESOLVED, 0.0) for i in range(3)]
                    + [_span(0, 2.0, None, AttributionMethod.UNRESOLVED, 0.0)])
    assert rg.speaker_queue(store, NOVEL, chapter=2.0)["total"] == 1
    assert len(rg.speaker_queue(store, NOVEL, limit=2)["items"]) == 2


def test_timeline_shows_a_title_held_before_it_was_learned_and_the_evidence_for_a_look() -> None:
    store = _world()
    sid = f"{NOVEL}:self:a"
    store.add_alias_binding(NOVEL, AliasBinding(
        alias="the clan head", alias_type=AliasType.TRANSFERABLE_TITLE, target_kind=TargetKind.SELF, target_id=sid,
        interval=FuzzyInterval.open_ended(1, last_evidence=1), learned_at_pos=DiscoursePosition(chapter=6, offset=0),
        observer_id="reader", asserted_by=AssertedBy.INFERENCE, truth_status=TruthStatus.TRUE, evidence="clan leader Alice"))
    store.add_attribute(NOVEL, Attribute(
        target_kind=TargetKind.PERSONA, target_id=f"{sid}:body1", key="eye_color", value="gray",
        interval=FuzzyInterval.open_ended(12, last_evidence=12), learned_at_pos=DiscoursePosition(chapter=12, offset=0),
        observer_id="reader", asserted_by=AssertedBy.INFERENCE, evidence="the gray-eyed inspector", confidence=0.8))
    timeline = rg.character_timeline(store, NOVEL, sid)
    title = next(i for i in timeline["identities"] if i["alias"] == "the clan head")
    assert (title["story_from"], title["learned_chapter"], title["story_to"]) == (1, 6, None)
    look = timeline["looks"][0]
    assert (look["key"], look["value"], look["from_chapter"], look["evidence"]) == ("eye_color", "gray", 12, "the gray-eyed inspector")
    assert rg.character_timeline(store, NOVEL, "missing") is None


def test_lock_versions_count_up_and_an_edit_marks_exactly_its_chapter_dirty() -> None:
    store = _world()
    store.add_spans([_span(0, 1.0, f"{NOVEL}:self:a", AttributionMethod.CONTEXTUAL_LLM),
                     _span(0, 2.0, f"{NOVEL}:self:b", AttributionMethod.CONTEXTUAL_LLM)])
    assert rg.bible_status(store, NOVEL)["current"]["dirty"] is True  # nothing locked yet
    first = rg.lock_bible(store, NOVEL, "first pass")
    assert first["version"] == 1 and first["changed_chapters"] == []
    status = rg.bible_status(store, NOVEL)["current"]
    assert status["dirty"] is False and status["locked_version"] == 1 and status["changed_chapters"] == []
    store.set_span_speaker(NOVEL, f"{NOVEL}:2:0:0", f"{NOVEL}:self:a", "EXPLICIT", 1.0)  # a reviewer fixes chapter 2
    dirty = rg.bible_status(store, NOVEL)["current"]
    assert dirty["dirty"] is True and dirty["changed_chapters"] == [2]
    second = rg.lock_bible(store, NOVEL)
    assert second["version"] == 2 and second["changed_chapters"] == [2]
    assert [lock["version"] for lock in rg.bible_status(store, NOVEL)["locks"]] == [1, 2]


def test_a_stale_build_cannot_be_locked_and_an_unlocked_one_cannot_render() -> None:
    stale = _world(stamped=False)
    with pytest.raises(rg.StaleBuild):
        rg.lock_bible(stale, NOVEL)
    store = _world()
    assert "no locked bible" in rg.unlocked_reason(store, NOVEL)
    rg.lock_bible(store, NOVEL)
    assert rg.unlocked_reason(store, NOVEL) is None
    store.add_spans([_span(0, 1.0, None, AttributionMethod.UNRESOLVED, 0.0)])
    assert "edits since bible v1" in rg.unlocked_reason(store, NOVEL)


@pytest.fixture
def gate_server(tmp_path: Path):
    db_path = tmp_path / "gate.db"
    store = Store(str(db_path))
    store.add_novel("gate", "Gate", "x", "epub")
    ensure_pipeline_run(store, novel_id="gate", source_digest="abcdef012345", pipeline_version=PIPELINE_VERSION)
    store.add_self(Self(id="gate:self:a", novel_id="gate", canonical_label="Alice", prominence=Prominence.RECURRING,
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
    store.add_spans([Span(id="gate:1:0:0", novel_id="gate", chapter=1.0, block_index=0, start=0, end=5,
                          span_type=SpanType.DIALOGUE, text="hi", speaker_self_id=None,
                          attribution_method=AttributionMethod.UNRESOLVED, confidence=0.0)])
    store.conn.commit()  # add_spans does not commit; the server opens its own connection to this file
    store.close()
    registry = Registry([NovelSource(novel_id="gate", label="Gate", db_path=db_path)], corrections_dir=tmp_path / "c")
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(registry, JobQueue()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2.0)


def _call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:  # type: ignore[type-arg]
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(method, path, body=json.dumps(body) if body is not None else None,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read().decode() or "{}")


def test_http_queue_timeline_and_lock(gate_server: int) -> None:
    port = gate_server
    status, queue = _call(port, "GET", "/api/novels/gate/review/lines?chapter=1")
    assert status == 200 and queue["total"] == 1 and queue["items"][0]["reason"] == "unnamed"
    status, timeline = _call(port, "GET", "/api/novels/gate/characters/gate%253Aself%253Aa/timeline")
    assert status == 200 and timeline["label"] == "Alice"
    assert _call(port, "GET", "/api/novels/gate/characters/nobody/timeline")[0] == 404
    assert _call(port, "GET", "/api/novels/gate/review/lines?chapter=abc")[0] == 400

    status, state = _call(port, "GET", "/api/novels/gate/bible")
    assert status == 200 and state["current"]["locked_version"] is None and state["current"]["dirty"] is True
    status, lock = _call(port, "POST", "/api/novels/gate/bible/lock", {"note": "ok"})
    assert status == 200 and lock["version"] == 1 and lock["counts"]["lines"] == 1
    status, state = _call(port, "GET", "/api/novels/gate/bible")
    assert state["current"]["dirty"] is False and state["locks"][0]["note"] == "ok"


def test_the_render_guard_needs_a_current_lock_for_a_real_engine_but_not_for_the_stub() -> None:
    from types import SimpleNamespace

    from echotales.pipeline.webview_server import _stale_build_refusal

    stale = SimpleNamespace(store=_world(stamped=False))
    assert _stale_build_refusal(stale, NOVEL, "stub") is None  # placeholders: nothing to protect
    assert "no recorded build" in _stale_build_refusal(stale, NOVEL, "sdxl")

    handle = SimpleNamespace(store=_world())
    assert "no locked bible" in _stale_build_refusal(handle, NOVEL, "sdxl")
    rg.lock_bible(handle.store, NOVEL)
    assert _stale_build_refusal(handle, NOVEL, "sdxl") is None
    handle.store.add_spans([_span(0, 1.0, None, AttributionMethod.UNRESOLVED, 0.0)])
    assert "edits since bible v1" in _stale_build_refusal(handle, NOVEL, "sdxl")


def test_timeline_shows_a_repeated_binding_once() -> None:
    store = _world()
    sid = f"{NOVEL}:self:a"
    for _ in range(3):
        store.add_alias_binding(NOVEL, AliasBinding(
            alias="Klein Moretti", alias_type=AliasType.RIGID_NAME, target_kind=TargetKind.SELF, target_id=sid,
            interval=FuzzyInterval.open_ended(1, last_evidence=1), learned_at_pos=DiscoursePosition(chapter=1, offset=0),
            observer_id="reader", asserted_by=AssertedBy.INFERENCE, truth_status=TruthStatus.TRUE, evidence="took Klein's body"))
    names = [i["alias"] for i in rg.character_timeline(store, NOVEL, sid)["identities"]]
    assert names.count("Klein Moretti") == 1
