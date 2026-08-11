"""Tests for active scene tracking and mob detection (xyz.md Step 2)."""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import MAIN_TIMELINE, Block, Chapter, Mention, NarrativeSegment, Span
from echotales.pipeline.spans.scene import build_active_scenes, detect_mobs


def _segment(offset_from: int, offset_to: int, chapter: float = 1.0) -> NarrativeSegment:
    return NarrativeSegment(
        id=f"seg-{offset_from}-{offset_to}",
        novel_id="t",
        chapter_from=chapter,
        offset_from=offset_from,
        chapter_to=chapter,
        offset_to=offset_to,
        timeline_id=MAIN_TIMELINE,
        story_seq_from=chapter,
        story_seq_to=chapter,
    )


def _mention(text: str, block_index: int, mode: ReferenceMode = ReferenceMode.PRESENT) -> Mention:
    return Mention(
        id=f"m-{text}-{block_index}",
        novel_id="t",
        segment_id="",
        chapter=1.0,
        offset=0,
        block_index=block_index,
        text=text,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=mode,
    )


def _span(text: str, block_index: int) -> Span:
    return Span(
        id=f"s{block_index}",
        novel_id="t",
        chapter=1.0,
        block_index=block_index,
        start=0,
        end=len(text),
        span_type=SpanType.NARRATION_ACTION,
        text=text,
    )


class TestDetectMobs:
    def test_finds_a_quantified_role_group(self) -> None:
        out = detect_mobs("Several disciples gathered outside.")
        assert len(out) == 1
        assert out[0].role == "disciples"

    def test_matches_crowd_itself_as_a_role(self) -> None:
        # "a crowd of disciples" matches on "a crowd" -- "crowd" is itself in
        # the role vocabulary, and that's a correct read of the phrase too.
        out = detect_mobs("A crowd of disciples gathered outside.")
        assert len(out) == 1
        assert out[0].role == "crowd"

    def test_finds_bare_the_plus_role(self) -> None:
        out = detect_mobs("The guards moved aside.")
        assert out[0].role == "guards"

    def test_does_not_match_a_named_individual(self) -> None:
        assert detect_mobs("Fang Yuan walked forward.") == []

    def test_does_not_match_singular_role(self) -> None:
        # "the guard" (singular) is not a described crowd.
        assert detect_mobs("The guard nodded.") == []


class TestBuildActiveScenes:
    def test_tracks_present_cast_per_segment(self) -> None:
        chapter = Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[
                Block(index=0, block_type=BlockType.PROSE, text="Fang Yuan stood."),
                Block(index=1, block_type=BlockType.PROSE, text="Fang Zheng joined him."),
            ],
        )
        mentions = [_mention("Fang Yuan", 0), _mention("Fang Zheng", 1)]
        spans = [_span("Fang Yuan stood.", 0), _span("Fang Zheng joined him.", 1)]
        segments = [_segment(0, 1)]

        scenes = build_active_scenes(chapter, mentions, segments, spans)
        assert len(scenes) == 1
        assert scenes[0].active_selves == {"Fang Yuan", "Fang Zheng"}

    def test_narrator_referenced_mention_is_not_present(self) -> None:
        chapter = Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="He thought of Fang Yuan.")],
        )
        mentions = [_mention("Fang Yuan", 0, mode=ReferenceMode.NARRATOR_REFERENCE)]
        spans = [_span("He thought of Fang Yuan.", 0)]
        segments = [_segment(0, 0)]

        scenes = build_active_scenes(chapter, mentions, segments, spans)
        assert scenes[0].active_selves == set()

    def test_collects_mobs_within_segment_bounds(self) -> None:
        chapter = Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[
                Block(index=0, block_type=BlockType.PROSE, text="A group of disciples watched."),
                Block(index=1, block_type=BlockType.PROSE, text="Fang Yuan left."),
            ],
        )
        spans = [_span("A group of disciples watched.", 0), _span("Fang Yuan left.", 1)]
        segments = [_segment(0, 1)]

        scenes = build_active_scenes(chapter, [], segments, spans)
        assert len(scenes[0].mobs) == 1
        assert scenes[0].mobs[0].role == "disciples"

    def test_segment_outside_chapter_is_skipped(self) -> None:
        chapter = Chapter(
            novel_id="t", number=2.0, title="T", source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="text")],
        )
        segments = [_segment(0, 0, chapter=1.0)]
        assert build_active_scenes(chapter, [], segments, []) == []
