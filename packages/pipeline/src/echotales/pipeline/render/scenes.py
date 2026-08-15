"""Group a chapter's blocks into scenes, for image-generation budgeting.

**Why this exists, separate from `render/beats.py`.** `beats.py` groups
blocks into *drawable moments* and then merges down to a hard panel count
(`max_panels`) by dropping the least dramatic ones -- the right unit for
"which moments get a picture." This module groups blocks into *scenes* --
contiguous stretches sharing a cast, a location and a timeline segment --
and is the right unit for a different question: "how many *distinct*
pictures does this stretch of story need before it starts repeating
itself." A 15-block conversation in one courtyard is one scene; it should
not cost 15 separate diffusion calls for 15 near-identical frames of the
same two people in the same place.

A scene boundary fires on any of three signals, first one wins:

1. **A `NarrativeSegment` boundary** -- a dream, flashback or timeline
   layer change (`spans/scene.py::build_active_scenes` already computes
   this; reused, not re-derived).
2. **The active cast changes** -- someone enters or leaves, read off each
   block's own resolved `speaker_self_id`s. Same signal
   `render/beats.py::segment_beats` already uses for its own boundary, kept
   independently here rather than imported, since beats merges its
   boundaries away under budget pressure and a scene boundary must not.
3. **The location changes** -- `persona/attire.py::scene_locale`'s cue
   table, the same lookup `render/panels.py` already uses per-panel to
   pick an environment. Two adjacent blocks whose locale cue disagrees
   ("a walled stone courtyard" -> "the ancestral temple") are a new scene
   even if the cast is identical.

Deliberately block-count tiered, not audio-duration tiered, even though
the spec this was built against states duration thresholds too (<=25s /
26-70s / >70s alongside the block counts). Per-block audio duration is
only known after voice synthesis has already run, and panel generation
(`render_panels`, Phase 9a) is not guaranteed to run after voice rendering
in every pipeline invocation -- block count is available unconditionally
from spans alone. The block-count bands (<=3 / 4-7 / >=8) are the same
bands the spec gives, just used as the sole gate rather than one of two.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.models import Chapter, Mention, NarrativeSegment, Span
from echotales.pipeline.persona.attire import scene_locale
from echotales.pipeline.spans.scene import ActiveScene, build_active_scenes

#: Scene length (in story blocks) -> how many unique images it gets.
#: Matches the spec's own bands.
SHORT_SCENE_MAX_BLOCKS = 3
MEDIUM_SCENE_MAX_BLOCKS = 7


@dataclass(slots=True)
class Scene:
    """One contiguous stretch of a chapter sharing cast, place and timeline."""

    index: int
    blocks: list[int]
    active_selves: set[str] = field(default_factory=set)

    @property
    def block_from(self) -> int:
        return self.blocks[0]

    @property
    def block_to(self) -> int:
        return self.blocks[-1]

    @property
    def image_budget(self) -> int:
        n = len(self.blocks)
        if n <= SHORT_SCENE_MAX_BLOCKS:
            return 1
        if n <= MEDIUM_SCENE_MAX_BLOCKS:
            return 2
        return 3


def _containing_segment(
    block_index: int, active_scenes: list[ActiveScene]
) -> ActiveScene | None:
    for seg in active_scenes:
        if seg.block_from <= block_index <= seg.block_to:
            return seg
    return None


def group_scenes(
    novel_id: str,
    chapter: Chapter,
    mentions: list[Mention],
    segments: list[NarrativeSegment],
    spans: list[Span],
) -> list[Scene]:
    """Split a chapter's story blocks into scenes.

    Only story-content blocks with actual text participate -- a heading or
    a non-diegetic block (already excluded from panels entirely,
    `panels.py`) has no business anchoring a scene boundary.
    """
    active_scenes = build_active_scenes(chapter, mentions, segments, spans)

    by_block: dict[int, list[Span]] = {}
    for span in spans:
        by_block.setdefault(span.block_index, []).append(span)

    story_blocks = sorted(
        b.index
        for b in chapter.blocks
        if b.block_type.is_story_content and b.text.strip()
    )
    block_text = {b.index: b.text for b in chapter.blocks}

    scenes: list[Scene] = []
    current: list[int] = []
    current_selves: set[str] = set()
    prev_cast: set[str] = set()
    prev_locale = ""
    prev_seg: ActiveScene | None = None

    def flush() -> None:
        if current:
            scenes.append(
                Scene(index=len(scenes), blocks=list(current), active_selves=set(current_selves))
            )

    for block_index in story_blocks:
        block_spans = by_block.get(block_index, [])
        cast_here = {s.speaker_self_id for s in block_spans if s.speaker_self_id}
        text = " ".join(s.text for s in block_spans) or block_text.get(block_index, "")
        locale_here = scene_locale(novel_id, text, block_index=block_index)
        seg_here = _containing_segment(block_index, active_scenes)

        boundary = (
            not current
            or seg_here is not prev_seg
            or (cast_here and prev_cast and cast_here != prev_cast)
            or (locale_here and prev_locale and locale_here != prev_locale)
        )
        if boundary and current:
            flush()
            current = []
            current_selves = set()

        current.append(block_index)
        if seg_here is not None:
            current_selves |= seg_here.active_selves
        if cast_here:
            prev_cast = cast_here
        if locale_here:
            prev_locale = locale_here
        prev_seg = seg_here

    flush()
    return scenes
