"""Tests for the corrections apply path: anon-slot reassignment and
create_mention, the two new correction capabilities added this session."""

from __future__ import annotations

from echotales.core.enums import AttributionMethod, BlockType, ReferenceMode, SpanType
from echotales.core.models import Block, Chapter, DiscoursePosition, Self, Span
from echotales.core.store import Store
from echotales.pipeline.corrections import Correction, CorrectionLog, CorrectionType, apply_pending


def _store_with_span(text: str = '"Old bastard Fang, stop resisting."') -> Store:
    store = Store(":memory:")
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
        )
    )
    store.add_spans(
        [
            Span(
                id="t:1:0:0",
                novel_id="t",
                chapter=1.0,
                block_index=0,
                start=0,
                end=len(text),
                span_type=SpanType.DIALOGUE,
                text=text,
                attribution_method=AttributionMethod.UNRESOLVED,
            )
        ]
    )
    store.add_self(
        Self(
            id="t:self1",
            novel_id="t",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1, offset=0),
        )
    )
    store.conn.commit()
    return store


class TestAnonSlotReassignment:
    def test_assigns_a_named_anon_slot(self, tmp_path) -> None:
        store = _store_with_span()
        log = CorrectionLog(tmp_path / "t.jsonl")
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.REASSIGN_SPEAKER,
                payload={"span_id": "t:1:0:0", "chapter": 1.0, "anon_slot": 2},
            )
        )
        result = apply_pending(store, log)
        assert result["count"] == 1

        span = store.get_spans("t", 1.0)[0]
        assert span.speaker_self_id == "t:anon:1:2"
        assert span.attribution_method is AttributionMethod.ANONYMOUS_SLOT

    def test_anon_slot_beats_stale_null_speaker_id(self, tmp_path) -> None:
        """anon_slot takes the branch even though speaker_id is absent/null,
        the same payload shape a "clear to unattributed" correction has."""
        store = _store_with_span()
        log = CorrectionLog(tmp_path / "t.jsonl")
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.REASSIGN_SPEAKER,
                payload={
                    "span_id": "t:1:0:0",
                    "chapter": 1.0,
                    "speaker_id": None,
                    "new_label": None,
                    "anon_slot": 1,
                },
            )
        )
        apply_pending(store, log)
        span = store.get_spans("t", 1.0)[0]
        assert span.speaker_self_id == "t:anon:1:1"
        assert span.attribution_method is AttributionMethod.ANONYMOUS_SLOT


class TestCreateMention:
    def test_creates_a_mention_on_existing_entity(self, tmp_path) -> None:
        text = '"Old bastard Fang, stop resisting."'
        store = _store_with_span(text)
        local_start = text.index("Old bastard Fang")
        local_end = local_start + len("Old bastard Fang")
        log = CorrectionLog(tmp_path / "t.jsonl")
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.CREATE_MENTION,
                payload={
                    "span_id": "t:1:0:0",
                    "chapter": 1.0,
                    "local_start": local_start,
                    "local_end": local_end,
                    "target_id": "t:self1",
                },
            )
        )
        result = apply_pending(store, log)
        assert result["count"] == 1

        mentions = store.get_mentions("t", 1.0)
        assert len(mentions) == 1
        m = mentions[0]
        assert m.text == "Old bastard Fang"
        assert m.target_id == "t:self1"
        assert m.offset == local_start  # span.start is 0 here
        assert m.reference_mode is ReferenceMode.DIALOGUE_REFERENCE

    def test_creates_a_new_entity_from_selected_text(self, tmp_path) -> None:
        text = '"Old bastard Fang, stop resisting."'
        store = _store_with_span(text)
        local_start = text.index("Old bastard Fang")
        local_end = local_start + len("Old bastard Fang")
        log = CorrectionLog(tmp_path / "t.jsonl")
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.CREATE_MENTION,
                payload={
                    "span_id": "t:1:0:0",
                    "chapter": 1.0,
                    "local_start": local_start,
                    "local_end": local_end,
                    "new_label": "Fang Yuan (insult)",
                },
            )
        )
        result = apply_pending(store, log)
        assert result["count"] == 1
        mentions = store.get_mentions("t", 1.0)
        assert len(mentions) == 1
        assert mentions[0].target_id is not None
        assert mentions[0].target_id != "t:self1"  # a fresh manual entity, not the existing one

    def test_out_of_range_offset_errors_without_crashing(self, tmp_path) -> None:
        store = _store_with_span()
        log = CorrectionLog(tmp_path / "t.jsonl")
        log.add(
            Correction(
                novel_id="t",
                type=CorrectionType.CREATE_MENTION,
                payload={
                    "span_id": "t:1:0:0",
                    "chapter": 1.0,
                    "local_start": 0,
                    "local_end": 9999,
                    "target_id": "t:self1",
                },
            )
        )
        result = apply_pending(store, log)
        assert result["count"] == 0
        assert store.get_mentions("t", 1.0) == []
