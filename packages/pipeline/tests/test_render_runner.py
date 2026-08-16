"""End-to-end: panels + a motion library + a voice manifest -> composited
chapter videos, all through the stub engines (xyz.md Step 4, video revision)."""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span
from echotales.core.store import Store
from echotales.pipeline.render.compose import get_engine as get_compose_engine
from echotales.pipeline.render.panels import get_engine as get_panel_engine, render_panels
from echotales.pipeline.render.runner import render_videos


def _write_wav(path: Path, seconds: float, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(struct.pack("<h", 0) * frames)


def _seeded_store(tmp_path: Path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(
        Chapter(
            novel_id="t",
            number=1.0,
            title="T",
            source_href="a.html",
            blocks=[
                Block(index=0, block_type=BlockType.PROSE, text='"Stop!" Fang Yuan shouted.'),
                Block(index=1, block_type=BlockType.PROSE, text="He walked north."),
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
                id="m1", novel_id="t", segment_id="s", chapter=1.0, offset=0, block_index=0,
                text="Fang Yuan", alias_type=AliasType.RIGID_NAME,
                span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT,
                target_kind=TargetKind.SELF, target_id="t:self1",
            )
        ]
    )
    store.add_spans(
        [
            Span(id="sp0", novel_id="t", chapter=1.0, block_index=0, start=0, end=10,
                 span_type=SpanType.DIALOGUE, text='"Stop!" Fang Yuan shouted.'),
            Span(id="sp1", novel_id="t", chapter=1.0, block_index=1, start=0, end=10,
                 span_type=SpanType.NARRATION_ACTION, text="He walked north."),
        ]
    )
    store.conn.commit()
    return store


def _write_voice_manifest(voice_dir: Path, panel_paths: dict[int, Path]) -> None:
    """A hand-built stand-in for `voice/runner.py::render_novel`'s output --
    this test only needs the fields `render/runner.py::_AudioLine` reads."""
    lines = []
    for block_index in (0, 1):
        wav = voice_dir / f"ch1_block{block_index}.wav"
        _write_wav(wav, 1.0)
        lines.append({"chapter": 1.0, "block_index": block_index, "audio_path": str(wav)})
    out = voice_dir / "manifest.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


class TestRenderVideosEndToEnd:
    def test_composites_a_chapter_from_panels_and_a_voice_manifest(self, tmp_path) -> None:
        store = _seeded_store(tmp_path)
        panel_dir = tmp_path / "panels"
        voice_dir = tmp_path / "audio"
        out_dir = tmp_path / "video"

        panel_report = render_panels("t", store, out_dir=panel_dir, engine=get_panel_engine("stub"))
        # Scene-grouped generation (render/scenes.py): both blocks share one
        # scene (2 blocks, no cast/locale signal in this fixture to split
        # them), so a short scene's budget of 1 unique image covers both --
        # `render_videos` below still produces one shot per block, both
        # pointing at that one generated image.
        assert panel_report.panels == 1

        _write_voice_manifest(voice_dir, {})

        report = render_videos(
            "t", store,
            panel_dir=panel_dir, motion_dir=tmp_path / "motion", voice_dir=voice_dir,
            out_dir=out_dir, engine=get_compose_engine("stub"),
        )
        assert report.chapters_rendered == 1
        assert report.chapters_skipped_no_audio == 0

        # StubComposeEngine's real output: concatenated audio + a shot manifest.
        wav = out_dir / "ch1.wav"
        assert wav.exists()
        with wave.open(str(wav)) as fh:
            assert abs(fh.getnframes() / fh.getframerate() - 2.0) < 0.01

        shots = json.loads((out_dir / "ch1.shots.json").read_text())
        assert [s["block_index"] for s in shots] == [0, 1]
        assert shots[0]["pan_direction"] == "zoom_in"  # dialogue block

    def test_chapter_with_no_voice_manifest_is_skipped_not_errored(self, tmp_path) -> None:
        store = _seeded_store(tmp_path)
        panel_dir = tmp_path / "panels"
        render_panels("t", store, out_dir=panel_dir, engine=get_panel_engine("stub"))

        report = render_videos(
            "t", store,
            panel_dir=panel_dir, motion_dir=tmp_path / "motion", voice_dir=tmp_path / "no_audio",
            out_dir=tmp_path / "video", engine=get_compose_engine("stub"),
        )
        assert report.chapters_rendered == 0
        assert report.chapters_skipped_no_audio == 1
