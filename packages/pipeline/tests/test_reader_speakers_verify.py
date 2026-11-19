"""The verification pass: a yes/no check on model-named lines that have no speech tag in their own block."""

from __future__ import annotations

from echotales.core.enums import AttributionMethod, BlockType, Prominence, SpanType
from echotales.core.models import Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.reader import speakers_verify as sv


def _world(blocks: list[str], method: AttributionMethod = AttributionMethod.CONTEXTUAL_LLM) -> tuple[Store, Chapter]:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    chapter = Chapter(novel_id="n", number=1.0, title="T", source_href="a",
                      blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(blocks)])
    store.add_chapter(chapter)
    store.add_self(Self(id="n:self:alice", novel_id="n", canonical_label="Alice",
                        first_attested_pos=DiscoursePosition(chapter=1, offset=0), prominence=Prominence.RECURRING))
    store.add_spans([
        Span(id=f"n:1:{i}:0", novel_id="n", chapter=1.0, block_index=i, start=0, end=t.find("”") + 1,
             span_type=SpanType.DIALOGUE, text=t, speaker_self_id="n:self:alice", attribution_method=method, confidence=0.8)
        for i, t in enumerate(blocks)
    ])
    return store, chapter


def _client(verdict: str) -> ModelClient:
    stub = StubProvider()
    stub.register_response("reader", {"verdict": verdict})
    return ModelClient(provider_override=stub)


def _who(store: Store, i: int) -> str | None:
    return next(s for s in store.get_spans("n", 1.0) if s.block_index == i).speaker_self_id


def test_a_no_returns_an_untagged_line_to_unresolved() -> None:
    store, chapter = _world(["“Who goes there?”"])
    report = sv.verify_chapter(store, _client("no"), chapter)
    assert _who(store, 0) is None and (report.asked, report.no, report.rejected) == (1, 1, 1)


def test_yes_keeps_it_and_unclear_keeps_it_unless_asked_to_reject() -> None:
    store, chapter = _world(["“Who goes there?”"])
    assert sv.verify_chapter(store, _client("yes"), chapter).rejected == 0
    assert sv.verify_chapter(store, _client("unclear"), chapter).rejected == 0 and _who(store, 0) == "n:self:alice"
    assert sv.verify_chapter(store, _client("unclear"), chapter, reject_unclear=True).rejected == 1


def test_a_line_tagged_in_its_own_block_is_never_questioned() -> None:
    store, chapter = _world(["“Who goes there?” Alice asked."])
    report = sv.verify_chapter(store, _client("no"), chapter)
    assert report.asked == 0 and report.skipped_tagged == 1 and _who(store, 0) == "n:self:alice"


def test_a_reviewers_decision_is_never_questioned() -> None:
    store, chapter = _world(["“Who goes there?”"], method=AttributionMethod.HUMAN)
    assert sv.verify_chapter(store, _client("no"), chapter).asked == 0 and _who(store, 0) == "n:self:alice"


def test_the_prompt_marks_the_asked_line_and_includes_the_neighbours() -> None:
    passage = sv._passage(Chapter(novel_id="n", number=1.0, title="T", source_href="a", blocks=[
        Block(index=0, block_type=BlockType.PROSE, text="Before."),
        Block(index=1, block_type=BlockType.PROSE, text="“One.” and “Two.”"),
        Block(index=2, block_type=BlockType.PROSE, text="After."),
    ]), 1, 1)
    assert passage == "Before.\n\n“One.” and >>>“Two.”<<<\n\nAfter."
