"""Per-block shot decisions: pan/zoom on a still panel, or cut to a motion
clip (xyz.md Step 4, video revision).

**One shot per block, matching `panels.py`'s granularity.** A block is
already the unit `get_panel_cast` casts a scene for, so it is the natural
unit to hold the camera on -- `timeline.py` then stretches that shot to
cover however long the block's lines take to speak.

**Motion-clip cutaways are capped and content-gated, not decorative.** The
reel that motivated this design cut to a clip only where the beat called
for one, and reused a small fixed set throughout -- see `motion.py`'s module
docstring. Two guards keep this stage honest about that:

1. `match_tag` (`motion.py`) must actually hit something in the block's
   text. A block with no action/impact cue never gets a cutaway, regardless
   of cadence.
2. `clip_gap_blocks` enforces a minimum spacing between cutaways even when
   consecutive blocks all cue the same tag -- a clip substituted every block
   reads as a glitch, not a beat.

**Pan direction is a legible, deterministic rule, not a per-shot guess.** A
block containing dialogue gets a slow push into the frame (draws the eye to
whoever is speaking); a block that is pure description gets a wide lateral
pan (there is no one face to hold on); everything else -- action, unattributed
narration -- gets a slow pull-out, which reads as scene-setting or aftermath
in most action beats. This is the one place flagged back to you as a
starting rule rather than a settled one: it has not been eyeballed against
real chapters yet, and `pan_direction` is a plain string specifically so it
is cheap to re-tune once it has been.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.motion import MotionClip, match_tag
from echotales.pipeline.render.panels import PanelImage

#: Minimum blocks between two motion-clip cutaways, even if every block in
#: between also cues a tag. Keeps clips feeling like accents, not the
#: default -- see the module docstring.
DEFAULT_CLIP_GAP_BLOCKS = 6


@dataclass(slots=True)
class ShotPlan:
    """What the camera does for one block, before timing is known."""

    chapter: float
    block_index: int
    kind: str  # "pan" | "clip"
    asset_path: str
    pan_direction: str | None = None  # "zoom_in" | "zoom_out" | "pan_left" | "pan_right"
    tag: str | None = None


def _pan_direction(spans: list[Span], block_index: int) -> str:
    if any(s.span_type is SpanType.DIALOGUE for s in spans):
        return "zoom_in"
    if any(s.span_type is SpanType.NARRATION_DESCRIPTION for s in spans):
        return "pan_left" if block_index % 2 == 0 else "pan_right"
    return "zoom_out"


def build_shot_plan(
    chapter: float,
    chapter_spans: list[Span],
    panel_images: dict[int, PanelImage],
    motion_library: dict[str, MotionClip],
    *,
    clip_gap_blocks: int = DEFAULT_CLIP_GAP_BLOCKS,
) -> list[ShotPlan]:
    """One `ShotPlan` per block that has both a rendered panel and dialogue
    or narration reaching audio.

    A block with spans but no panel (e.g. outside every tracked scene,
    `PanelCast` still returns an environment-only image, so it *would* have
    a panel) or a panel but no spans (a heading, filtered out upstream)
    contributes nothing here -- shots exist only where there is both
    something to show and something being said over it.
    """
    by_block: dict[int, list[Span]] = {
        block_index: list(group)
        for block_index, group in itertools.groupby(chapter_spans, key=lambda s: s.block_index)
    }

    plans: list[ShotPlan] = []
    last_clip_block: int | None = None

    for block_index in sorted(by_block):
        panel = panel_images.get(block_index)
        if panel is None:
            continue
        spans = by_block[block_index]
        blob = " ".join(s.text for s in spans)

        tag = match_tag(blob)
        far_enough = last_clip_block is None or block_index - last_clip_block >= clip_gap_blocks
        clip = motion_library.get(tag) if tag else None

        if clip is not None and far_enough:
            plans.append(
                ShotPlan(
                    chapter=chapter,
                    block_index=block_index,
                    kind="clip",
                    asset_path=clip.frames_dir,
                    tag=tag,
                )
            )
            last_clip_block = block_index
        else:
            plans.append(
                ShotPlan(
                    chapter=chapter,
                    block_index=block_index,
                    kind="pan",
                    asset_path=panel.image_path,
                    pan_direction=_pan_direction(spans, block_index),
                )
            )

    return plans
