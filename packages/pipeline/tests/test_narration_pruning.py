"""Tests for Show, Don't Tell narration pruning (narration_pruning.py)."""

from __future__ import annotations

import pytest

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.narration_pruning import (
    NarrationVisualStatus,
    classify_span_visual_status,
    prune_spans_for_visual_mode,
)


def _span(span_id: str, span_type: SpanType, text: str) -> Span:
    return Span(
        id=span_id,
        novel_id="test",
        chapter=1.0,
        block_index=0,
        start=0,
        end=len(text),
        text=text,
        span_type=span_type,
    )


def test_dialogue_is_always_kept() -> None:
    s = _span("s1", SpanType.DIALOGUE, "“Who goes there?” he asked.")
    assert classify_span_visual_status(s) is NarrationVisualStatus.DIALOGUE_KEEP


def test_inner_monologue_is_always_kept() -> None:
    s = _span("s2", SpanType.INNER_MONOLOGUE, "This trap was laid centuries ago.")
    assert classify_span_visual_status(s) is NarrationVisualStatus.ABSTRACT_UNSEEN


def test_visual_physical_action_is_pruned() -> None:
    s = _span("s3", SpanType.NARRATION_ACTION, "Fang Yuan stood on the mountain peak as rain poured down.")
    assert classify_span_visual_status(s) is NarrationVisualStatus.CONVEYED_VISUALLY


def test_facial_expression_and_clothing_is_pruned() -> None:
    s = _span("s4", SpanType.NARRATION_DESCRIPTION, "A cold smile appeared on his face as his green robes fluttered.")
    assert classify_span_visual_status(s) is NarrationVisualStatus.CONVEYED_VISUALLY


def test_abstract_lore_and_memory_is_kept() -> None:
    s = _span(
        "s5",
        SpanType.NARRATION_EXPOSITION,
        "Five hundred years of experience in his past life had taught him that weakness invites slaughter.",
    )
    assert classify_span_visual_status(s) is NarrationVisualStatus.ABSTRACT_UNSEEN


def test_audiobook_mode_preserves_all_spans() -> None:
    spans = [
        _span("s1", SpanType.NARRATION_ACTION, "He drew his sword."),
        _span("s2", SpanType.DIALOGUE, "“Die!”"),
        _span("s3", SpanType.NARRATION_DESCRIPTION, "Blood dripped from the blade."),
    ]
    kept, report = prune_spans_for_visual_mode(spans, is_visual_mode=False)
    assert len(kept) == 3
    assert report.visually_pruned == 0
    assert report.reduction_rate == 0.0


def test_visual_mode_prunes_redundant_descriptions() -> None:
    spans = [
        _span("s1", SpanType.NARRATION_ACTION, "Fang Yuan stood quietly in the rainy courtyard."),  # visual -> prune
        _span("s2", SpanType.DIALOGUE, "“It begins.”"),  # dialogue -> keep
        _span("s3", SpanType.NARRATION_EXPOSITION, "Five hundred years of memories flashed through his mind."),  # abstract -> keep
        _span("s4", SpanType.NARRATION_DESCRIPTION, "His dark eyes gazed out toward the distant gate."),  # visual -> prune
    ]
    kept, report = prune_spans_for_visual_mode(spans, is_visual_mode=True)
    assert len(kept) == 2
    assert [s.id for s in kept] == ["s2", "s3"]
    assert report.visually_pruned == 2
    assert report.reduction_rate == pytest.approx(0.667, abs=0.01)
    assert "redundant visual spans pruned" in report.summary()


def test_render_cli_pruning_flag_is_off_by_default() -> None:
    from echotales.pipeline.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["render", "--novel", "x"]).prune_visual_narration is False
    assert parser.parse_args(["render", "--novel", "x", "--prune-visual-narration"]).prune_visual_narration is True
