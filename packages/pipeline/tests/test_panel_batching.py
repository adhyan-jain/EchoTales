"""Unit tests for chapter-level panel generation batching and compiled routing."""

from __future__ import annotations

import base64
import io
from pathlib import Path
import pytest
from PIL import Image

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.render import compiled_route
from echotales.pipeline.render.panels import PanelImageRequest, render_panels
from echotales.pipeline.workers_contract import ImageWorkerResponse


class FakeWorker:
    def __init__(self) -> None:
        self.calls: list[tuple[list, list, bool]] = []

    def generate_many(self, requests, sections=None, *, greyscale=False):
        self.calls.append((list(requests), list(sections) if sections else [], greyscale))
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
        raw = base64.b64encode(buf.getvalue()).decode()
        return [
            ImageWorkerResponse(image_b64=raw, seed=r.seed, duration_s=0.01)
            for r in requests
        ]


def test_generate_compiled_batch_empty() -> None:
    # Empty batch should be a no-op
    compiled_route.generate_compiled_batch([], [], "z-image-turbo", greyscale=False)


def test_generate_compiled_batch_multiple_requests(tmp_path: Path) -> None:
    fake = FakeWorker()
    compiled_route.set_worker("z-image-turbo", fake)
    try:
        req1 = PanelImageRequest(
            prompt="Prompt 1",
            out_path=tmp_path / "panel_01.png",
            negative_prompt="neg1",
            width=512,
            height=512,
            seed=42,
        )
        req2 = PanelImageRequest(
            prompt="Prompt 2",
            out_path=tmp_path / "sub" / "panel_02.png",
            negative_prompt="neg2",
            width=512,
            height=512,
            seed=43,
        )
        secs1 = [("subject", "Prompt 1")]
        secs2 = [("subject", "Prompt 2")]

        compiled_route.generate_compiled_batch(
            [req1, req2], [secs1, secs2], "z-image-turbo", greyscale=True
        )

        assert len(fake.calls) == 1
        reqs, secs, grey = fake.calls[0]
        assert len(reqs) == 2
        assert reqs[0].prompt == "Prompt 1" and reqs[0].seed == 42
        assert reqs[1].prompt == "Prompt 2" and reqs[1].seed == 43
        assert secs == [secs1, secs2]
        assert grey is True

        assert req1.out_path.exists()
        assert req1.out_path.read_bytes().startswith(b"\x89PNG")
        assert req2.out_path.exists()
        assert req2.out_path.read_bytes().startswith(b"\x89PNG")
    finally:
        compiled_route.set_worker("z-image-turbo", None)


class MockNonStubEngine:
    name: str = "z-image-turbo"

    def generate(self, req):
        return req.out_path


def test_render_panels_batches_chapter_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify render_panels collects panels across the chapter into a single worker batch."""
    from echotales.pipeline.config import get_settings

    # Configure pipeline settings to use compiled route
    settings = get_settings()
    monkeypatch.setattr(settings, "render_prompt_compiler", True)
    monkeypatch.setattr(settings, "render_image_model", "z-image-turbo")
    monkeypatch.setattr(settings, "render_panel_mode", "manga")

    store = Store(str(tmp_path / "test.db"))
    store.add_novel("test_novel", "Test Novel", "test.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="test_novel",
            number=1.0,
            title="Chapter 1",
            source_href="ch1.html",
            blocks=[
                Block(index=0, block_type=BlockType.HEADING, text="Chapter 1"),
                Block(index=1, block_type=BlockType.PROSE, text="Fang Yuan stood on the mountain cliff overlooking the misty valley."),
                Block(index=2, block_type=BlockType.PROSE, text="Gu Yue Bo led the clan elders through the ancient stone pavilion."),
            ],
        )
    )
    store.add_self(
        Self(
            id="test_novel:self1",
            novel_id="test_novel",
            canonical_label="Fang Yuan",
            first_attested_pos=DiscoursePosition(chapter=1.0, offset=0),
            kind=TargetKind.SELF,
        )
    )
    store.add_mentions(
        [
            Mention(
                id="m1",
                novel_id="test_novel",
                segment_id="s1",
                chapter=1.0,
                offset=0,
                block_index=1,
                text="Fang Yuan",
                alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION,
                reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF,
                target_id="test_novel:self1",
            )
        ]
    )
    store.conn.commit()

    fake = FakeWorker()
    compiled_route.set_worker("z-image-turbo", fake)
    try:
        report = render_panels(
            "test_novel",
            store,
            engine=MockNonStubEngine(),
            out_dir=tmp_path / "panels",
            max_panels=5,
        )
        # Should have generated panels
        assert report.panels >= 1
        # Worker generate_many should have been called in a single chapter-level batch
        assert len(fake.calls) == 1
        reqs, _, greyscale = fake.calls[0]
        assert len(reqs) == report.panels
        assert greyscale is True
    finally:
        compiled_route.set_worker("z-image-turbo", None)
