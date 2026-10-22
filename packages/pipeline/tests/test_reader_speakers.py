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
TEXT2 = "“Nobody important,” the academy elder muttered."


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


def test_first_person_narrator_is_the_one_others_address_but_narration_rarely_names() -> None:
    """ORV ch2: Yoo Sangah is named in narration constantly; Dokja only inside her quotes. Choosing the most-mentioned
    character picked Sangah and lowered the score (50.7% -> 47.9%)."""
    narration = " ".join("I looked at Sangah and Sangah smiled." for _ in range(15))
    text = narration + ' "Dokja-ssi, what do you read?" "Dokja-ssi, you are so quiet."'
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    chapter = Chapter(novel_id="n", number=1.0, title="T", source_href="a",
                      blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)])
    cast = [sp.CastEntry("s", "Yoo Sangah", ["Sangah"]), sp.CastEntry("d", "Kim Dokja", ["Dokja"])]
    assert sp.first_person_narrator(store, "n", chapter, cast).self_id == "d"  # type: ignore[union-attr]
    third = Chapter(novel_id="n", number=2.0, title="T", source_href="a",
                    blocks=[Block(index=0, block_type=BlockType.PROSE, text="Sangah smiled. \"Dokja.\"")])
    assert sp.first_person_narrator(store, "n", third, cast) is None


def test_an_unnamed_speaker_with_a_role_gets_one_stable_slot() -> None:
    store, report = _run({"0.0": "Alice", "1.0": "UNKNOWN: academy elder", "2.0": "UNKNOWN: The Academy Elder"})
    one, two = _span(store, 1), _span(store, 2)
    assert one.speaker_self_id == two.speaker_self_id == "n:title:academy_elder"  # a persistent title entity
    assert one.attribution_method is AttributionMethod.EPITHET_SLOT
    assert report.role_slots == 2
    assert sp._role_slug("UNKNOWN") == "" and sp._role_slug("UNKNOWN: a guard") == "guard"


def test_dated_written_entries_are_not_speech_and_leave_dialogue() -> None:
    """LotM ch21 quotes Emperor Roselle's diary; the old pipeline voiced nine entries as dialogue."""
    assert sp.looks_written("18th November. Truly a fascinating matter.")
    assert sp.looks_written("1184, 1st January. At the grand New Year Gala")
    assert not sp.looks_written("Hello there.") and not sp.looks_written("I was there on 9th September.")


def test_a_none_answer_retypes_dialogue_to_narration() -> None:
    store, report = _run({"0.0": "Alice", "1.0": "NONE", "2.0": "UNKNOWN"})
    assert _span(store, 1).span_type is SpanType.NARRATION_DESCRIPTION
    assert _span(store, 1).speaker_self_id is None and report.not_speech == 1


def _holder(store: Store, sid: str, name: str, first: int, title_bindings: list[tuple[str, tuple[int, float]]],
            name_learned: int | None = None) -> None:
    from echotales.core.enums import AliasType, AssertedBy, TruthStatus
    from echotales.core.interval import FuzzyInterval
    from echotales.core.models import AliasBinding

    pos = DiscoursePosition(chapter=first, offset=0)
    store.add_self(Self(id=sid, novel_id="n", canonical_label=name, first_attested_pos=pos, prominence=Prominence.RECURRING))

    def bind(alias: str, kind: AliasType, interval: FuzzyInterval, learned: int) -> None:
        store.add_alias_binding("n", AliasBinding(
            alias=alias, alias_type=kind, target_kind=TargetKind.SELF, target_id=sid, interval=interval,
            learned_at_pos=DiscoursePosition(chapter=learned, offset=0), observer_id="reader",
            asserted_by=AssertedBy.INFERENCE, truth_status=TruthStatus.TRUE,
        ))

    for title, (start, end) in title_bindings:
        interval = FuzzyInterval(from_lb=start, from_ub=start, to_lb=end if end != float("inf") else start, to_ub=end)
        bind(title, AliasType.TRANSFERABLE_TITLE, interval, name_learned or first)
    if name_learned:
        bind(name, AliasType.RIGID_NAME, FuzzyInterval.open_ended(name_learned, last_evidence=name_learned), name_learned)


def test_a_title_is_shown_before_its_holders_name_is_known_and_the_name_after() -> None:
    """RI: 'the clan head' for five chapters, named Gu Yue Bo from chapter 6; the title binds back to chapter 1."""
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    _holder(store, "n:self:bo", "Gu Yue Bo", 6, [("the clan head", (1, float("inf")))], name_learned=6)
    early = sp.build_cast(store, "n", "The clan head spoke to the elders.", 1.0)
    assert [e.name for e in early] == ["the clan head"] and early[0].self_id == "n:self:bo"
    assert "Gu Yue Bo" not in early[0].surfaces()  # a name the reader has not learned never reaches an earlier prompt
    late = sp.build_cast(store, "n", "Go against me, Gu Yue Bo! said the clan head.", 7.0)
    assert late[0].name == "Gu Yue Bo" and "the clan head" in late[0].aliases


def test_a_title_follows_its_holder_through_a_handover() -> None:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    _holder(store, "n:self:old", "Old Holder", 1, [("clan leader", (1, 10))], name_learned=1)
    _holder(store, "n:self:new", "New Holder", 12, [("clan leader", (10, float("inf")))], name_learned=12)
    text = "The clan leader spoke."
    assert [e.self_id for e in sp.build_cast(store, "n", text, 5.0)] == ["n:self:old"]
    assert [e.self_id for e in sp.build_cast(store, "n", text, 12.0)] == ["n:self:new"]


def test_one_person_can_hold_several_titles_as_they_advance() -> None:
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    _holder(store, "n:self:li", "Li Wei", 1, [("elder", (1, 20)), ("first elder", (20, float("inf")))], name_learned=1)
    early = sp.build_cast(store, "n", "The elder nodded.", 3.0)[0]
    later = sp.build_cast(store, "n", "The first elder nodded.", 25.0)[0]
    assert early.self_id == later.self_id == "n:self:li"
    assert "elder" in early.aliases and "first elder" not in early.aliases
    assert "first elder" in later.aliases and "elder" not in later.aliases


def test_a_role_made_of_words_the_chapter_never_uses_is_rejected() -> None:
    """The prompt once listed 'the clan head' as an example and the model wrote it into an ORV chapter."""
    store, report = _run({"0.0": "Alice", "1.0": "UNKNOWN: clan head", "2.0": "UNKNOWN"})
    assert report.role_rejected == 1 and report.role_slots == 0
    assert store.get_self("n:title:clan_head") is None


def test_an_honorific_suffix_is_not_a_new_name() -> None:
    """ORV: 'Yoo Sangah-ssi' once became a duplicate entity that later chapters answered with."""
    index = sp.NameIndex([sp.CastEntry("s", "Yoo Sangah", ["Sangah"]), sp.CastEntry("d", "Kim Dokja", ["Dokja"])])
    assert index.resolve("Yoo Sangah-ssi").self_id == "s"  # type: ignore[union-attr]
    assert index.resolve("Dokja-ssi").self_id == "d"  # type: ignore[union-attr]
    assert index.resolve("Soldier-nim") is None


def test_only_offices_become_persistent_title_entities() -> None:
    """ORV gemma2 run: a minted 'dokkaebi' (a creature) later took 12 of the narrator's lines."""
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    assert sp._title_entity(store, "n", 3.0, "academy_elder") == "n:title:academy_elder"
    assert sp._title_entity(store, "n", 3.0, "dokkaebi") == "n:anon:3:dokkaebi"
    assert sp._title_entity(store, "n", 3.0, "old_man") == "n:anon:3:old_man"
    assert store.get_self("n:title:dokkaebi") is None and store.get_self("n:title:academy_elder") is not None
