"""Fix 6: narrator reveal patterns ("It was Fang Yuan of course").

The resolver links mentions from surface forms already in the text and does
not read this rhetorical move; `detect_reveals` is a strictly additive
stage on top of it -- it only ever appends `ResolutionEvent` rows for
`OBSERVER_READER`, never touches a `Mention`, and defines no new schema.
"""

from __future__ import annotations

from echotales.core.enums import (
    AliasType,
    EventType,
    ReferenceMode,
    SpanType,
    TargetKind,
)
from echotales.core.models import (
    Block,
    BlockType,
    Chapter,
    DiscoursePosition,
    Mention,
    Self,
    Span,
)
from echotales.core.store import Store
from echotales.pipeline.resolve.detect_reveals import (
    REVEAL_EVENT_KIND,
    detect_reveals,
    find_reveals,
    reveal_target_for_block,
)


def _store(tmp_path, narration_text: str) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text=narration_text)],
        )
    )
    store.add_self(
        Self(
            id="t:self1",
            novel_id="t",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
            kind=TargetKind.SELF,
        )
    )
    store.add_spans(
        [
            Span(
                id="sp0",
                novel_id="t",
                chapter=1.0,
                block_index=0,
                start=0,
                end=len(narration_text),
                span_type=SpanType.NARRATION_DESCRIPTION,
                text=narration_text,
            )
        ]
    )
    store.add_mentions(
        [
            Mention(
                id="m0",
                novel_id="t",
                segment_id="s",
                chapter=1.0,
                offset=0,
                block_index=0,
                text="Fang Yuan",
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_DESCRIPTION,
                reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF,
                target_id="t:self1",
            )
        ]
    )
    store.conn.commit()
    return store


class TestFindReveals:
    def test_matches_each_pattern_shape(self, tmp_path) -> None:
        cases = [
            "It was Fang Yuan of course, standing at the gate.",
            "This was none other than Fang Yuan.",
            "None other than Fang Yuan walked out of the shadows.",
            "Who else could it be but Fang Yuan, grinning as always.",
            "As it turned out, it was Fang Yuan behind the mask.",
            "The person was in fact Fang Yuan, disguised as an elder.",
        ]
        for text in cases:
            store = _store(tmp_path, text)
            reveals = find_reveals(store, "t")
            assert len(reveals) == 1, text
            assert reveals[0].target_id == "t:self1"

    def test_dialogue_is_not_a_reveal_source(self, tmp_path) -> None:
        """A character's own guess about someone's identity is a claim, not
        the narrator handing the reader a fact -- same discipline appearance
        extraction applies to narration vs. dialogue."""
        store = Store(str(tmp_path / "t.db"))
        store.add_novel("t", "T", "x.epub", "generic")
        store.add_chapter(
            Chapter(
                novel_id="t",
                number=1.0,
                title="T",
                source_href="a.html",
                blocks=[Block(index=0, block_type=BlockType.DIALOGUE, text='"It was Fang Yuan of course!"')],
            )
        )
        store.add_self(
            Self(
                id="t:self1",
                novel_id="t",
                canonical_label="Fang Yuan",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.SELF,
            )
        )
        store.add_spans(
            [
                Span(
                    id="sp0",
                    novel_id="t",
                    chapter=1.0,
                    block_index=0,
                    start=0,
                    end=29,
                    span_type=SpanType.DIALOGUE,
                    text='"It was Fang Yuan of course!"',
                )
            ]
        )
        store.conn.commit()
        assert find_reveals(store, "t") == []

    def test_unresolvable_name_is_not_reported(self, tmp_path) -> None:
        """A name that names no known character is not a reveal this stage
        can act on -- it is silently absent from `find_reveals`'s output,
        and `detect_reveals` counts it under `unresolved_name` instead."""
        store = _store(tmp_path, "It was Some Stranger of course.")
        assert find_reveals(store, "t") == []


class TestDetectReveals:
    def test_logs_a_resolution_event_for_the_reader(self, tmp_path) -> None:
        store = _store(tmp_path, "This was none other than Fang Yuan.")
        report = detect_reveals(store, "t")

        assert report.resolved == 1
        events = [
            e
            for e in store.iter_events()
            if e.type is EventType.LINK and e.payload.get("kind") == REVEAL_EVENT_KIND
        ]
        assert len(events) == 1
        event = events[0]
        assert event.payload["target_id"] == "t:self1"
        assert event.payload["observer_id"] == "READER"
        assert event.payload["chapter"] == 1.0
        assert event.payload["block_index"] == 0
        assert event.method.value == "DECLARATION"

    def test_rerunning_does_not_duplicate_the_event(self, tmp_path) -> None:
        store = _store(tmp_path, "This was none other than Fang Yuan.")
        detect_reveals(store, "t")
        again = detect_reveals(store, "t")

        assert again.already_logged == 1
        assert again.resolved == 0
        events = [
            e
            for e in store.iter_events()
            if e.type is EventType.LINK and e.payload.get("kind") == REVEAL_EVENT_KIND
        ]
        assert len(events) == 1

    def test_reveal_target_for_block_is_scoped_to_the_exact_block(self, tmp_path) -> None:
        """Same discipline as `get_panel_cast`'s block-scoped presence: a
        reveal three blocks away describes what the reader knows generally,
        not who is in *this* frame."""
        store = _store(tmp_path, "This was none other than Fang Yuan.")
        detect_reveals(store, "t")

        assert reveal_target_for_block(store, "t", 1.0, 0) == "t:self1"
        assert reveal_target_for_block(store, "t", 1.0, 1) is None
        assert reveal_target_for_block(store, "t", 2.0, 0) is None
