"""Who witnessed a reveal (COMPLETION_PLAN Track 4 item 16, EVOLUTION 4.80)."""

from __future__ import annotations

import pytest
from echotales.core.enums import AliasType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import (
    Chapter,
    DiscoursePosition,
    Mention,
    NarrativeSegment,
    Self,
    Span,
)
from echotales.core.readset import fact_ref, normalize
from echotales.core.store import Store
from echotales.pipeline.resolve.detect_observations import (
    detect_observations,
    reveal_fact_ref,
)

REVEAL_TEXT = "The masked figure was none other than Fang Yuan."
TARGET = "n:self:fangyuan"
WITNESS = "n:self:bystander"


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    s = Store(str(tmp_path / "r.db"))
    s.add_novel("n", "N", "", "")
    for entity_id, label in ((TARGET, "Fang Yuan"), (WITNESS, "Gu Yue Bo")):
        s.add_self(
            Self(
                id=entity_id,
                novel_id="n",
                canonical_label=label,
                first_attested_pos=DiscoursePosition(chapter=1),
            )
        )
    s.add_chapter(
        Chapter(
            novel_id="n",
            number=1.0,
            title="One",
            source_href="one.html",
            blocks=[
                {"index": 0, "block_type": "PROSE", "text": "Gu Yue Bo watched."},
                {"index": 1, "block_type": "PROSE", "text": REVEAL_TEXT},
            ],
        )
    )
    s.add_spans(
        [
            Span(
                id="sp1",
                novel_id="n",
                chapter=1.0,
                block_index=1,
                start=0,
                end=len(REVEAL_TEXT),
                span_type=SpanType.NARRATION_DESCRIPTION,
                text=REVEAL_TEXT,
            )
        ]
    )
    # A real run always segments; without a segment `_scene_blocks` falls
    # back to the reveal's own block, which is the behaviour pinned
    # separately in `TestSceneGranularity`.
    s.add_segments(
        [
            NarrativeSegment(
                id="seg1",
                novel_id="n",
                chapter_from=1.0,
                offset_from=0,
                chapter_to=1.0,
                offset_to=1,
                story_seq_from=1.0,
                story_seq_to=1.0,
            )
        ]
    )
    s.conn.commit()
    yield s
    s.close()


def _mention(mid: str, text: str, target: str, block: int, mode: ReferenceMode) -> Mention:
    return Mention(
        id=mid,
        novel_id="n",
        segment_id="seg1",
        chapter=1.0,
        offset=0,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_DESCRIPTION,
        reference_mode=mode,
        block_index=block,
        target_kind=TargetKind.SELF,
        target_id=target,
    )


class TestWitnessDetection:
    def test_a_co_present_character_gets_an_observation(self, store) -> None:  # type: ignore[no-untyped-def]
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Bo", WITNESS, 0, ReferenceMode.PRESENT),
                _mention("m2", "Fang Yuan", TARGET, 1, ReferenceMode.PRESENT),
            ]
        )
        store.conn.commit()
        report = detect_observations(store, "n")
        assert report.reveals == 1
        assert report.reveals_with_witnesses == 1
        assert store.observations_for(WITNESS)

    def test_the_revealed_character_is_not_recorded_as_learning_it(self, store) -> None:  # type: ignore[no-untyped-def]
        """They already knew. Dating their self-knowledge to when someone else
        found out is exactly the Self/Persona confusion #3 forbids."""
        store.add_mentions([_mention("m2", "Fang Yuan", TARGET, 1, ReferenceMode.PRESENT)])
        store.conn.commit()
        detect_observations(store, "n")
        assert store.observations_for(TARGET) == {}

    def test_include_revealed_self_is_opt_in(self, store) -> None:  # type: ignore[no-untyped-def]
        store.add_mentions([_mention("m2", "Fang Yuan", TARGET, 1, ReferenceMode.PRESENT)])
        store.conn.commit()
        detect_observations(store, "n", include_revealed_self=True)
        assert store.observations_for(TARGET)

    def test_a_merely_mentioned_character_is_not_a_witness(self, store) -> None:  # type: ignore[no-untyped-def]
        """Being named in dialogue is not being in the room -- the same
        distinction `present_cast` exists to draw."""
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Bo", WITNESS, 0, ReferenceMode.DIALOGUE_REFERENCE),
                _mention("m2", "Fang Yuan", TARGET, 1, ReferenceMode.PRESENT),
            ]
        )
        store.conn.commit()
        detect_observations(store, "n")
        assert store.observations_for(WITNESS) == {}

    def test_rerunning_does_not_duplicate(self, store) -> None:  # type: ignore[no-untyped-def]
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Bo", WITNESS, 0, ReferenceMode.PRESENT),
                _mention("m2", "Fang Yuan", TARGET, 1, ReferenceMode.PRESENT),
            ]
        )
        store.conn.commit()
        detect_observations(store, "n")
        first = store.count_observations()
        detect_observations(store, "n")
        assert store.count_observations() == first

    def test_no_reveals_is_an_empty_report_not_a_crash(self, store) -> None:  # type: ignore[no-untyped-def]
        store.conn.execute("DELETE FROM span")
        store.conn.commit()
        assert detect_observations(store, "n").reveals == 0


class TestSceneGranularity:
    def test_witnessing_spans_the_scene_not_just_the_reveal_block(self, store) -> None:  # type: ignore[no-untyped-def]
        """Measured, not assumed: block granularity produced **zero**
        observations from all three RI reveals, because each reveal block
        held exactly one person mention -- the revealed character. Someone
        standing in the room is a witness whether or not their name recurs in
        the same paragraph."""
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Bo", WITNESS, 0, ReferenceMode.PRESENT),
                _mention("m2", "Fang Yuan", TARGET, 1, ReferenceMode.PRESENT),
            ]
        )
        store.conn.commit()
        assert detect_observations(store, "n").observations_written == 1

    def test_without_segmentation_it_falls_back_to_the_block(self, store) -> None:  # type: ignore[no-untyped-def]
        """Fewer observations, not silently none."""
        store.conn.execute("DELETE FROM narrative_segment")
        store.add_mentions(
            [
                _mention("m1", "Gu Yue Bo", WITNESS, 0, ReferenceMode.PRESENT),
                _mention("m2", "Fang Yuan", TARGET, 1, ReferenceMode.PRESENT),
            ]
        )
        store.conn.commit()
        assert detect_observations(store, "n").observations_written == 0


class TestRefAgreement:
    def test_the_written_ref_matches_what_state_of_will_look_up(self) -> None:
        """A mismatch is silent: a missing observation is indistinguishable
        from "this character did not witness it"."""
        assert reveal_fact_ref(TARGET, "Fang  YUAN") == fact_ref(
            "alias", TARGET, normalize("fang yuan")
        )
