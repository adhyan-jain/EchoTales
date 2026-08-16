"""Phase 9: assemble a finished per-chapter video from what phases 7-8
already produced (xyz.md Step 4, video revision -- the orchestrator that
ties `panels.py`, `motion.py`, `director.py`, `timeline.py` and
`compose.py` together).

Reads two manifests that must already exist on disk -- `panels.py`'s
(`render_panels`) and `voice/runner.py`'s (`render_novel`) -- rather than
regenerating either, because both are expensive (a GPU image render, a GPU
TTS synthesis) and this stage's whole job is arranging already-paid-for
assets against each other, never re-paying for them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.render.captions import build_captions, write_ass
from echotales.pipeline.render.compose import ComposeEngine, get_engine
from echotales.pipeline.render.director import build_shot_plan
from echotales.pipeline.render.motion import load_motion_library
from echotales.pipeline.render.panels import PanelImage
from echotales.pipeline.render.scenes import group_scenes
from echotales.pipeline.render.timeline import build_timeline, read_wav_duration


@dataclass(slots=True)
class _AudioLine:
    """Just enough of `voice/runner.py::AudioLine` to build a timeline --
    reconstructed from JSON by field name, so extra manifest columns are
    ignored rather than rejected."""

    chapter: float
    block_index: int
    audio_path: str = ""
    #: Carried for the caption track, not the timeline: the on-screen text
    #: is the line's own prose, attributed and typed exactly as the voice
    #: stage recorded it (`render/captions.py`).
    span_id: str = ""
    span_type: str = ""
    text: str = ""
    speaker_label: str = ""

    @classmethod
    def from_json(cls, raw: dict) -> _AudioLine:
        return cls(
            chapter=raw["chapter"],
            block_index=raw["block_index"],
            audio_path=raw.get("audio_path", ""),
            span_id=raw.get("span_id", ""),
            span_type=raw.get("span_type", ""),
            text=raw.get("text", ""),
            speaker_label=raw.get("speaker_label", ""),
        )


@dataclass(slots=True)
class VideoReport:
    novel_id: str
    chapters_rendered: int = 0
    chapters_skipped_no_audio: int = 0
    caption_cards: int = 0
    engine: str = "stub"

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.chapters_rendered} chapter videos ({self.engine}); "
            f"{self.chapters_skipped_no_audio} skipped (no rendered audio); "
            f"{self.caption_cards:,} caption cards"
        )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def render_videos(
    novel_id: str,
    store: Store,
    *,
    panel_dir: str | Path = "data/panels",
    motion_dir: str | Path = "data/motion",
    voice_dir: str | Path = "data/audio",
    out_dir: str | Path = "data/video",
    engine: ComposeEngine | None = None,
    chapters: list[float] | None = None,
    clips_per_chapter: int = 2,
    captions: bool = True,
) -> VideoReport:
    """Composite one mp4 per chapter that has both rendered panels and
    rendered audio.

    A chapter present in the panel manifest but absent from the voice
    manifest (voice rendering hasn't reached it yet, in a partial run) is
    skipped and counted, not treated as an error -- the two upstream stages
    are allowed to run at different paces.
    """
    engine = engine or get_engine("stub")
    report = VideoReport(novel_id=novel_id, engine=engine.name)
    out_dir = Path(out_dir)

    panels = [PanelImage(**raw) for raw in _read_jsonl(Path(panel_dir) / "manifest.jsonl")]
    audio_lines = [_AudioLine.from_json(raw) for raw in _read_jsonl(Path(voice_dir) / "manifest.jsonl")]
    motion_library = load_motion_library(novel_id, motion_dir)

    panels_by_chapter: dict[float, dict[int, PanelImage]] = {}
    for panel in panels:
        panels_by_chapter.setdefault(panel.chapter, {})[panel.block_index] = panel

    audio_by_chapter: dict[float, list[_AudioLine]] = {}
    for line in audio_lines:
        audio_by_chapter.setdefault(line.chapter, []).append(line)

    wanted = chapters if chapters is not None else sorted(panels_by_chapter)

    for chapter_number in wanted:
        chapter_audio = audio_by_chapter.get(chapter_number)
        panel_images = panels_by_chapter.get(chapter_number)
        if not chapter_audio or not panel_images:
            report.chapters_skipped_no_audio += 1
            continue

        chapter_spans = store.get_spans(novel_id, chapter_number)
        # Per-block audio length, so the director's pacing signal (a long
        # block goes stale under Ken Burns) sees real durations rather than
        # falling back to content cues alone.
        durations: dict[int, float] = {}
        for line in chapter_audio:
            if line.audio_path:
                durations[line.block_index] = durations.get(
                    line.block_index, 0.0
                ) + read_wav_duration(Path(line.audio_path))

        # Scene grouping for the clip-selection tier 2 signal ("emotional
        # peak of its scene") -- same scenes `render_panels` already
        # generated images against, recomputed here rather than persisted,
        # since it is cheap (spans/mentions/segments are already stored)
        # and keeps this stage independent of panel-generation internals.
        chapter_obj = store.get_chapter(novel_id, chapter_number)
        scenes = None
        if chapter_obj is not None:
            mentions = store.get_mentions(novel_id, chapter_number)
            segments = store.get_segments(novel_id, chapter_number)
            scenes = group_scenes(novel_id, chapter_obj, mentions, segments, chapter_spans)

        shots = build_shot_plan(
            chapter_number,
            chapter_spans,
            panel_images,
            motion_library,
            durations=durations,
            clips_per_chapter=clips_per_chapter,
            scenes=scenes,
        )
        timeline = build_timeline(chapter_number, chapter_audio, shots)
        if not timeline:
            report.chapters_skipped_no_audio += 1
            continue

        audio_paths = [Path(line.audio_path) for line in chapter_audio if line.audio_path]
        out_path = out_dir / f"ch{chapter_number:g}.mp4"

        # The prose on screen, timed off the same WAVs the picture is timed
        # off -- see `render/captions.py` on why this is the format rather
        # than an accessibility extra. Written next to the video so it is
        # inspectable (and editable by hand) without re-rendering.
        if captions and hasattr(engine, "captions_path"):
            per_span = {
                line.span_id: read_wav_duration(Path(line.audio_path))
                for line in chapter_audio
                if line.audio_path and getattr(line, "span_id", "")
            }
            cards = build_captions(chapter_audio, per_span)
            if cards:
                engine.captions_path = write_ass(
                    cards,
                    out_dir / f"ch{chapter_number:g}.ass",
                    width=getattr(engine, "width", 1080),
                    height=getattr(engine, "height", 1920),
                )
                report.caption_cards += len(cards)

        engine.render(timeline, audio_paths, out_path)
        report.chapters_rendered += 1

    return report
