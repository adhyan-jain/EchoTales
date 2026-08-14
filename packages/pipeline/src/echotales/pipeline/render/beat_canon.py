"""Hand-authored staging for panels a general-purpose director gets wrong.

**Same argument as `persona/canon.py`, one layer up.** That module exists
because an extractor reading scattered narration cannot recover a
character's canonical look as well as someone who has read the book. This
module is the same claim about a *moment*: some panels are not "whatever
this block's prose literally says," they are a specific, iconic staging a
reader holds in their head, and the automated pipeline has no way to invent
it from text alone.

**The two cases this exists for, both from RI ch1, both requested after
watching the composed video rather than a single generation:**

- The opening confrontation. The prose is dialogue-only ("hand over the
  Cicada or I'll give you a quick death") with no resolved speaker in that
  block, so `get_panel_cast` correctly returns an empty foreground and
  `shot_style` correctly routes to a scene shot -- but a scene shot with no
  staging hint still has nothing to draw beyond generic scenery. The
  moment is a lone figure surrounded by an armed faction; that framing has
  to be said, because nothing upstream of this module can derive it from a
  block whose only content is one hostile line of dialogue.
- The rebirth line. "With the use of the Spring Autumn Cicada I have been
  reborn" is extracted correctly (§4.27/§4.28) and gets its own panel
  correctly (§4.28's transformation cue) -- but the *visual* the reader
  wants is not implied by that sentence: blood pooled where he stands, a
  bloody trail leading to it, a calm and expressionless face, the Cicada
  itself glowing and held up in both palms. None of that is stated in the
  surrounding prose closely enough for extraction to find it; it is staged
  the way a reader who knows the scene would stage it, exactly `canon.py`'s
  argument.

**Deliberately keyed to exact block ranges in one novel, not a general
mechanism.** A `beat_canon` seeded generically ("panels about confrontation
get warriors") would drift from what the specific chapter says the moment
it stopped matching this one; better to have zero coverage on an
unseeded block than a wrong generic guess -- the same trade-off
`persona/canon.py::CANON_APPEARANCE` makes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BeatCanonEntry:
    """One block range's hand-authored staging."""

    block_from: int
    block_to: int
    #: Prepended to the beat text before prompt assembly -- so it is
    #: present for both the mechanical `build_image_prompt` path and the
    #: LLM-directed `direct_beat` path (the model reads the same staging
    #: hint as part of the beat it is asked to direct).
    staging: str
    #: Force a specific framing (`"establishing"` or `"scene"`), or None to
    #: let `shot_style` decide as usual. The opening needs `"establishing"`
    #: for the wide mountain-stronghold view; the rebirth panel needs
    #: `"scene"` because its default framing (a dialogue block's tight face
    #: close-up) would crop out the raised palms and the cicada, which are
    #: the point of the staging.
    style_override: str | None = None


#: novel_id -> chapter -> ordered entries. Ordered so the first matching
#: range wins even if ranges were ever adjacent, though none overlap today.
BEAT_CANON: dict[str, dict[float, list[BeatCanonEntry]]] = {
    "reverend-insanity": {
        1.0: [
            BeatCanonEntry(
                block_from=0,
                block_to=1,
                staging=(
                    "Wide establishing view of a xianxia mountain stronghold "
                    "under siege at dusk. A lone robed figure stands at the "
                    "center, surrounded by a faction of armed warlords and "
                    "warrior women, some standing on the ground with drawn "
                    "swords, some flying overhead on blades and talismans, "
                    "closing in on him."
                ),
                style_override="establishing",
            ),
            BeatCanonEntry(
                # Block 83 only, not 82: 82 is scene-setting narration
                # ("In short, it is the ability to be reborn") where Fang
                # Yuan is not the block's own resolved subject, while 83 is
                # his own spoken line and the one block in this beat where
                # `get_panel_cast` actually resolves him present -- which
                # is what earns the panel its "1boy" tag and appearance
                # clause. Attaching the directive there instead of
                # spanning both keeps that machinery intact rather than
                # overriding around it.
                block_from=83,
                block_to=83,
                # **An earlier version of this entry forced "no weapon, no
                # sword" and named the Cicada an "insect" outright, on the
                # assumption that a cicada must look like a literal bug.
                # That assumption was never checked against the source and
                # was wrong to make.** RI ch1-2 never describes the Spring
                # Autumn Cicada's physical form -- it is introduced only
                # functionally, as the seventh-ranked of the Ten Great
                # Mystical Gu, a life form Fang Yuan *cultivates*, not an
                # object with a stated shape. Gu in this novel are
                # insect-derived but routinely depicted as strange,
                # weapon-like or crystalline artifacts rather than mundane
                # bugs (the checkpoint's own instinct here, unprompted).
                # Insisting on a literal insect was inventing a detail the
                # text does not support -- exactly what
                # `appearance_extract.py`'s "never invent a detail that is
                # not there" discipline exists to prevent, applied to a
                # hand-authored directive instead of a model's extraction.
                # Left open rather than re-forced in either direction.
                staging=(
                    "standing in a pool of blood, robes soaked and torn, "
                    "face calm and expressionless. Both palms cupped "
                    "before his chest, holding a small glowing Gu artifact "
                    "that emits a soft light, gazing down at it plainly."
                ),
                # A tight face close-up -- what a dialogue block would get
                # by default -- crops out the raised palms and the cicada,
                # which are the point of the staging. Medium shot instead,
                # so the pose reads.
                style_override="scene",
            ),
        ],
    },
}


def beat_canon_for(novel_id: str, chapter: float, block_index: int) -> BeatCanonEntry | None:
    """The staging entry covering `block_index`, if this block has one."""
    for entry in BEAT_CANON.get(novel_id, {}).get(chapter, []):
        if entry.block_from <= block_index <= entry.block_to:
            return entry
    return None
