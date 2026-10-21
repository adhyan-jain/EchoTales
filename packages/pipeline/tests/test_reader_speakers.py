"""The reader pass's speaker stage, driven by the stub provider (no model, no network)."""

from __future__ import annotations

from echotales.core.enums import AttributionMethod, BlockType, Prominence, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.reader import speakers_pass as sp

TEXT0 = "“Hello there.” Alice smiled at Bob."
TEXT1 = "“Who are you?” Carol Wu asked from the doorway."
TEXT2 = "“Nobody important,” someone muttered."


def _world(first_attribution: AttributionMethod = AttributionMethod.PROXIMAL) -> tuple[Store, Chapter]:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    chapter = Chapter(
        novel_id="n", number=1.0, title="T", source_href="a",
        blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate((TEXT0, TEXT1, TEXT2))],
    )
    store.add_chapter(chapter)
    for sid, name in (("n:self:alice", "Alice"), ("n:self:bob", "Bob")):
        store.add_self(
            Self(id=sid, novel_id="n", canonical_label=name,
                 first_attested_pos=DiscoursePosition(chapter=1, offset=0), prominence=Prominence.RECURRING)
        )
    store.add_self(
        Self(id="n:self:gate", novel_id="n", canonical_label="Chanis Gate",
             first_attested_pos=DiscoursePosition(chapter=1, offset=0), kind=TargetKind.LOCATION)
    )
    types = (SpanType.CROWD_REACTION, SpanType.DIALOGUE, SpanType.DIALOGUE)
    store.add_spans([
        Span(id=f"n:1:{i}:0", novel_id="n", chapter=1.0, block_index=i, start=0, end=len(t.split("”")[0]) + 1,
             span_type=types[i], text=t, speaker_self_id="n:self:bob" if i == 2 else None,
             attribution_method=first_attribution)
        for i, t in enumerate((TEXT0, TEXT1, TEXT2))
    ])
    return store, chapter


def _run(answers: dict[str, str], **world: AttributionMethod) -> tuple[Store, sp.SpeakerReport]:
    store, chapter = _world(**world)
    stub = StubProvider()
    stub.register_response("reader", {"lines": [{"tag": t, "speaker": s} for t, s in answers.items()]})
    return store, sp.read_chapter_speakers(store, ModelClient(provider_override=stub), chapter)


def _span(store: Store, block: int) -> Span:
    return next(s for s in store.get_spans("n", 1.0) if s.block_index == block)


def test_named_answer_sets_speaker_and_retypes_crowd_reaction() -> None:
    store, report = _run({"0.0": "Alice", "1.0": "UNKNOWN", "2.0": "UNKNOWN"})
    first = _span(store, 0)
    assert first.speaker_self_id == "n:self:alice"
    assert first.attribution_method is AttributionMethod.CONTEXTUAL_LLM
    # The classifier called this quote a crowd reaction; a named speaker owns it, so it is dialogue.
    assert first.span_type is SpanType.DIALOGUE
    assert report.attributed == 1 and report.retyped == 1


def test_unknown_clears_a_proximity_guess_but_keeps_an_explicit_one() -> None:
    store, report = _run({"0.0": "Alice", "1.0": "UNKNOWN", "2.0": "UNKNOWN"})
    assert _span(store, 2).speaker_self_id is None  # proximity guess "Bob" cleared
    assert report.cleared == 1

    store, report = _run({"0.0": "Alice", "1.0": "UNKNOWN", "2.0": "UNKNOWN"}, first_attribution=AttributionMethod.EXPLICIT)
    assert _span(store, 2).speaker_self_id == "n:self:bob"  # an explicit "X said" survives
    assert report.cleared == 0


def test_a_named_person_the_cast_lacks_is_minted_but_a_place_is_not() -> None:
    store, report = _run({"0.0": "Alice", "1.0": "Carol Wu", "2.0": "Chanis Gate"})
    assert report.minted == 1
    carol = _span(store, 1)
    assert store.get_self(carol.speaker_self_id).canonical_label == "Carol Wu"  # type: ignore[arg-type,union-attr]
    # "Chanis Gate" spoke 18 lines in the old LotM database because a place was typed as a character.
    assert _span(store, 2).speaker_self_id != "n:self:gate"


def test_none_marks_a_non_speech_quote() -> None:
    store, report = _run({"0.0": "NONE", "1.0": "UNKNOWN", "2.0": "UNKNOWN"})
    assert _span(store, 0).speaker_self_id is None
    assert report.not_speech == 1


def test_name_index_resolves_titles_and_unique_words() -> None:
    cast = [sp.CastEntry("a", "Audrey Hall", ["Justice"]), sp.CastEntry("k", "Klein Moretti", ["The Fool"])]
    index = sp.NameIndex(cast)
    assert index.resolve("Miss Justice").self_id == "a"  # type: ignore[union-attr]
    assert index.resolve("Mr. Fool").self_id == "k"  # type: ignore[union-attr]
    assert index.resolve("Audrey").self_id == "a"  # type: ignore[union-attr]
    assert index.resolve("Welch") is None
