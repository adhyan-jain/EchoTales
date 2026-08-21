"""Tests for Phase 2 narrative segmentation.

The governing asymmetry (plans.md Section 6 Phase 2): a missed flashback costs one
temporal misattribution; a false flashback costs that *plus* a spurious
timeline every later fact gets attached to. So most of these tests are about
what segmentation must refuse to do.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from echotales.core.enums import BlockType, EventType, NarrativeLayer, SegmentType
from echotales.core.models import MAIN_TIMELINE, Block, Chapter
from echotales.core.store import Store
from echotales.pipeline.config import LLMMode, Settings
from echotales.pipeline.llm import LLMRouter, StubProvider
from echotales.pipeline.segment import (
    MarkerKind,
    find_markers,
    find_time_skips,
    needs_llm_pass,
    scan_chapter,
    segment_chapter,
    segment_novel,
)
from echotales.pipeline.segment.llm_pass import SegmentationResponse


def chapter(*texts: str, number: float = 1.0, novel: str = "t") -> Chapter:
    return Chapter(
        novel_id=novel,
        number=number,
        title="T",
        source_href="a.html",
        blocks=[
            Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)
        ],
    )


def filler(n: int, word: str = "He walked onward.") -> list[str]:
    return [word] * n


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


class TestMarkers:
    @pytest.mark.parametrize(
        "text",
        [
            "His vision changed.",
            "Her vision blurred and shifted.",
            "He entered the dream realm.",
            "The scene before him changed.",
        ],
    )
    def test_dream_entry_is_detected(self, text: str) -> None:
        """Dream entry is formulaic in this genre, which is why rules work."""
        kinds = {m.kind for m in find_markers(text)}
        assert MarkerKind.ENTER_DREAM in kinds

    @pytest.mark.parametrize(
        "text",
        ["The dream realm faded.", "He awoke.", "The memory faded.", "He returned to reality."],
    )
    def test_dream_exit_is_detected(self, text: str) -> None:
        kinds = {m.kind for m in find_markers(text)}
        assert kinds & {MarkerKind.EXIT_DREAM, MarkerKind.EXIT_FLASHBACK}

    @pytest.mark.parametrize(
        "text",
        [
            "Three years later, the sect had changed.",
            "Time passed.",
            "Five months went by.",
            "The following spring, he returned.",
        ],
    )
    def test_time_skips_are_detected(self, text: str) -> None:
        assert MarkerKind.TIME_SKIP in {m.kind for m in find_markers(text)}

    def test_scene_breaks_are_detected(self) -> None:
        assert find_markers("* * *")[0].kind is MarkerKind.SCENE_BREAK

    def test_flashback_cues_stay_below_the_promotion_threshold(self) -> None:
        """'Years ago' appears in ordinary dialogue constantly.

        It must be suggestive evidence only, never enough on its own to mint a
        timeline.
        """
        markers = find_markers("Many years ago, the sect was founded.")
        flashback = [m for m in markers if m.kind is MarkerKind.ENTER_FLASHBACK]
        assert flashback and all(m.confidence < 0.7 for m in flashback)

    def test_ordinary_narration_produces_no_markers(self) -> None:
        assert find_markers("He drew his blade and stepped forward.") == []


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


class TestDefaultBehaviour:
    def test_a_linear_chapter_is_one_main_segment(self) -> None:
        """Reduces to naive behaviour for a linear novel."""
        segments = segment_chapter(chapter(*filler(20)))
        assert len(segments) == 1
        assert segments[0].segment_type is SegmentType.MAIN
        assert segments[0].timeline_id == MAIN_TIMELINE

    def test_main_segment_story_seq_is_the_chapter_index(self) -> None:
        segments = segment_chapter(chapter(*filler(10), number=42.0))
        assert segments[0].story_seq_from == 42.0

    def test_a_short_chapter_is_never_split(self) -> None:
        segments = segment_chapter(chapter("His vision changed.", "A dream."))
        assert len(segments) == 1
        assert segments[0].segment_type is SegmentType.MAIN

    def test_mentioning_the_past_does_not_create_a_flashback(self) -> None:
        """The false-positive case that costs a spurious timeline."""
        segments = segment_chapter(
            chapter(*filler(5), "Many years ago the sect was founded, he mused.", *filler(5))
        )
        assert all(s.segment_type is SegmentType.MAIN for s in segments)


class TestDreamSegments:
    def build(self) -> Chapter:
        return chapter(
            *filler(4),
            "His vision changed.",
            *filler(6, "The dream unfolded strangely."),
            "The dream realm faded.",
            *filler(4),
        )

    def test_a_dream_becomes_its_own_segment(self) -> None:
        segments = segment_chapter(self.build())
        dreams = [s for s in segments if s.segment_type is SegmentType.DREAM_OTHER]
        assert len(dreams) == 1

    def test_dream_gets_its_own_timeline(self) -> None:
        """Not MAIN, so its cast cannot be linked to main-timeline entities."""
        dream = next(
            s for s in segment_chapter(self.build()) if s.segment_type is SegmentType.DREAM_OTHER
        )
        assert dream.timeline_id != MAIN_TIMELINE
        assert dream.timeline_id.startswith("DREAM_")

    def test_dream_layer_is_tagged_for_generation(self) -> None:
        dream = next(
            s for s in segment_chapter(self.build()) if s.segment_type is SegmentType.DREAM_OTHER
        )
        assert dream.narrative_layer is NarrativeLayer.DREAM_OTHER

    def test_main_narration_surrounds_the_dream(self) -> None:
        segments = segment_chapter(self.build())
        assert [s.segment_type for s in segments] == [
            SegmentType.MAIN,
            SegmentType.DREAM_OTHER,
            SegmentType.MAIN,
        ]

    def test_segments_tile_the_chapter_without_gaps(self) -> None:
        segments = sorted(segment_chapter(self.build()), key=lambda s: s.offset_from)
        for a, b in pairwise(segments):
            assert b.offset_from == a.offset_to + 1

    def test_dream_story_seq_is_local_to_its_timeline(self) -> None:
        """Derived timelines start at 0 and are not comparable with MAIN."""
        dream = next(
            s for s in segment_chapter(self.build()) if s.segment_type is SegmentType.DREAM_OTHER
        )
        assert dream.story_seq_from == 0.0

    def test_an_unterminated_dream_runs_to_the_end(self) -> None:
        """A dream continuing into the next chapter must not be closed early."""
        ch = chapter(*filler(4), "His vision changed.", *filler(8, "Still dreaming."))
        last_index = len(ch.blocks) - 1
        dream = next(
            s for s in segment_chapter(ch) if s.segment_type is SegmentType.DREAM_OTHER
        )
        assert dream.offset_to == last_index

    def test_two_dreams_get_distinct_timelines(self) -> None:
        """Sharing one would let unrelated dream casts be compared."""
        ch = chapter(
            *filler(4),
            "His vision changed.",
            *filler(5, "Dream one."),
            "He awoke.",
            *filler(4),
            "His vision changed.",
            *filler(5, "Dream two."),
            "He awoke.",
        )
        dreams = [s for s in segment_chapter(ch) if s.segment_type is SegmentType.DREAM_OTHER]
        assert len({d.timeline_id for d in dreams}) == len(dreams)


class TestTimeSkips:
    def test_skips_are_found(self) -> None:
        skips = find_time_skips(chapter(*filler(3), "Three years later, he returned.", *filler(3)))
        assert len(skips) == 1

    def test_a_skip_does_not_create_a_timeline(self) -> None:
        """The story stays on MAIN; a skip marks unobserved change, not a branch."""
        ch = chapter(*filler(4), "Three years later, he returned.", *filler(4))
        assert all(s.timeline_id == MAIN_TIMELINE for s in segment_chapter(ch))


# ---------------------------------------------------------------------------
# LLM gating -- the budget rule
# ---------------------------------------------------------------------------


class TestLLMGating:
    def test_a_linear_chapter_needs_no_call(self) -> None:
        assert not needs_llm_pass(scan_chapter(chapter(*filler(10))).markers)

    def test_a_confidently_marked_chapter_needs_no_call(self) -> None:
        """The rules already settled it; a call would be wasted budget."""
        ch = chapter(*filler(4), "His vision changed.", *filler(6), "He awoke.")
        assert not needs_llm_pass(scan_chapter(ch).markers)

    def test_an_ambiguous_chapter_asks_for_a_call(self) -> None:
        ch = chapter(*filler(4), "Many years ago, things were different.", *filler(4))
        assert needs_llm_pass(scan_chapter(ch).markers)


class TestRunner:
    @pytest.fixture
    def store(self) -> Store:
        s = Store(":memory:")
        s.add_novel("t", "T", "x.epub", "generic")
        return s

    def test_segments_are_persisted(self, store: Store) -> None:
        store.add_chapter(chapter(*filler(10), number=1.0))
        store.add_chapter(chapter(*filler(10), number=2.0))
        store.conn.commit()

        report = segment_novel("t", store)
        assert report.chapters == 2
        assert len(store.get_segments("t")) == report.segments

    def test_time_skip_events_are_logged(self, store: Store) -> None:
        store.add_chapter(chapter(*filler(3), "Three years later, all had changed.", *filler(3)))
        store.conn.commit()
        segment_novel("t", store)
        assert store.event_counts().get(EventType.TIME_SKIP.value) == 1

    def test_multiple_skips_in_one_chapter_get_distinct_ids(self, store: Store) -> None:
        """Character offsets repeat across blocks, so ids need the block index."""
        store.add_chapter(
            chapter(
                "Three years later, all had changed.",
                "Time passed.",
                "Five months went by.",
                *filler(3),
            )
        )
        store.conn.commit()
        report = segment_novel("t", store)
        assert report.time_skips >= 2

    def test_llm_is_not_called_when_disabled(self, store: Store) -> None:
        stub = StubProvider()
        router = LLMRouter(settings=Settings(llm_mode=LLMMode.STUB), stub=stub)
        store.add_chapter(chapter(*filler(4), "Many years ago it was different.", *filler(4)))
        store.conn.commit()

        segment_novel("t", store, router=router, use_llm=False)
        assert stub.calls == []

    def test_llm_fires_only_on_ambiguous_chapters(self, store: Store) -> None:
        """The budget rule in practice: one call per ambiguous chapter, no more."""
        stub = StubProvider()
        stub.register_response("segment", SegmentationResponse())
        router = LLMRouter(settings=Settings(llm_mode=LLMMode.STUB), stub=stub)

        store.add_chapter(chapter(*filler(10), number=1.0))
        store.add_chapter(
            chapter(*filler(4), "Many years ago it was different.", *filler(4), number=2.0)
        )
        store.conn.commit()

        report = segment_novel("t", store, router=router, use_llm=True)
        assert report.llm_calls == 1
        assert len(stub.calls) == 1

    def test_empty_llm_response_leaves_rules_untouched(self, store: Store) -> None:
        stub = StubProvider()
        stub.register_response("segment", SegmentationResponse())
        router = LLMRouter(settings=Settings(llm_mode=LLMMode.STUB), stub=stub)
        store.add_chapter(chapter(*filler(4), "Many years ago it differed.", *filler(4)))
        store.conn.commit()

        report = segment_novel("t", store, router=router, use_llm=True)
        assert all(
            s.segment_type is SegmentType.MAIN for s in store.get_segments("t")
        ), "an empty response must not invent segments"
        assert report.segments == 1
