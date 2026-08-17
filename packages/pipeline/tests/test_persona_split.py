"""Body changes: detection, epochs, and position-keyed persona lookup.

Every regex case here is a sentence taken from the corpus rather than
invented -- the cue vocabulary in `split.py` exists because the first draft
of a cue list written from imagination (§4.24's combat verbs) scored zero on
real chapters, and a test suite written the same way would have hidden that.
"""

from __future__ import annotations

from echotales.core.enums import (
    AliasType,
    BlockType,
    ReferenceMode,
    SpanType,
    TargetKind,
)
from echotales.core.models import (
    Block,
    Chapter,
    DiscoursePosition,
    Mention,
    Self,
    Span,
)
from echotales.core.store import Store
from echotales.pipeline.persona.split import (
    BodyChange,
    SplitReport,
    bodies_of,
    detect_body_changes,
    epochs_for,
    find_change_candidates,
    is_split,
    persona_at,
    split_selves,
    write_epochs,
)

# Verbatim from Reverend Insanity chapter 1 -- the moment the whole
# self/persona split exists for.
RI_CH1_CUE = "In short, it is the ability to be reborn."
RI_CH1_NEXT = (
    "With the use of the Spring Autumn Cicada I have been reborn, "
    "going back to the time of 500 years ago!"
)


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    return store


def _self(store: Store, entity_id: str = "t:self1", label: str = "Fang Yuan") -> Self:
    entity = Self(
        id=entity_id,
        novel_id="t",
        canonical_label=label,
        first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
    )
    store.add_self(entity)
    return entity


def _chapter(store: Store, number: float, texts: list[str]) -> None:
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=number,
            title=f"ch{number:g}",
            source_href=f"{number:g}.html",
            blocks=[
                Block(index=i, block_type=BlockType.PROSE, text=t)
                for i, t in enumerate(texts)
            ],
        )
    )


def _spans(
    store: Store,
    number: float,
    texts: list[str],
    *,
    span_type: SpanType = SpanType.NARRATION_DESCRIPTION,
    speaker: str | None = None,
) -> None:
    store.add_spans(
        [
            Span(
                id=f"s{number:g}-{i}",
                novel_id="t",
                chapter=number,
                block_index=i,
                start=0,
                end=len(t),
                text=t,
                span_type=span_type,
                speaker_self_id=speaker,
            )
            for i, t in enumerate(texts)
        ]
    )


def _mention(
    store: Store,
    number: float,
    block_index: int,
    *,
    text: str = "Fang Yuan",
    target_id: str = "t:self1",
    mode: ReferenceMode = ReferenceMode.PRESENT,
) -> None:
    store.add_mentions(
        [
            Mention(
                id=f"m{number:g}-{block_index}-{text}",
                novel_id="t",
                segment_id="s",
                chapter=number,
                offset=0,
                block_index=block_index,
                text=text,
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION,
                reference_mode=mode,
                target_kind=TargetKind.SELF,
                target_id=target_id,
            )
        ]
    )


class TestCueDetection:
    def test_ri_chapter_one_rebirth_is_found(self, tmp_path) -> None:
        """The worked example. This is the case the module exists for."""
        store = _store(tmp_path)
        _self(store)
        for ch in (1.0, 2.0, 3.0):
            texts = ["He walked.", RI_CH1_CUE if ch == 1.0 else "Later.", "After."]
            _chapter(store, ch, texts)
            _spans(store, ch, texts)
            _mention(store, ch, 0)
        store.conn.commit()

        found = find_change_candidates(store, "t", "t:self1")
        assert [c.chapter for c in found] == [1.0]
        assert found[0].kind == "rebirth"
        store.close()

    def test_first_person_dialogue_counts_when_the_speaker_matches(
        self, tmp_path
    ) -> None:
        """Fang Yuan *says* he has been reborn, and that is the clearest
        statement in the chapter -- narration-only detection missed it."""
        store = _store(tmp_path)
        _self(store)
        for ch in (1.0, 2.0, 3.0):
            texts = ["Quiet.", RI_CH1_NEXT if ch == 1.0 else "Later.", "After."]
            _chapter(store, ch, texts)
            _spans(store, ch, texts, span_type=SpanType.DIALOGUE, speaker="Fang Yuan")
            _mention(store, ch, 0)
        store.conn.commit()

        found = find_change_candidates(store, "t", "t:self1")
        assert [c.chapter for c in found] == [1.0]
        store.close()

    def test_someone_elses_line_does_not_give_them_a_body(self, tmp_path) -> None:
        """Same sentence, a different speaker: no candidate."""
        store = _store(tmp_path)
        _self(store)
        for ch in (1.0, 2.0, 3.0):
            texts = ["Quiet.", RI_CH1_NEXT if ch == 1.0 else "Later.", "After."]
            _chapter(store, ch, texts)
            _spans(store, ch, texts, span_type=SpanType.DIALOGUE, speaker="Shen Cui")
            _mention(store, ch, 0)
        store.conn.commit()

        assert find_change_candidates(store, "t", "t:self1") == []
        store.close()

    def test_passage_naming_another_character_is_about_them(self, tmp_path) -> None:
        """RI ch109's "Fang Yuan's rebirth changed his current situation"
        produced a candidate for every bystander in the block before this
        guard existed."""
        store = _store(tmp_path)
        _self(store)
        _self(store, "t:self2", "Jia Fu")
        for ch in (1.0, 2.0, 3.0):
            texts = [
                "A room.",
                "Fang Yuan's rebirth changed his current situation."
                if ch == 1.0
                else "Later.",
                "After.",
            ]
            _chapter(store, ch, texts)
            _spans(store, ch, texts)
            _mention(store, ch, 0, text="Jia Fu", target_id="t:self2")
        store.conn.commit()

        assert find_change_candidates(store, "t", "t:self2") == []
        store.close()

    def test_a_recalled_rebirth_is_an_echo_not_a_second_body(self, tmp_path) -> None:
        """Fang Yuan refers back to his rebirth in chapters 2, 19, 71, 105,
        135, 145, 187 and 198. A distance window alone gave him eight
        bodies, which is why a repeat of an already-accepted *kind* is
        folded no matter how far away it is."""
        store = _store(tmp_path)
        _self(store)
        for ch in (1.0, 2.0, 40.0, 80.0, 100.0):
            texts = ["He walked.", RI_CH1_CUE if ch < 100.0 else "Rain fell.", "After."]
            _chapter(store, ch, texts)
            _spans(store, ch, texts)
            _mention(store, ch, 0)
        store.conn.commit()

        report = SplitReport(novel_id="t")
        found = find_change_candidates(store, "t", "t:self1", report=report)
        assert [c.chapter for c in found] == [1.0]
        assert report.echoes_folded == 3
        store.close()

    def test_no_cue_means_no_candidate(self, tmp_path) -> None:
        """The overwhelmingly common case: one body, and the stage must not
        invent a second."""
        store = _store(tmp_path)
        _self(store)
        for ch in (1.0, 2.0):
            texts = ["He walked.", "He drew his blade.", "Rain fell."]
            _chapter(store, ch, texts)
            _spans(store, ch, texts)
            _mention(store, ch, 0)
        store.conn.commit()

        assert find_change_candidates(store, "t", "t:self1") == []
        store.close()

    def test_a_trance_is_not_a_body_change(self, tmp_path) -> None:
        """LOTM ch126: "his mind, body, and soul suddenly entered a magical
        state" matched the first soul-transfer pattern, and the model agreed
        with it. The regex now requires a destination body."""
        store = _store(tmp_path)
        _self(store)
        for ch in (1.0, 2.0, 3.0):
            texts = [
                "He sighed.",
                "His mind, body, and soul suddenly entered a magical state.",
                "After.",
            ]
            _chapter(store, ch, texts)
            _spans(store, ch, texts)
            _mention(store, ch, 0)
        store.conn.commit()

        assert find_change_candidates(store, "t", "t:self1") == []
        store.close()


class _StubClient:
    """Confirms or vetoes, and records what it was asked."""

    def __init__(self, verdicts: list[bool], label: str = "") -> None:
        self.verdicts = list(verdicts)
        self.label = label
        self.prompts: list[str] = []

    def complete(self, task, prompt, schema, *, system="", novel_id=""):  # type: ignore[no-untyped-def]
        from types import SimpleNamespace

        self.prompts.append(prompt)
        changed = self.verdicts.pop(0) if self.verdicts else False
        return SimpleNamespace(
            value=schema(
                changed=changed,
                kind="rebirth",
                new_body_label=self.label,
                reason="",
            )
        )


class TestModelVeto:
    def _seed(self, tmp_path):  # type: ignore[no-untyped-def]
        store = _store(tmp_path)
        entity = _self(store)
        for ch in (1.0, 2.0, 3.0):
            texts = ["He walked.", RI_CH1_CUE if ch == 1.0 else "Later.", "After."]
            _chapter(store, ch, texts)
            _spans(store, ch, texts)
            _mention(store, ch, 0)
        store.conn.commit()
        return store, entity

    def test_veto_discards_the_candidate(self, tmp_path) -> None:
        store, entity = self._seed(tmp_path)
        report = SplitReport(novel_id="t")
        client = _StubClient([False])
        assert detect_body_changes(store, "t", entity, client=client, report=report) == []
        assert report.vetoed_by_model == 1
        store.close()

    def test_confirmation_keeps_it_and_records_the_label(self, tmp_path) -> None:
        store, entity = self._seed(tmp_path)
        client = _StubClient([True], label="Fang Yuan, age 15")
        changes = detect_body_changes(store, "t", entity, client=client)
        assert len(changes) == 1
        assert changes[0].new_body_label == "Fang Yuan, age 15"
        assert changes[0].source == "llm"
        store.close()

    def test_a_sentence_is_not_a_body_label(self, tmp_path) -> None:
        """A model asked for a name sometimes returns a reason. Anything that
        reads as prose is dropped rather than becoming a persona's name."""
        store, entity = self._seed(tmp_path)
        client = _StubClient(
            [True], label="He was reborn into his fifteen-year-old body."
        )
        changes = detect_body_changes(store, "t", entity, client=client)
        assert changes[0].new_body_label == ""
        store.close()

    def test_no_client_keeps_the_lexical_candidate(self, tmp_path) -> None:
        """`--no-llm` still splits, and says so through `source`."""
        store, entity = self._seed(tmp_path)
        changes = detect_body_changes(store, "t", entity, client=None)
        assert [c.source for c in changes] == ["lexicon"]
        store.close()

    def test_the_prompt_carries_neighbouring_blocks(self, tmp_path) -> None:
        """The matched sentence alone ("it is the ability to be reborn") is
        not enough to judge; the next block is what settles it."""
        store, entity = self._seed(tmp_path)
        client = _StubClient([True])
        detect_body_changes(store, "t", entity, client=client)
        assert "He walked." in client.prompts[0]
        store.close()


class TestEpochs:
    def test_no_change_is_one_open_epoch(self, tmp_path) -> None:
        epochs = epochs_for("t:self1", "Fang Yuan", 1.0, [])
        assert len(epochs) == 1
        assert epochs[0].persona_id == "t:self1:body1"
        assert epochs[0].to_pos is None

    def test_a_change_splits_into_two_contiguous_epochs(self) -> None:
        change = BodyChange(
            chapter=1.0,
            block_index=82,
            story_pos=1.89,
            kind="rebirth",
            cue="reborn",
            passage=RI_CH1_CUE,
        )
        epochs = epochs_for("t:self1", "Fang Yuan", 1.0, [change], last_pos=199.0)
        assert [e.persona_id for e in epochs] == ["t:self1:body1", "t:self1:body2"]
        # Contiguous and half-open: the first ends exactly where the second
        # begins, so no position falls in both or in neither.
        assert epochs[0].to_pos == 1.89
        assert epochs[1].from_pos == 1.89
        assert epochs[1].cause == "rebirth"

    def test_the_new_label_carries_into_the_later_body(self) -> None:
        change = BodyChange(
            chapter=1.0,
            block_index=82,
            story_pos=1.89,
            kind="rebirth",
            cue="reborn",
            passage="",
            new_body_label="Fang Yuan, age 15",
        )
        epochs = epochs_for("t:self1", "Fang Yuan", 1.0, [change])
        assert epochs[0].body_label == "Fang Yuan"
        assert "Fang Yuan, age 15" in epochs[1].body_label

    def test_a_change_before_the_first_sighting_is_ignored(self) -> None:
        """A cue dated earlier than the character's own first attestation
        would produce an interval that ends before it starts."""
        change = BodyChange(
            chapter=1.0,
            block_index=0,
            story_pos=1.0,
            kind="rebirth",
            cue="reborn",
            passage="",
        )
        epochs = epochs_for("t:self1", "Fang Yuan", 5.0, [change])
        assert len(epochs) == 1


class TestPerBodyCanon:
    """The reader-supplied half. Extraction cannot describe a body the prose
    never describes, and RI's narration describes Fang Yuan's death scene and
    little else -- so what the fifteen-year-old looks like is written down by
    someone who read the book, per `canon.py`'s own argument."""

    def test_bodies_get_different_appearances(self) -> None:
        from echotales.pipeline.persona.canon import canon_for

        first = canon_for("reverend-insanity", "Fang Yuan", "x:self1:body1")
        second = canon_for("reverend-insanity", "Fang Yuan", "x:self1:body2")
        assert first["height_build"] != second["height_build"]
        # Body-independent identity survives into both.
        assert first["hair_color"] == second["hair_color"] == "midnight black"

    def test_a_character_without_body_entries_is_unaffected(self) -> None:
        """Body layering changes nothing for a character with no body entry.

        Asserted as "same as with no persona id" rather than "empty": since
        `wiki_canon.py`, a character with no hand-authored entry can still
        have imported wiki traits, and this test is about body layering.
        """
        from echotales.pipeline.persona.canon import CANON_BY_BODY, canon_for

        assert "Shen Cui" not in CANON_BY_BODY.get("reverend-insanity", {})
        assert canon_for("reverend-insanity", "Shen Cui", "x:self2:body1") == canon_for(
            "reverend-insanity", "Shen Cui"
        )

    def test_no_persona_id_keeps_the_old_behaviour(self) -> None:
        """Every existing caller passed a label only, and must keep getting
        the character-level entry."""
        from echotales.pipeline.persona.canon import canon_for

        base = canon_for("reverend-insanity", "Fang Yuan")
        assert "height_build" in base and "gaunt" not in base["height_build"]


class TestPersonaAt:
    def _written(self, tmp_path):  # type: ignore[no-untyped-def]
        store = _store(tmp_path)
        entity = _self(store)
        change = BodyChange(
            chapter=1.0,
            block_index=82,
            story_pos=1.89,
            kind="rebirth",
            cue="reborn",
            passage=RI_CH1_CUE,
        )
        epochs = epochs_for("t:self1", "Fang Yuan", 1.0, [change], last_pos=199.0)
        write_epochs(store, "t", entity, epochs, observer_id="reader")
        store.conn.commit()
        return store

    def test_the_right_body_at_each_position(self, tmp_path) -> None:
        """The demonstration: chapter 1 is the 500-year-old, chapter 20 is
        the fifteen-year-old, and nothing about the query changed but the
        position."""
        store = self._written(tmp_path)
        assert persona_at(store, "t:self1", 1.0) == "t:self1:body1"
        assert persona_at(store, "t:self1", 20.0) == "t:self1:body2"
        assert persona_at(store, "t:self1", 199.0) == "t:self1:body2"
        store.close()

    def test_the_boundary_belongs_to_the_new_body(self, tmp_path) -> None:
        """Half-open intervals: the change position is the first moment of
        the new body, not the last of the old one."""
        store = self._written(tmp_path)
        assert persona_at(store, "t:self1", 1.89) == "t:self1:body2"
        assert persona_at(store, "t:self1", 1.88) == "t:self1:body1"
        store.close()

    def test_no_position_means_the_latest_body(self, tmp_path) -> None:
        store = self._written(tmp_path)
        assert persona_at(store, "t:self1") == "t:self1:body2"
        store.close()

    def test_before_the_character_exists_returns_their_first_body(
        self, tmp_path
    ) -> None:
        """Returning nothing would make a caller invent a persona id."""
        store = self._written(tmp_path)
        assert persona_at(store, "t:self1", 0.5) == "t:self1:body1"
        store.close()

    def test_an_ungraphed_self_still_resolves(self, tmp_path) -> None:
        """Every database built before this module existed has no bindings.
        They must keep working, unsplit."""
        store = _store(tmp_path)
        assert persona_at(store, "t:self9", 4.0) == "t:self9:body1"
        store.close()

    def test_bodies_and_split_reporting(self, tmp_path) -> None:
        store = self._written(tmp_path)
        assert len(bodies_of(store, "t:self1")) == 2
        assert is_split(store, "t:self1")
        assert split_selves(store, "t") == {"t:self1": ["t:self1:body1", "t:self1:body2"]}
        store.close()

    def test_rebuilding_does_not_double_the_bindings(self, tmp_path) -> None:
        """Bindings are a plain INSERT because one self legitimately has
        several, so a second persona run would otherwise bind each body
        twice."""
        store = self._written(tmp_path)
        entity = store.get_self("t:self1")
        epochs = epochs_for("t:self1", "Fang Yuan", 1.0, [])
        store.clear_self_persona_bindings("t:self1")
        write_epochs(store, "t", entity, epochs, observer_id="reader")
        store.conn.commit()
        assert len(bodies_of(store, "t:self1")) == 1
        store.close()
