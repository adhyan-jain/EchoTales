"""Panel image generation (xyz.md Step 4, video-assembly revision)."""

from __future__ import annotations

import pytest

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.render.panels import get_engine, render_panels


def _seeded_store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[
                Block(index=0, block_type=BlockType.HEADING, text="Chapter 1"),
                Block(index=1, block_type=BlockType.PROSE, text="Fang Yuan stood."),
            ],
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
    store.add_mentions(
        [
            Mention(
                id="m1",
                novel_id="t",
                segment_id="s",
                chapter=1.0,
                offset=0,
                block_index=1,
                text="Fang Yuan",
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF,
                target_id="t:self1",
            )
        ]
    )
    store.conn.commit()
    return store


class TestRenderPanels:
    def test_renders_one_panel_per_beat_not_per_block(self, tmp_path) -> None:
        """A paragraph is not a panel. Drawing every block produced 89
        near-duplicate images for one RI chapter, mostly scenery -- see
        `render/beats.py`. The heading block still contributes nothing."""
        store = _seeded_store(tmp_path)
        report = render_panels("t", store, out_dir=tmp_path / "panels")
        assert report.panels == 1

    def test_panel_count_is_capped_per_chapter(self, tmp_path) -> None:
        """The cap is the point: fewer, better images beat a hundred
        variations on an empty courtyard, and the render budget is better
        spent on more steps per image than on more images."""
        store = _seeded_store(tmp_path)
        report = render_panels(
            "t", store, out_dir=tmp_path / "panels", max_panels=1
        )
        assert report.panels <= 1

    def test_stub_writes_a_real_png(self, tmp_path) -> None:
        """Not a no-op: `director.py`/`compose.py` will open these files and
        read their dimensions, and a stub that wrote nothing would let a
        broken path pass CI -- same reasoning as `voice/engine.py::StubEngine`."""
        store = _seeded_store(tmp_path)
        out_dir = tmp_path / "panels"
        render_panels("t", store, out_dir=out_dir)
        image = out_dir / "t" / "ch1" / "block0001.png"
        assert image.exists()
        assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_rerun_reuses_cached_panels(self, tmp_path) -> None:
        store = _seeded_store(tmp_path)
        out_dir = tmp_path / "panels"
        render_panels("t", store, out_dir=out_dir)
        report = render_panels("t", store, out_dir=out_dir)
        assert report.skipped_cached == 1
        assert report.panels == 1

    def test_unknown_engine_raises_rather_than_silently_stubbing(self) -> None:
        with pytest.raises(ValueError, match="unknown image engine"):
            get_engine("nope")

    def test_identical_prompts_across_blocks_are_deduped_not_regenerated(
        self, tmp_path
    ) -> None:
        """Two blocks whose final prompt is byte-identical -- same cast (none),
        same environment, same locale, same beat text -- must not pay for a
        second diffusion pass. With one fixed seed per run, an identical
        prompt produces an identical image, so a second generation call
        reproduces a file already on disk for pure GPU cost."""
        store = Store(str(tmp_path / "t.db"))
        store.add_novel("t", "T", "x.epub", "generic")
        for chapter_number in (1.0, 2.0):
            store.add_chapter(
                Chapter(
                    novel_id="t",
                    number=chapter_number,
                    title="T",
                    source_href=f"{chapter_number:g}.html",
                    blocks=[Block(index=0, block_type=BlockType.PROSE, text="A room was quiet.")],
                )
            )
        store.conn.commit()

        report = render_panels("t", store, out_dir=tmp_path / "panels")
        assert report.panels == 2
        assert report.deduped_panels == 1
        # And the deduped file is a real, independent copy, not a symlink
        # into the manifest referencing a path that vanishes if the source
        # is ever cleaned up.
        ch1 = (tmp_path / "panels" / "t" / "ch1" / "block0000.png")
        ch2 = (tmp_path / "panels" / "t" / "ch2" / "block0000.png")
        assert ch1.exists() and ch2.exists()
        assert ch1.read_bytes() == ch2.read_bytes()

    def test_a_non_person_entity_never_joins_the_foreground_cast(self, tmp_path) -> None:
        """Measured on real RI ch1: a LOCATION ("Qing Mao Mountain") and an
        ORGANIZATION ("Daoist Gu") were both marked PRESENT in the block
        Fang Yuan is in, and rode into the panel prompt as if they were
        people to draw -- the generated panel was a stranger's face with no
        gender, hair or expression grounding it, because two of the three
        "characters" had no appearance data and never could."""
        from echotales.core.enums import TargetKind
        from echotales.core.models import MAIN_TIMELINE, NarrativeSegment
        from echotales.pipeline.persona.runner import get_panel_cast

        store = _seeded_store(tmp_path)
        store.add_self(
            Self(
                id="t:self2",
                novel_id="t",
                canonical_label="Some Mountain",
                first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
                kind=TargetKind.LOCATION,
            )
        )
        store.add_mentions(
            [
                Mention(
                    id="m2",
                    novel_id="t",
                    segment_id="s",
                    chapter=1.0,
                    offset=0,
                    block_index=1,
                    text="Some Mountain",
                    alias_type=AliasType.RIGID_NAME,
                    span_type=SpanType.NARRATION_ACTION,
                    reference_mode=ReferenceMode.PRESENT,
                    target_kind=TargetKind.SELF,  # stale on purpose -- see note below
                    target_id="t:self2",
                )
            ]
        )
        store.conn.commit()

        chapter = store.get_chapter("t", 1.0)
        mentions = store.get_mentions("t", 1.0)
        segment = NarrativeSegment(
            id="seg-1",
            novel_id="t",
            chapter_from=1.0,
            offset_from=0,
            chapter_to=1.0,
            offset_to=1,
            timeline_id=MAIN_TIMELINE,
            story_seq_from=1.0,
            story_seq_to=1.0,
        )
        cast = get_panel_cast(
            "t", chapter, 1, mentions=mentions, segments=[segment], spans=[], store=store
        )
        labels = [c.self_label for c in cast.foreground_characters]
        assert "Fang Yuan" in labels
        assert "Some Mountain" not in labels
