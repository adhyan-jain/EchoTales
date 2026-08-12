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
    def test_renders_one_panel_per_story_block(self, tmp_path) -> None:
        store = _seeded_store(tmp_path)
        report = render_panels("t", store, out_dir=tmp_path / "panels")
        assert report.panels == 1
        assert report.skipped_non_story == 1

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
