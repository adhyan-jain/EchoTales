"""Scene-cut vocabulary shared by discontinuity scoring, induction and the LLM pass.

A scene cut is not a NarrativeSegment boundary by itself: the existing enums say
which *layer* a stretch of text belongs to, not how its story time relates to
the stretch before it. RI ch1 shows the gap. Its cliff (blocks 0-30) is the end
of a life; the ritual after it is that same person's life 500 years earlier,
announced only at block 80 ("this is 500 years ago?!"). Nothing at block 31
itself says so. So a cut carries its own `time_relation`, which may be UNKNOWN
when the cut is first made and revised once a later block states the relation
(`implicit.resolve_story_order`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from echotales.core.enums import NarrativeLayer, SegmentType


class CutType(StrEnum):
    NEW_SCENE = "NEW_SCENE"  # place or participants change, story time continues
    TIME_JUMP = "TIME_JUMP"  # same story, an unobserved gap
    FLASHBACK = "FLASHBACK"  # earlier story time, remembered or shown
    PRIOR_LOOP = "PRIOR_LOOP"  # an earlier life/loop of a regressor, or its aftermath
    POV_SWITCH = "POV_SWITCH"  # simultaneous action, another viewpoint
    LORE = "LORE"  # legend or world history told apart from the plot


class TimeRelation(StrEnum):
    """Story time of the scene after the cut, relative to the scene before it."""

    EARLIER = "EARLIER"
    LATER = "LATER"
    SAME = "SAME"  # simultaneous or directly continuous
    UNKNOWN = "UNKNOWN"  # the text around the cut does not say


@dataclass(slots=True)
class SceneCut:
    """A cut placed before `block` (the first block of the new scene)."""

    chapter: float
    block: int
    source: str  # "induced:<convention id>" | "implicit:llm" | "implicit:score"
    score: float = 0.0
    cut_type: CutType = CutType.NEW_SCENE
    time_relation: TimeRelation = TimeRelation.UNKNOWN
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


#: CutType -> (segment_type, layer). There is no NarrativeLayer for a prior loop
#: and the core enum is shared with the visual stages, so a prior loop takes the
#: nearest existing layer (FLASHBACK_OWN, "an earlier stretch of this character's
#: own existence") and keeps its precise type in `segment_type`.
SEGMENT_FOR_CUT: dict[CutType, tuple[SegmentType, NarrativeLayer]] = {
    CutType.NEW_SCENE: (SegmentType.MAIN, NarrativeLayer.MAIN),
    CutType.TIME_JUMP: (SegmentType.MAIN, NarrativeLayer.MAIN),
    CutType.POV_SWITCH: (SegmentType.MAIN, NarrativeLayer.MAIN),
    CutType.FLASHBACK: (SegmentType.FLASHBACK_OWN, NarrativeLayer.FLASHBACK_OWN),
    CutType.PRIOR_LOOP: (SegmentType.REGRESSION_PRIOR_LOOP, NarrativeLayer.FLASHBACK_OWN),
    CutType.LORE: (SegmentType.HEARSAY, NarrativeLayer.MAIN),
}
