"""Tests for panel-casting data and the attire fallback chain (xyz.md Step 4)."""

from __future__ import annotations

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType
from echotales.core.models import MAIN_TIMELINE, Block, Chapter, Mention, NarrativeSegment, Span
from echotales.pipeline.persona import get_panel_cast, resolve_attire


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


class TestResolveAttire:
    def test_explicit_wins_over_everything(self) -> None:
        assert (
            resolve_attire(
                "reverend-insanity", explicit="a scholar's robe", faction="Gu Yue Clan"
            )
            == "a scholar's robe"
        )

    def test_faction_default_when_no_explicit(self) -> None:
        out = resolve_attire("reverend-insanity", faction="Gu Yue Clan")
        assert "silk cultivator robes" in out

    def test_regional_default_when_no_faction_match(self) -> None:
        out = resolve_attire("reverend-insanity", faction="unknown sect", region="Southern Border")
        assert "bamboo" in out

    def test_falls_back_to_novel_style(self) -> None:
        out = resolve_attire("reverend-insanity")
        assert "xianxia" in out

    def test_unseeded_novel_gets_a_labelled_default(self) -> None:
        out = resolve_attire("some-other-novel")
        assert "no further style data" in out


class TestGetPanelCast:
    def test_foreground_and_environment_for_a_tracked_scene(self) -> None:
        chapter = Chapter(
            novel_id="reverend-insanity",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="Fang Yuan stood.")],
        )
        mentions = [_mention("Fang Yuan", 0)]
        spans = [_span("Fang Yuan stood.", 0)]
        segments = [_segment(0, 0)]

        cast = get_panel_cast(
            "reverend-insanity", chapter, 0, mentions=mentions, segments=segments, spans=spans
        )
        assert [c.self_label for c in cast.foreground_characters] == ["Fang Yuan"]
        assert "xianxia" in cast.environment

    def test_faction_default_applied_to_a_named_character(self) -> None:
        chapter = Chapter(
            novel_id="reverend-insanity",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="Fang Yuan stood.")],
        )
        mentions = [_mention("Fang Yuan", 0)]
        spans = [_span("Fang Yuan stood.", 0)]
        segments = [_segment(0, 0)]

        cast = get_panel_cast(
            "reverend-insanity",
            chapter,
            0,
            mentions=mentions,
            segments=segments,
            spans=spans,
            faction_by_self={"Fang Yuan": "Gu Yue Clan"},
        )
        assert "silk cultivator robes" in cast.foreground_characters[0].attire

    def test_background_mob_scoped_to_exact_block(self) -> None:
        chapter = Chapter(
            novel_id="reverend-insanity",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[
                Block(index=0, block_type=BlockType.PROSE, text="A group of disciples watched."),
                Block(index=1, block_type=BlockType.PROSE, text="Fang Yuan left."),
            ],
        )
        spans = [
            _span("A group of disciples watched.", 0),
            _span("Fang Yuan left.", 1),
        ]
        segments = [_segment(0, 1)]

        cast_block0 = get_panel_cast(
            "reverend-insanity", chapter, 0, mentions=[], segments=segments, spans=spans
        )
        assert len(cast_block0.background_mobs) == 1
        assert cast_block0.background_mobs[0].role == "disciples"

        cast_block1 = get_panel_cast(
            "reverend-insanity", chapter, 1, mentions=[], segments=segments, spans=spans
        )
        assert cast_block1.background_mobs == []

    def test_outside_any_scene_returns_environment_only(self) -> None:
        chapter = Chapter(
            novel_id="reverend-insanity",
            number=2.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text="text")],
        )
        segments = [_segment(0, 0, chapter=1.0)]  # different chapter, so no scene covers ch2

        cast = get_panel_cast(
            "reverend-insanity", chapter, 0, mentions=[], segments=segments, spans=[]
        )
        assert cast.foreground_characters == []
        assert cast.background_mobs == []
        assert "xianxia" in cast.environment
