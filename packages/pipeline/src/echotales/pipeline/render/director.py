"""Per-block shot decisions: pan/zoom on a still panel, or cut to a motion
clip (xyz.md Step 4, video revision).

**One shot per block, matching `panels.py`'s granularity.** A block is
already the unit `get_panel_cast` casts a scene for, so it is the natural
unit to hold the camera on -- `timeline.py` then stretches that shot to
cover however long the block's lines take to speak.

**Exactly two motion-clip cutaways per chapter, chosen by competition
rather than by cadence.** The reel this is modelled on used two clips for a
whole episode and reused them throughout -- see `motion.py`'s docstring. An
earlier version of this module placed a clip wherever a tag matched and a
spacing rule allowed, which is a *local* rule: it fires on whichever
matching block happens to come first, with no idea whether a better
candidate is coming. `score_blocks` instead ranks every block in the
chapter and takes the best two, so the clips land on the chapter's actual
peaks.

A chapter gets **two or zero**, never five: zero when nothing clears
`MIN_IMPACT_SCORE`, because a quiet chapter has no beat worth cutting to
and a clip inserted anyway reads as a non-sequitur.

The score combines what the prose says with what the audio is doing:

- combat verbs and revelation phrasing are the content signal;
- a block whose narration runs past `LONG_BLOCK_SECONDS` is the *pacing*
  signal, and it is the one that needs a clip most -- a static panel held
  for eight seconds of narration goes stale no matter how good the panel
  is, which is precisely the staleness the technique exists to break;
- a cast change marks a new beat, where a cut reads as intentional.

Selected blocks are never adjacent: two cutaways back to back read as one
long clip with a seam in it, so the second pick skips past any block
neighbouring the first.

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
from dataclasses import dataclass, field

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.motion import MotionClip, match_tag
from echotales.pipeline.render.panels import PanelImage
from echotales.pipeline.spans.delivery import (
    DeliveryPolarity,
    dominant_polarity,
    extract_delivery_markers,
)

#: How many cutaways a chapter gets. A hard cap, not a target: see the
#: module docstring on why two, and why zero is a valid answer.
CLIPS_PER_CHAPTER = 2

# TUNING: these values are first-guess, re-tune after watching ch1
#
# Ken Burns parameters for a held panel. `compose.py` reads these to build
# the actual pan/zoom filter; kept here as plain constants (not buried in
# an ffmpeg filter string) so they are the one place to adjust after
# watching real output, per the module docstring on `pan_direction` being
# a starting rule rather than a settled one.
#
# All transforms are linear easing, deliberately -- acceleration on a still
# image reads as shaky, not cinematic. A 1.0 -> 1.08 (or the reverse) scale
# range is a small, steady drift: enough to read as motion over a 5-15s
# hold, not so much that a face at the edge of frame leaves it.
KEN_BURNS_ZOOM_IN = (1.00, 1.08)
KEN_BURNS_ZOOM_OUT = (1.08, 1.00)
#: Lateral pan: fixed scale (headroom to pan within), translate range in
#: percent of frame width. Direction alternates per panel (`_pan_direction`
#: already alternates left/right by block-index parity) so a chapter does
#: not always drift the same way.
KEN_BURNS_PAN_SCALE = 1.05
KEN_BURNS_PAN_TRANSLATE_PCT = 3.0

#: A block must clear tier 3 (duration alone) to be worth a cutaway at
#: all -- see `score_blocks`'s three-tier priority order.
MIN_IMPACT_SCORE = 1

#: Narration longer than this on a single panel goes stale under Ken Burns.
LONG_BLOCK_SECONDS = 6.0

#: Delivery-marker polarity -> how much emotional intensity it represents,
#: for picking a scene's "emotional peak" block (tier 2 below). Reuses
#: `spans/delivery.py` rather than a second emotion vocabulary -- same
#: reasoning as `motion.py::POLARITY_TAGS`.
_INTENSITY_BY_POLARITY: dict[DeliveryPolarity, int] = {
    DeliveryPolarity.HEIGHTENED: 3,
    DeliveryPolarity.WARM: 2,
    DeliveryPolarity.COLD: 2,
    DeliveryPolarity.HUSHED: 1,
    DeliveryPolarity.HESITANT: 1,
    DeliveryPolarity.FLAT: 0,
}


def _delivery_intensity(text: str) -> int:
    polarity = dominant_polarity(extract_delivery_markers(text))
    return _INTENSITY_BY_POLARITY.get(polarity, 0) if polarity is not None else 0


@dataclass(slots=True)
class BlockScore:
    """Why a block did or did not earn a cutaway.

    Carried into the report rather than discarded, because "why did the clip
    land there" is the first question anyone watching the output asks, and
    re-deriving it from the video is impossible.
    """

    block_index: int
    score: int = 0
    duration: float = 0.0
    reasons: list[str] = field(default_factory=list)


def score_blocks(
    by_block: dict[int, list[Span]],
    durations: dict[int, float] | None = None,
    scenes: list[object] | None = None,
) -> list[BlockScore]:
    """Rank every block in a chapter by how much it wants a motion clip.

    Three priority tiers, strictly ordered -- a tier-1 block always outranks
    every tier-2 block regardless of duration, and so on:

    1. Duration > 8s **and** the block cues a motion-clip tag
       (`motion.py::match_tag`'s own vocabulary -- clash/wind/flame/impact).
    2. Duration > 6s **and** the block is its scene's emotional peak
       (highest `spans/delivery.py` marker intensity among the scene's
       blocks -- `scenes` groups blocks into scenes, `render/scenes.py`).
    3. Duration > 6s alone, as a fallback when nothing scores higher.

    `durations` is the per-block audio length from the voice manifest; when
    it is absent every duration reads as 0 and nothing clears any tier --
    the pacing signal cannot fire on a guess. `scenes` is optional for the
    same reason: without it, tier 2 never fires (no scene to be the peak
    of), and scoring still produces tier-1/tier-3 results.
    """
    durations = durations or {}

    scene_peak_block: dict[int, int] = {}
    if scenes:
        for scene in scenes:
            best_block, best_intensity = None, -1
            for b in scene.blocks:  # type: ignore[attr-defined]
                if b not in by_block:
                    continue
                text = " ".join(s.text for s in by_block[b])
                intensity = _delivery_intensity(text)
                if intensity > best_intensity:
                    best_intensity, best_block = intensity, b
            if best_block is not None:
                scene_peak_block[scene.index] = best_block  # type: ignore[attr-defined]
    peak_blocks = set(scene_peak_block.values())

    scored: list[BlockScore] = []
    for block_index in sorted(by_block):
        spans = by_block[block_index]
        blob = " ".join(s.text for s in spans)
        duration = durations.get(block_index, 0.0)
        entry = BlockScore(block_index=block_index, duration=duration)

        tag = match_tag(blob)
        if duration > 8.0 and tag is not None:
            entry.score = 3
            entry.reasons.append(f"tier 1: {duration:.1f}s + clip tag {tag!r}")
        elif duration > 6.0 and block_index in peak_blocks:
            entry.score = 2
            entry.reasons.append(f"tier 2: {duration:.1f}s + scene emotional peak")
        elif duration > 6.0:
            entry.score = 1
            entry.reasons.append(f"tier 3: {duration:.1f}s duration alone")

        scored.append(entry)

    return scored


def select_clip_blocks(
    scored: list[BlockScore],
    *,
    limit: int = CLIPS_PER_CHAPTER,
    min_score: int = MIN_IMPACT_SCORE,
) -> list[BlockScore]:
    """The blocks that get a cutaway: highest scoring, never adjacent.

    Ties break toward the longer block, then the earlier one, so selection
    is deterministic across runs -- a chapter that re-rendered with its
    clips in different places would look like a bug to anyone comparing two
    takes.
    """
    ranked = sorted(
        (b for b in scored if b.score >= min_score),
        key=lambda b: (-b.score, -b.duration, b.block_index),
    )

    chosen: list[BlockScore] = []
    for candidate in ranked:
        if len(chosen) >= limit:
            break
        if any(abs(candidate.block_index - c.block_index) <= 1 for c in chosen):
            continue
        chosen.append(candidate)
    return sorted(chosen, key=lambda b: b.block_index)


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
    durations: dict[int, float] | None = None,
    clips_per_chapter: int = CLIPS_PER_CHAPTER,
    min_impact_score: int = MIN_IMPACT_SCORE,
    scenes: list[object] | None = None,
) -> list[ShotPlan]:
    """One `ShotPlan` per block that has both a rendered panel and dialogue
    or narration reaching audio.

    A block with spans but no panel (e.g. outside every tracked scene,
    `PanelCast` still returns an environment-only image, so it *would* have
    a panel) or a panel but no spans (a heading, filtered out upstream)
    contributes nothing here -- shots exist only where there is both
    something to show and something being said over it.

    `durations` (block index -> seconds of audio) feeds tiers 1/2/3 of the
    impact score; pass the voice manifest's per-block sums. `scenes`
    (`render/scenes.py::Scene`, optional) feeds tier 2's "emotional peak of
    its scene" signal -- without it, tier 2 never fires and scoring falls
    back to tiers 1/3 alone.
    """
    by_block: dict[int, list[Span]] = {
        block_index: list(group)
        for block_index, group in itertools.groupby(chapter_spans, key=lambda s: s.block_index)
    }
    # Only blocks that actually have a panel can hold a shot, so score the
    # candidates rather than the whole chapter -- otherwise a cutaway can be
    # "selected" for a block that then falls through to nothing.
    candidates = {b: spans for b, spans in by_block.items() if b in panel_images}

    scored = score_blocks(candidates, durations, scenes)
    selected = select_clip_blocks(
        scored, limit=clips_per_chapter, min_score=min_impact_score
    )

    clip_by_block: dict[int, tuple[str, MotionClip]] = {}
    for entry in selected:
        spans = candidates[entry.block_index]
        tag = match_tag(" ".join(s.text for s in spans))
        # A block can earn a cutaway on impact but cue no specific tag --
        # "idle" is the neutral loop that exists for exactly this case.
        clip = motion_library.get(tag) if tag else None
        if clip is None:
            tag, clip = "idle", motion_library.get("idle")
        if clip is not None:
            clip_by_block[entry.block_index] = (tag, clip)

    plans: list[ShotPlan] = []
    for block_index in sorted(candidates):
        spans = candidates[block_index]
        if block_index in clip_by_block:
            tag, clip = clip_by_block[block_index]
            plans.append(
                ShotPlan(
                    chapter=chapter,
                    block_index=block_index,
                    kind="clip",
                    asset_path=clip.frames_dir,
                    tag=tag,
                )
            )
        else:
            plans.append(
                ShotPlan(
                    chapter=chapter,
                    block_index=block_index,
                    kind="pan",
                    asset_path=panel_images[block_index].image_path,
                    pan_direction=_pan_direction(spans, block_index),
                )
            )

    return plans
