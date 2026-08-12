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
import re
from dataclasses import dataclass, field

from echotales.core.enums import SpanType
from echotales.core.models import Span
from echotales.pipeline.render.motion import MotionClip, match_tag
from echotales.pipeline.render.panels import PanelImage

#: How many cutaways a chapter gets. A hard cap, not a target: see the
#: module docstring on why two, and why zero is a valid answer.
CLIPS_PER_CHAPTER = 2

#: A block must score at least this to be worth a cutaway at all. Set so
#: that a long block (+2) or a bare combat verb (+3) alone does not qualify:
#: a cutaway should need either a strong content cue or a weak one
#: reinforced by pacing.
MIN_IMPACT_SCORE = 4

#: Narration longer than this on a single panel goes stale under Ken Burns.
LONG_BLOCK_SECONDS = 6.0

#: Stems that mark a landed physical beat. Deliberately narrower than
#: `motion.py::GENERIC_KEYWORDS`, which decides *which* clip to use; this
#: decides whether the moment deserves one at all.
#:
#: **Matched as stems, and chosen against the corpus rather than from
#: intuition.** The first version of this list was past-tense whole words
#: ("struck", "slammed", "erupted", "shattered"...) and scored **zero hits
#: across RI chapters 1, 8 and 20** -- chapter 1 is a massacre and matched
#: none of them, because the translation says "killed", "attacked" and
#: "blood", not "slammed". A cue vocabulary that never fires is worse than
#: no cue vocabulary, since it silently turns the impact score into a
#: cast-change detector. Stems (`attack` -> attacked/attacking) are what
#: make this robust to tense, which whole-word matching was not.
_COMBAT_VERBS = (
    "kill", "slay", "slaughter", "attack", "struck", "strike", "stab",
    "sever", "crush", "blast", "charge", "lunge", "hurl", "collide",
    "explod", "shatter", "smash", "erupt", "pierc", "slash", "slam",
    "roar", "massacre", "wound", "corpse",
)

#: Phrasing that marks a reveal.
_REVELATION_PATTERNS = (
    "revealed", "was none other", "true identity", "realised", "realized",
    "it was actually", "turned out to be",
)


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
) -> list[BlockScore]:
    """Rank every block in a chapter by how much it wants a motion clip.

    `durations` is the per-block audio length from the voice manifest; when
    it is absent the pacing signal simply does not fire, and scoring falls
    back to content cues alone rather than guessing at timing.
    """
    durations = durations or {}
    scored: list[BlockScore] = []

    for block_index in sorted(by_block):
        spans = by_block[block_index]
        blob = " ".join(s.text for s in spans).casefold()
        entry = BlockScore(
            block_index=block_index, duration=durations.get(block_index, 0.0)
        )

        for verb in _COMBAT_VERBS:
            # Stem-matched: a trailing \w* catches every inflection, which
            # whole-word matching missed entirely (see `_COMBAT_VERBS`).
            if re.search(rf"(?<!\w){verb}\w*", blob):
                entry.score += 3
                entry.reasons.append(f"combat stem {verb!r} (+3)")
                break

        for pattern in _REVELATION_PATTERNS:
            if pattern in blob:
                entry.score += 2
                entry.reasons.append(f"revelation {pattern!r} (+2)")
                break

        if entry.duration > LONG_BLOCK_SECONDS:
            entry.score += 2
            entry.reasons.append(f"{entry.duration:.1f}s of narration (+2)")

        scored.append(entry)

    # A cast change marks a new beat. Computed as a second pass because it
    # is the only signal that depends on the neighbouring block.
    order = sorted(by_block)
    for i, block_index in enumerate(order):
        if i == 0:
            continue
        prev = {s.speaker_self_id for s in by_block[order[i - 1]] if s.speaker_self_id}
        here = {s.speaker_self_id for s in by_block[block_index] if s.speaker_self_id}
        if here and prev and here != prev:
            entry = scored[i]
            entry.score += 1
            entry.reasons.append("cast change from previous block (+1)")

    return scored


def select_clip_blocks(
    scored: list[BlockScore],
    *,
    limit: int = CLIPS_PER_CHAPTER,
    min_score: int = MIN_IMPACT_SCORE,
) -> list[BlockScore]:
    """The blocks that get a cutaway: highest scoring, never adjacent.

    Ties break toward the earlier block, so selection is deterministic
    across runs -- a chapter that re-rendered with its clips in different
    places would look like a bug to anyone comparing two takes.
    """
    ranked = sorted(
        (b for b in scored if b.score >= min_score),
        key=lambda b: (-b.score, b.block_index),
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
) -> list[ShotPlan]:
    """One `ShotPlan` per block that has both a rendered panel and dialogue
    or narration reaching audio.

    A block with spans but no panel (e.g. outside every tracked scene,
    `PanelCast` still returns an environment-only image, so it *would* have
    a panel) or a panel but no spans (a heading, filtered out upstream)
    contributes nothing here -- shots exist only where there is both
    something to show and something being said over it.

    `durations` (block index -> seconds of audio) feeds the pacing half of
    the impact score; pass the voice manifest's per-block sums. Without it
    the clips are placed on content cues alone.
    """
    by_block: dict[int, list[Span]] = {
        block_index: list(group)
        for block_index, group in itertools.groupby(chapter_spans, key=lambda s: s.block_index)
    }
    # Only blocks that actually have a panel can hold a shot, so score the
    # candidates rather than the whole chapter -- otherwise a cutaway can be
    # "selected" for a block that then falls through to nothing.
    candidates = {b: spans for b, spans in by_block.items() if b in panel_images}

    scored = score_blocks(candidates, durations)
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
