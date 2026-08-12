"""Per-block shot decisions (xyz.md Step 4, video revision)."""

from __future__ import annotations

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.director import build_shot_plan
from echotales.pipeline.render.motion import MotionClip
from echotales.pipeline.render.panels import PanelImage


def _span(block_index: int, span_type: SpanType, text: str, i: int = 0) -> Span:
    return Span(
        id=f"sp{block_index}-{i}",
        novel_id="t",
        chapter=1.0,
        block_index=block_index,
        start=0,
        end=len(text),
        span_type=span_type,
        text=text,
    )


def _panel(block_index: int) -> PanelImage:
    return PanelImage(chapter=1.0, block_index=block_index, prompt="p", image_path=f"block{block_index}.png")


class TestBuildShotPlan:
    def test_dialogue_block_zooms_in(self) -> None:
        spans = [_span(0, SpanType.DIALOGUE, '"Stop!" he said.')]
        plans = build_shot_plan(1.0, spans, {0: _panel(0)}, {})
        assert plans[0].kind == "pan"
        assert plans[0].pan_direction == "zoom_in"

    def test_description_block_pans(self) -> None:
        spans = [_span(0, SpanType.NARRATION_DESCRIPTION, "The hall stretched on, pillars of jade.")]
        plans = build_shot_plan(1.0, spans, {0: _panel(0)}, {})
        assert plans[0].pan_direction in ("pan_left", "pan_right")

    def test_action_block_zooms_out(self) -> None:
        spans = [_span(0, SpanType.NARRATION_ACTION, "He walked north through the gate.")]
        plans = build_shot_plan(1.0, spans, {0: _panel(0)}, {})
        assert plans[0].pan_direction == "zoom_out"

    def test_block_without_a_panel_is_skipped(self) -> None:
        spans = [_span(0, SpanType.NARRATION_ACTION, "He walked north.")]
        plans = build_shot_plan(1.0, spans, {}, {})
        assert plans == []

    def test_matching_tag_cuts_to_a_clip(self) -> None:
        spans = [_span(0, SpanType.NARRATION_ACTION, "Their swords clashed violently.")]
        library = {"clash": MotionClip(tag="clash", frames_dir="/clips/clash", num_frames=24, fps=12)}
        plans = build_shot_plan(1.0, spans, {0: _panel(0)}, library)
        assert plans[0].kind == "clip"
        assert plans[0].tag == "clash"
        assert plans[0].asset_path == "/clips/clash"

    def test_clip_cutaways_respect_the_minimum_gap(self) -> None:
        """Every block cues the same tag; only the first (and anything past
        the gap) should actually cut to the clip -- constant cutaways would
        read as a glitch, not a beat (see `director.py`'s module docstring)."""
        spans = [
            _span(i, SpanType.NARRATION_ACTION, "Swords clashed again.")
            for i in range(5)
        ]
        panels = {i: _panel(i) for i in range(5)}
        library = {"clash": MotionClip(tag="clash", frames_dir="/clips/clash", num_frames=24, fps=12)}

        plans = build_shot_plan(1.0, spans, panels, library, clip_gap_blocks=3)
        kinds = [p.kind for p in plans]
        assert kinds[0] == "clip"
        assert kinds[1] == "pan" and kinds[2] == "pan"
        assert kinds[3] == "clip"  # 3 blocks after the first cutaway
        assert kinds[4] == "pan"

    def test_no_tag_match_stays_a_pan_even_with_a_library(self) -> None:
        spans = [_span(0, SpanType.NARRATION_ACTION, "He walked to the market.")]
        library = {"clash": MotionClip(tag="clash", frames_dir="/clips/clash", num_frames=24, fps=12)}
        plans = build_shot_plan(1.0, spans, {0: _panel(0)}, library)
        assert plans[0].kind == "pan"
