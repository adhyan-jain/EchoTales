"""Tests for panel-casting data and the attire fallback chain (xyz.md Step 4)."""

from __future__ import annotations

import pytest

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import (
    MAIN_TIMELINE,
    Block,
    Chapter,
    DiscoursePosition,
    Mention,
    NarrativeSegment,
    Self,
    Span,
)
from echotales.core.store import Store
from echotales.pipeline.persona import get_panel_cast, resolve_attire
from echotales.pipeline.resolve.detect_reveals import detect_reveals


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


@pytest.fixture(autouse=True)
def _project_genres():
    # A project's genre is stored or detected from its text; these tests stand in for that for the old test books.
    from echotales.pipeline.persona import genre

    saved = dict(genre._PROJECT_GENRE)
    genre._PROJECT_GENRE.update({"reverend-insanity": "xianxia"})
    yield
    genre._PROJECT_GENRE.clear()
    genre._PROJECT_GENRE.update(saved)


class TestResolveAttire:
    def test_explicit_wins(self) -> None:
        assert resolve_attire("reverend-insanity", explicit="a scholar's robe") == "a scholar's robe"

    def test_falls_back_to_the_genre_style(self) -> None:
        assert "xianxia" in resolve_attire("reverend-insanity")

    def test_unseeded_novel_gets_a_labelled_default(self) -> None:
        out = resolve_attire("some-other-novel")
        assert out and "xianxia" not in out


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

    def test_reveal_adds_the_revealed_character_to_the_cast(self, tmp_path) -> None:
        """Fix 6: a block whose only mention is an unresolved placeholder
        ("the stranger", no `target_id` -- `present_cast`'s own person
        filter already excludes it) still draws the revealed identity once
        the narrator hands it to the reader."""
        store = Store(str(tmp_path / "t.db"))
        store.add_novel("reverend-insanity", "RI", "x.epub", "generic")
        store.add_self(
            Self(
                id="ri:self1",
                novel_id="reverend-insanity",
                canonical_label="Fang Yuan",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.SELF,
            )
        )
        text = "The stranger walked in. This was none other than Fang Yuan."
        store.add_chapter(
            Chapter(
                novel_id="reverend-insanity",
                number=1.0,
                title="T",
                source_href="a.html",
                blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
            )
        )
        store.add_spans(
            [
                Span(
                    id="sp0",
                    novel_id="reverend-insanity",
                    chapter=1.0,
                    block_index=0,
                    start=0,
                    end=len(text),
                    span_type=SpanType.NARRATION_DESCRIPTION,
                    text=text,
                )
            ]
        )
        store.conn.commit()
        detect_reveals(store, "reverend-insanity")

        chapter = Chapter(
            novel_id="reverend-insanity",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[Block(index=0, block_type=BlockType.PROSE, text=text)],
        )
        # Only a placeholder mention resolves in-scene -- no mention of
        # "Fang Yuan" himself, which is exactly the case a reveal covers.
        mentions = [_mention("The stranger", 0)]
        spans = [_span(text, 0)]
        segments = [_segment(0, 0)]

        cast = get_panel_cast(
            "reverend-insanity",
            chapter,
            0,
            mentions=mentions,
            segments=segments,
            spans=spans,
            store=store,
        )
        labels = {c.self_label for c in cast.foreground_characters}
        assert labels == {"Fang Yuan"}

    def test_reveal_in_a_different_block_does_not_leak_in(self, tmp_path) -> None:
        store = Store(str(tmp_path / "t.db"))
        store.add_novel("reverend-insanity", "RI", "x.epub", "generic")
        store.add_self(
            Self(
                id="ri:self1",
                novel_id="reverend-insanity",
                canonical_label="Fang Yuan",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.SELF,
            )
        )
        reveal_text = "This was none other than Fang Yuan."
        chapter = Chapter(
            novel_id="reverend-insanity",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[
                Block(index=0, block_type=BlockType.PROSE, text="Someone else was here."),
                Block(index=1, block_type=BlockType.PROSE, text=reveal_text),
            ],
        )
        store.add_chapter(chapter)
        store.add_spans(
            [
                Span(
                    id="sp0",
                    novel_id="reverend-insanity",
                    chapter=1.0,
                    block_index=0,
                    start=0,
                    end=23,
                    span_type=SpanType.NARRATION_DESCRIPTION,
                    text="Someone else was here.",
                ),
                Span(
                    id="sp1",
                    novel_id="reverend-insanity",
                    chapter=1.0,
                    block_index=1,
                    start=0,
                    end=len(reveal_text),
                    span_type=SpanType.NARRATION_DESCRIPTION,
                    text=reveal_text,
                ),
            ]
        )
        store.conn.commit()
        detect_reveals(store, "reverend-insanity")

        mentions = []
        spans = [
            _span("Someone else was here.", 0),
            _span(reveal_text, 1),
        ]
        segments = [_segment(0, 1)]

        cast = get_panel_cast(
            "reverend-insanity", chapter, 0, mentions=mentions, segments=segments, spans=spans, store=store
        )
        assert cast.foreground_characters == []
