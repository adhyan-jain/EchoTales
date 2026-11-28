"""Scenes for the storyboard taken from the segment stage instead of a second model read.

Why: v1 asked its own model for scene cuts and, on RI ch1, missed the reborn timeline's start and put the prior-loop
death on the wrong layer (docs/results/STORYBOARD_DIRECTOR.md). The segment stage already reads the whole chapter for
cuts, time relation and prior loops, with quotes it verified; the director reuses that answer so two stages cannot
disagree about where a scene ends.

`SceneAnalysis.time_labels` exists only once the segment v3 work is merged (one `SegmentTimeLabel` per segment in reading
order: layer, TimeRelation, a verified quote, `verified`). It is read through getattr so this module works on both sides
of that merge; without labels the cut's own relation and evidence carry the story time.
"""

from __future__ import annotations

from typing import Any

from echotales.pipeline.storyboard.inputs import ChapterInput, Scene
from echotales.pipeline.storyboard.schema import Layer

_LAYER_FROM_LABEL = {
    "past": Layer.PAST,
    "memory": Layer.MEMORY,
    "dream": Layer.DREAM,
    "imagined": Layer.IMAGINED,
    "lore": Layer.LORE,
    "present": Layer.PRESENT,
}


def _name(value: Any) -> str:
    return str(getattr(value, "value", value) or "").upper()


def _cut_signal(cut_type: str, relation: str) -> str:
    # a simultaneous scene elsewhere is carried by a graphic match (RI ch1 block 79: both men at their windows); a jump in
    # time wants a caption; any other cut gets the wide establishing view
    if cut_type == "POV_SWITCH" or relation == "SAME":
        return "match"
    if cut_type == "TIME_JUMP":
        return "card"
    return "establishing"


def scenes_from_analysis(inp: ChapterInput, analysis: Any) -> list[Scene]:
    """Scenes (no presence yet) for the chapter's story blocks from a `SceneAnalysis`."""
    story = inp.block_ids
    starts: dict[int, Any] = {}
    for cut in sorted(analysis.cuts, key=lambda c: c.block):
        # a cut may sit on a non-story block (a separator or note): the scene begins at the next story block
        b = next((x for x in story if x >= cut.block), None)
        if b is not None and b != story[0]:
            starts.setdefault(b, cut)
    bounds = sorted(starts)
    labels = list(getattr(analysis, "time_labels", None) or [])
    prior = set(getattr(analysis, "prior_loop_segments", None) or ())
    out: list[Scene] = []
    first = [story[0], *bounds]
    for i, b0 in enumerate(first):
        b1 = (first[i + 1] - 1) if i + 1 < len(first) else story[-1]
        b1 = max((x for x in story if x <= b1), default=b0)
        cut = starts.get(b0)
        label = labels[i] if i < len(labels) else None
        layer = Layer.PAST if i in prior else Layer.PRESENT
        story_time = ""
        if label is not None and getattr(label, "verified", False):
            layer = _LAYER_FROM_LABEL.get(str(getattr(label, "layer", "present")).lower(), layer)
            story_time = str(getattr(label, "quote", "") or "")
        relation = _name(getattr(cut, "time_relation", "")) if cut is not None else ""
        if not story_time and cut is not None:
            ev = list(getattr(cut, "evidence", None) or [])
            story_time = (ev[0] if ev else relation.lower().replace("unknown", "")).strip()
        out.append(
            Scene(
                b0, b1, layer=layer, story_time=story_time,
                cut_signal="" if cut is None else _cut_signal(_name(getattr(cut, "cut_type", "")), relation),
                from_graph=False,
            )
        )
    return out
