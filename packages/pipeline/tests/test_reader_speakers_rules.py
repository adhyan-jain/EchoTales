"""Deterministic speaker rules added from the v13 miss analysis (data/scratch/speaker_diag/REPORT.md 6.2, 6.3, 6.5, 6.6)."""

from __future__ import annotations

from echotales.core.enums import AttributionMethod, BlockType, Prominence, SpanType
from echotales.core.models import Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.llm.stub import StubProvider
from echotales.pipeline.reader import speakers_pass as sp


def _run(
    blocks: list[str], answers: dict[str, str], *, names: tuple[str, ...] = ("Alice", "Bob"),
    baseline: dict[int, tuple[str, AttributionMethod]] | None = None,
) -> tuple[Store, sp.SpeakerReport]:
    """One DIALOGUE span per block over its first quote; `baseline` is {block: (self id, method)} before the reader."""
    store = Store(":memory:")
    store.add_novel("n", "N", "x", "epub")
    chapter = Chapter(novel_id="n", number=1.0, title="T", source_href="a",
                      blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(blocks)])
    store.add_chapter(chapter)
    for name in names:
        store.add_self(Self(id=f"n:self:{name.lower()}", novel_id="n", canonical_label=name,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0), prominence=Prominence.RECURRING))
    spans = []
    for i, text in enumerate(blocks):
        close = max(text.find("”"), text.find('"', 1))
        who, how = (baseline or {}).get(i, (None, AttributionMethod.PROXIMAL))
        spans.append(Span(id=f"n:1:{i}:0", novel_id="n", chapter=1.0, block_index=i, start=0, end=close + 1,
                          span_type=SpanType.DIALOGUE, text=text[:close + 1], speaker_self_id=who, attribution_method=how))
    store.add_spans(spans)
    stub = StubProvider()
    stub.register_response("reader", {"lines": [{"tag": t, "speaker": s} for t, s in answers.items()]})
    return store, sp.read_chapter_speakers(store, ModelClient(provider_override=stub), chapter)


def _speaker(store: Store, block: int) -> str | None:
    return next(s for s in store.get_spans("n", 1.0) if s.block_index == block).speaker_self_id


class TestVocativeGuard:
    def test_honorific_suffix_and_a_period_are_still_a_vocative(self) -> None:
        # ORV ch3 b51: "Yoo Sangah-ssi. Isn't that Department Head Han..." is spoken TO Sangah.
        assert sp.addresses("Yoo Sangah-ssi. Isn't that Department Head Han", "Yoo Sangah")
        assert sp.addresses("Sangah-nim, please", "Sangah")

    def test_a_name_inside_a_longer_first_sentence_is_not_a_vocative(self) -> None:
        assert not sp.addresses("Alice. is a name I like", "Alicia")
        assert not sp.addresses("Alice went home. She was tired.", "Alice")
        assert not sp.addresses("Alice and I went home.", "Alice")

    def test_any_surface_of_the_person_counts_not_only_the_display_name(self) -> None:
        store = Store(":memory:")
        entry = sp.CastEntry("d", "Kim Dokja", ["Dokja"])
        assert sp.rejection(store, entry, "Dokja-ssi, what do you read?")[0] == "addressee"
        assert sp.rejection(store, entry, "I read it, Dokja.")[0] == ""


class TestExplicitTagOfTheBlockItselfIsFinal:
    def test_the_model_cannot_overwrite_its_own_block_tag(self) -> None:
        # ORV ch2 b27: baseline EXPLICIT Yoo Sangah, "..." Yoo Sangah replied proudly; the model said Kim Dokja.
        store, report = _run(
            ["“Thank you.” Alice replied proudly, and Bob nodded."], {"0.0": "Bob"},
            baseline={0: ("n:self:alice", AttributionMethod.EXPLICIT)},
        )
        assert _speaker(store, 0) == "n:self:alice"
        assert report.explicit_kept == 1

    def test_an_explicit_tag_borrowed_from_a_neighbour_can_still_be_overridden(self) -> None:
        # ORV ch4 b34/b36: the EXPLICIT row came from the neighbouring paragraph, the block itself names nobody.
        store, report = _run(
            ["“Thank you.”", "Alice sat. Bob stood."], {"0.0": "Bob"},
            baseline={0: ("n:self:alice", AttributionMethod.EXPLICIT)},
        )
        assert _speaker(store, 0) == "n:self:bob"
        assert report.explicit_kept == 0


class TestFirstPersonSaidIsTheNarrator:
    NARRATION = "I am Kim Dokja. " + " ".join("I looked at Alice and Alice smiled." for _ in range(15))

    def _blocks(self, line: str) -> list[str]:
        return [self.NARRATION + ' “Dokja-ssi, what do you read?” “Dokja-ssi, you are quiet.” “Dokja-ssi!”', line]

    def test_i_asked_after_the_quote_is_the_narrator(self) -> None:
        # ORV ch3 b15: `I ... asked, "...Do you know what that is?"` was left unresolved.
        store, report = _run(
            self._blocks("“Do you know what that is?” I asked Alice."), {"1.0": "Alice"}, names=("Alice", "Kim Dokja"),
        )
        assert _speaker(store, 1) == "n:self:kim dokja"
        assert report.first_person == 1

    def test_i_asked_before_the_quote_is_the_narrator(self) -> None:
        store, _ = _run(self._blocks("I turned to her and asked, “Do you know what that is?”"), {"1.0": "Alice"}, names=("Alice", "Kim Dokja"))
        assert _speaker(store, 1) == "n:self:kim dokja"

    def test_i_inside_the_quote_is_not_a_tag(self) -> None:
        store, _ = _run(self._blocks("“I said it already,” Alice sighed."), {"1.0": "Alice"}, names=("Alice", "Kim Dokja"))
        assert _speaker(store, 1) == "n:self:alice"


def test_a_role_written_three_ways_is_one_slot() -> None:
    # RI ch4: the academy elder got a different voice per line when the model wrote the role differently each time.
    store, report = _run(
        ["“One.” the academy elder said.", "“Two.” the elder said.", "“Three.” the elder of the academy said."],
        {"0.0": "UNKNOWN: academy elder", "1.0": "UNKNOWN: elder", "2.0": "UNKNOWN: elder of the academy"},
    )
    ids = {_speaker(store, i) for i in range(3)}
    assert len(ids) == 1 and next(iter(ids)).startswith("n:title:")


class TestRulesAcrossWritingStyles:
    """Owner rule 2026-11-19: a pattern rule decides only when sure; otherwise the model's answer stands. Each style
    below is a place a strict pattern would backfire (19th-century English, translated Chinese, Korean, first person)."""

    def _own(self, name: str, text: str, q: int = 0) -> bool:
        store = Store(":memory:")
        store.add_self(Self(id=f"n:{name}", novel_id="n", canonical_label=name,
                            first_attested_pos=DiscoursePosition(chapter=1, offset=0)))
        return sp.own_explicit_tag(store, f"n:{name}", text, q)

    def test_own_tag_recognises_the_usual_shapes_in_every_style(self) -> None:
        assert self._own("Mr. Bennet", "“What is his name?” said Mr. Bennet.")
        assert self._own("Mr. Bennet", "“What is his name?” replied Mr. Bennet, coldly.")
        assert self._own("Fang Yuan", "Fang Yuan said coldly, “I do not care.”")
        assert self._own("Yoo Sangah", '"Thank you." Yoo Sangah replied proudly.')
        assert self._own("Klein", "“Good evening,” Klein said, bowing.")

    def test_own_tag_defers_when_the_name_is_not_the_subject_of_the_tag(self) -> None:
        assert not self._own("Alice", "“Thanks,” Bob said to Alice.")
        assert not self._own("Mr. Bennet", "“Do you not want to know?” cried his wife impatiently. Mr. Bennet made no answer.")
        assert not self._own("Alice", "“Come here,” he said. Alice sat down.")
        assert not self._own("Fang Yuan", "“Old bastard Fang, stop!” the attackers shouted at Fang Yuan.")
        # LotM ch3/14/21: the name is the listener ("looked at X and said,"), the model was right and the rule was wrong
        assert not self._own("Zhou Mingrui", "She looked at Zhou Mingrui and said, “Remember the bread.”")
        assert not self._own("Klein", "Her emerald eyes smiled at Klein as she said, “Help me.”")
        assert not self._own("Old Neil", "he handed it over to Old Neil and thoughtlessly asked, “Is that all?”")
        assert self._own("Daly", "Seated across him, Daly laughed and said, “Fine.”")

    def test_first_person_tag_is_only_a_tag_outside_the_quote(self) -> None:
        assert sp.first_person_tag('"Do you know what that is?" I asked.', 0)
        assert sp.first_person_tag('I turned and asked, "Do you know what that is?"', 0)
        assert not sp.first_person_tag('"I asked him already," Alice said.', 0)
        assert not sp.first_person_tag('"Come in," he said. I asked, "Why?"', 0)
        assert not sp.first_person_tag("“Mr. Bennet,” said she, “I have told you.”", 0)

    def test_a_bare_name_with_a_full_stop_is_not_called_a_vocative(self) -> None:
        assert not sp.addresses("Fang Yuan. That is who I am.", "Fang Yuan")
        assert not sp.addresses("Elizabeth.", "Elizabeth")
        assert sp.addresses("Elizabeth, my dear,", "Elizabeth")
        assert sp.addresses("Dokja-ssi. Are you there?", "Dokja")


def test_a_first_person_narrator_is_carried_to_a_chapter_that_never_names_him() -> None:
    # ORV ch3: Kim Dokja is not in the chapter's cast at all; ch2 identified him, and the "I" is the same person.
    store = Store(":memory:")
    first = Chapter(novel_id="carry", number=1.0, title="T", source_href="a", blocks=[Block(
        index=0, block_type=BlockType.PROSE,
        text=" ".join("I looked at Sangah and Sangah smiled." for _ in range(15)) + ' "Dokja-ssi, what do you read?" "Dokja-ssi, you are quiet."')])
    second = Chapter(novel_id="carry", number=2.0, title="T", source_href="a", blocks=[Block(
        index=0, block_type=BlockType.PROSE, text=" ".join("I walked home alone." for _ in range(15)))])
    third = Chapter(novel_id="carry", number=3.0, title="T", source_href="a", blocks=[Block(
        index=0, block_type=BlockType.PROSE, text="Sangah walked home. She did not speak.")])
    cast = [sp.CastEntry("s", "Yoo Sangah", ["Sangah"]), sp.CastEntry("d", "Kim Dokja", ["Dokja"])]
    assert sp.narrator_for(store, "carry", first, list(cast)).self_id == "d"  # type: ignore[union-attr]
    later_cast = [cast[0]]
    carried = sp.narrator_for(store, "carry", second, later_cast)
    assert carried is not None and carried.self_id == "d" and any(e.self_id == "d" for e in later_cast)
    assert sp.narrator_for(store, "carry", third, [cast[0]]) is None  # third person: no narrator, whatever was carried


class TestPromptContext:
    def test_a_window_shows_only_people_introduced_so_far_but_always_the_narrator(self) -> None:
        cast = [sp.CastEntry("a", "Alice"), sp.CastEntry("h", "Han Myungoh", ["Han"]), sp.CastEntry("d", "Kim Dokja", ["Dokja"])]
        shown = sp.scene_cast(cast, "#0: Alice walked in. “Hello.”", narrator=cast[2])
        assert [e.name for e in shown] == ["Alice", "Kim Dokja"]
        later = sp.scene_cast(cast, "#0: Alice walked in.\n#9: Han Myungoh stood up.", narrator=None)
        assert [e.name for e in later] == ["Alice", "Han Myungoh"]
        assert sp.scene_cast(cast, "nobody here", narrator=None) == cast  # never an empty list

    def test_the_turn_note_names_the_last_speakers_and_is_empty_before_the_first_window(self) -> None:
        assert sp.turn_note([]) == "" and sp.turn_note(["", ""]) == ""
        note = sp.turn_note(["Kim Dokja", "UNKNOWN", "Yoo Sangah"])
        assert "Kim Dokja, an unnamed speaker, Yoo Sangah" in note

    def test_the_prompt_carries_the_crowd_and_listener_rules(self) -> None:
        prompt = sp._prompt([sp.CastEntry("a", "Alice")], "#0: [0.0]“Hi.”", ["0.0"])
        assert "UNKNOWN even when a listed person stands nearby" in prompt and "spoken TO" in prompt


def test_two_different_ranks_are_not_merged() -> None:
    store, _ = _run(
        ["“One.” the first elder said.", "“Two.” the second elder said."],
        {"0.0": "UNKNOWN: first elder", "1.0": "UNKNOWN: second elder"},
    )
    assert _speaker(store, 0) != _speaker(store, 1)


class TestAnswerThatIsADescriptionNotAName:
    """RI ch4/ch5 (v16 trace): the model wrote "The elder", "the academy elder", "third Gu" with no UNKNOWN: prefix. Not a name
    in the cast, so the line was left "unmapped" with its baseline guess (a named wrong person for 2 of 7 elder lines)."""

    def test_a_described_office_becomes_the_role_slot(self) -> None:
        store, report = _run(
            ["“Come here.” The academy elder waved.", "“Next.” The elder frowned."],
            {"0.0": "the academy elder", "1.0": "The elder"},
            baseline={0: ("n:self:bob", AttributionMethod.PROXIMAL)},
        )
        assert _speaker(store, 0) == "n:title:academy_elder"
        assert _speaker(store, 1) == "n:title:academy_elder"  # merged with the longer wording of the same role
        assert report.role_slots == 2

    def test_a_described_non_office_is_an_anonymous_slot(self) -> None:
        store, _ = _run(["“Take me up.” The third Gu spoke."], {"0.0": "third Gu"})
        assert _speaker(store, 0) == "n:anon:1:third_gu"

    def test_a_description_that_is_not_in_the_chapter_is_not_trusted(self) -> None:
        store, report = _run(["“Hello.” Alice smiled."], {"0.0": "the wise old sage"},
                             baseline={0: ("n:self:bob", AttributionMethod.PROXIMAL)})
        assert _speaker(store, 0) is None and report.role_rejected == 1

    def test_a_bare_pronoun_is_left_to_the_baseline(self) -> None:
        store, _ = _run(["“Hello.” Alice smiled."], {"0.0": "she"},
                        baseline={0: ("n:self:alice", AttributionMethod.EXPLICIT)})
        assert _speaker(store, 0) == "n:self:alice"

    def test_a_long_phrase_is_not_a_name_because_it_contains_one(self) -> None:
        # RI ch5 b25: "Many elders watching Fang Yuan in the dark" resolved to Fang Yuan by the unique-word fallback.
        store, _ = _run(["“It is lesser.” Many elders watched Alice in the dark."],
                        {"0.0": "Many elders watching Alice in the dark"})
        assert _speaker(store, 0) != "n:self:alice"


class TestUnknownOverABorrowedExplicitTag:
    """ORV ch4 b34/b36: the baseline's EXPLICIT Lee Hyunsung came from the neighbouring paragraph; the model said UNKNOWN and the
    old code kept the borrowed name because EXPLICIT always survived an UNKNOWN."""

    def test_the_model_unknown_clears_an_explicit_name_that_is_not_in_the_block(self) -> None:
        store, _ = _run(["“Why are you taking control?”", "Alice explained."], {"0.0": "UNKNOWN"},
                        baseline={0: ("n:self:alice", AttributionMethod.EXPLICIT)})
        assert _speaker(store, 0) is None

    def test_an_explicit_name_that_is_in_the_block_survives_unknown(self) -> None:
        store, _ = _run(["“Why are you taking control?” Bob looked at Alice."], {"0.0": "UNKNOWN"},
                        baseline={0: ("n:self:alice", AttributionMethod.EXPLICIT)})
        assert _speaker(store, 0) == "n:self:alice"
