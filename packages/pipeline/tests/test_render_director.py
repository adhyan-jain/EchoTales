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


def _clip(tag: str) -> MotionClip:
    return MotionClip(tag=tag, frames_dir=f"/clips/{tag}", num_frames=24, fps=12)


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

    def test_high_impact_block_cuts_to_a_matching_clip(self) -> None:
        """A combat verb (+3) plus a long block (+2) clears MIN_IMPACT_SCORE."""
        spans = [_span(0, SpanType.NARRATION_ACTION, "Their swords clashed as he struck.")]
        library = {"clash": _clip("clash")}
        plans = build_shot_plan(1.0, spans, {0: _panel(0)}, library, durations={0: 9.0})
        assert plans[0].kind == "clip"
        assert plans[0].tag == "clash"
        assert plans[0].asset_path == "/clips/clash"

    def test_exactly_two_clips_per_chapter_however_many_blocks_qualify(self) -> None:
        """The hard cap: ten blocks all cueing combat still yields two
        cutaways, not ten -- a clip is an accent (`director.py` docstring)."""
        spans = [
            _span(i, SpanType.NARRATION_ACTION, "He struck, and the blade shattered.")
            for i in range(10)
        ]
        panels = {i: _panel(i) for i in range(10)}
        plans = build_shot_plan(
            1.0, spans, panels, {"clash": _clip("clash"), "impact": _clip("impact")},
            durations={i: 9.0 for i in range(10)},
        )
        assert sum(1 for p in plans if p.kind == "clip") == 2

    def test_selected_clips_are_never_adjacent(self) -> None:
        """Back-to-back cutaways read as one clip with a seam in it."""
        spans = [
            _span(i, SpanType.NARRATION_ACTION, "He struck, and the wall shattered.")
            for i in range(6)
        ]
        panels = {i: _panel(i) for i in range(6)}
        plans = build_shot_plan(
            1.0, spans, panels, {"clash": _clip("clash"), "impact": _clip("impact")},
            durations={i: 9.0 for i in range(6)},
        )
        clip_blocks = [p.block_index for p in plans if p.kind == "clip"]
        assert len(clip_blocks) == 2
        assert abs(clip_blocks[0] - clip_blocks[1]) > 1

    def test_quiet_chapter_gets_zero_clips(self) -> None:
        """Two or zero, never a clip inserted for its own sake."""
        spans = [
            _span(i, SpanType.NARRATION_ACTION, "He walked to the market and bought rice.")
            for i in range(5)
        ]
        panels = {i: _panel(i) for i in range(5)}
        plans = build_shot_plan(
            1.0, spans, panels, {"clash": _clip("clash"), "idle": _clip("idle")},
            durations={i: 2.0 for i in range(5)},
        )
        assert all(p.kind == "pan" for p in plans)

    def test_short_narration_does_not_earn_a_cutaway(self) -> None:
        """Tier 3 (duration alone) requires > 6s; a short block clears no
        tier no matter its content."""
        spans = [_span(0, SpanType.NARRATION_ACTION, "He considered the road ahead.")]
        plans = build_shot_plan(
            1.0, spans, {0: _panel(0)}, {"idle": _clip("idle")}, durations={0: 5.0}
        )
        assert plans[0].kind == "pan"

    def test_long_block_with_no_tag_earns_a_cutaway_on_duration_alone(self) -> None:
        """Tier 3 is duration alone, deliberately with no content
        requirement -- a long block goes stale under Ken Burns regardless
        of what it says, and the neutral "idle" loop exists for exactly
        this case: a cutaway with no specific tag to cue."""
        spans = [
            _span(0, SpanType.NARRATION_DESCRIPTION,
                  "It was revealed that his true identity had been hidden all along.")
        ]
        plans = build_shot_plan(
            1.0, spans, {0: _panel(0)}, {"idle": _clip("idle")}, durations={0: 9.0}
        )
        assert plans[0].kind == "clip"
        assert plans[0].tag == "idle"

    def test_no_tag_match_stays_a_pan_even_with_a_library(self) -> None:
        spans = [_span(0, SpanType.NARRATION_ACTION, "He walked to the market.")]
        library = {"clash": _clip("clash")}
        plans = build_shot_plan(1.0, spans, {0: _panel(0)}, library)
        assert plans[0].kind == "pan"
