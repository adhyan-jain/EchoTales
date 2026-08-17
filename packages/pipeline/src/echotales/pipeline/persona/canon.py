"""Hand-authored canonical appearances, outranking everything extracted.

**Why this exists, stated plainly: a reader beats an extractor.** The
appearance extractor reads scattered narration and produces something
defensible from the sentences it sampled -- but for a novel's most
recognisable characters that is a poor substitute for what a reader (or the
novel's wiki, or the author's own art) already knows. Measured on RI:
extraction gave Fang Yuan "green robes" and short dishevelled hair, when the
character is canonically 188 cm, lean, with **waist-length midnight black
hair** and jet-black cold narrow eyes. Nobody reading the novel would accept
the generated version, and no amount of prompt tuning fixes a wrong premise.

So this is a small, deliberately manual table. It is **not** a fallback and
**not** a default -- `attire.py::APPEARANCE_DEFAULTS` is the thing that fills
silence. This overrides *speech*: where a canon entry exists it wins over the
model's reading, because it is better evidence.

Keyed by canonical label rather than entity id, because ids are minted per
resolve run (`resolve/runner.py` counts from scratch every time) and would
not survive a re-run, whereas "Fang Yuan" is stable across every database
this project will ever build.

Adding a character here is cheap and is the highest-leverage thing anyone
can do for visual quality on a novel they have actually read.
"""

from __future__ import annotations

#: novel_id -> canonical label -> appearance attributes.
#:
#: Keys are `appearance_extract.APPEARANCE_KEYS`, so a canon entry drops
#: into the same slots an extracted one would and needs no special handling
#: downstream.
CANON_APPEARANCE: dict[str, dict[str, dict[str, str]]] = {
    "reverend-insanity": {
        "Fang Yuan": {
            "hair_color": "midnight black",
            "hair_style": "very long straight hair down to the waist",
            "eye_color": "jet black, cold and narrow",
            "skin_tone": "pale",
            "height_build": "tall and lean, 188cm",
            # Inert for Fang Yuan today -- `CANON_BY_BODY` overrides this key
            # for both his bodies -- but kept matching the look the author
            # actually confirmed they wanted (serious, cold, ruthless), not
            # the "plain ordinary" wording that was tried and reverted (see
            # `CANON_BY_BODY` below for why).
            "distinguishing_features": (
                "cold expressionless stare, utterly ruthless demeanour"
            ),
            # No "typical_attire" entry, deliberately: `appearance_extract.py`
            # already extracted "green robes" from Fang Yuan's own ch1
            # death-scene text, grounded evidence, not a hallucination (its
            # own docstring on `TRANSIENT_KEYS` uses this exact case as the
            # example of *correct* standing-garment extraction -- green is
            # the garment, "torn to shreds" is the transient condition that
            # correctly got filtered out already). This table's job is
            # permanent physical traits a reader already knows outrank an
            # extractor's guess on; attire that varies is not that -- an
            # earlier version hardcoded "simple robes with wide sleeves"
            # here, which silently overwrote the correct extracted colour
            # with a colourless generic on every single reference sheet.
        },
    },
}


#: novel_id -> canonical label -> body index -> attributes that differ **for
#: that body only**, layered on top of the character's entry above.
#:
#: **This is where a body change becomes visible.** `persona/split.py` finds
#: that Fang Yuan is reborn in chapter 1 and binds a second persona from
#: there; the graph knows the two bodies are different, but nothing in the
#: prose ever states what the fifteen-year-old looks like -- RI's narration
#: describes his *death scene* in chapter 1 and almost nothing afterwards
#: (§4.24's honest caveat on that output). An extractor cannot invent what
#: the text does not say, and a reader can simply write it down.
#:
#: Sparse by design: a body with no entry here inherits the character's
#: appearance unchanged, which is right for the overwhelming majority of
#: characters, who have exactly one body.
CANON_BY_BODY: dict[str, dict[str, dict[int, dict[str, str]]]] = {
    "reverend-insanity": {
        "Fang Yuan": {
            # Body 1: the 500-year-old demonic cultivator of chapter 1,
            # dying at the hands of the righteous factions.
            #
            # **The "plain ordinary" wording was tried and reverted.** A
            # version of this entry pushed hard on plainness in both the
            # text and `REFERENCE_STYLE`, and the author's own visual
            # judgement on the result was that it was worse on every axis
            # except clothing colour -- the original "serious, sharp
            # features" framing produced the image the author actually
            # wanted. Only the colour was ever really wrong (see
            # `CANON_APPEARANCE` above: no more hardcoded "simple robes",
            # extraction's real "green robes" flows through instead). Do
            # not re-add plainness language here without the author asking
            # for it again.
            1: {
                "height_build": "tall and lean, gaunt with age and injury",
                "current_condition": "gravely wounded, robes torn",
                "distinguishing_features": (
                    "aged, hollow-cheeked, cold expressionless stare, "
                    "utterly ruthless demeanour"
                ),
            },
            # Body 2: the same consciousness in his fifteen-year-old self,
            # from chapter 1's rebirth onward -- which is the entire book.
            2: {
                "height_build": "slim adolescent build, not yet grown",
                "distinguishing_features": (
                    "a boy's face wearing an adult's cold, ruthless "
                    "expression"
                ),
            },
        },
    },
}


def _body_index(persona_id: str | None) -> int | None:
    """The body number encoded in a persona id, if there is one."""
    if not persona_id or ":body" not in persona_id:
        return None
    try:
        return int(persona_id.rsplit(":body", 1)[1])
    except ValueError:
        return None


def canon_for(
    novel_id: str, label: str, persona_id: str | None = None
) -> dict[str, str]:
    """Canonical appearance for this character, or an empty dict.

    With a `persona_id`, any body-specific overrides are layered on top --
    the character's entry describes who they are, the body entry describes
    which body the reader is looking at.

    **Three tiers, in this order: hand-authored > wiki > extraction.** The
    table below is typed by someone who read the novel and meant it; the
    wiki (`wiki_canon.py`, imported by an explicit command and cached to
    disk) is written by many hands and can be stale or wrong; extraction is
    a guess from whichever sentences it happened to sample. This function
    covers the first two -- `apply_canon` layers the pair over the third.
    """
    from echotales.pipeline.persona.wiki_canon import load_wiki_canon

    base = dict(load_wiki_canon(novel_id).get(label, {}))
    base.update(CANON_APPEARANCE.get(novel_id, {}).get(label, {}))
    index = _body_index(persona_id)
    if index is None:
        return base
    base.update(CANON_BY_BODY.get(novel_id, {}).get(label, {}).get(index, {}))
    return base


def apply_canon(
    novel_id: str,
    label: str,
    extracted: dict[str, str],
    persona_id: str | None = None,
) -> dict[str, str]:
    """Overlay canon onto extracted attributes.

    Canon wins key by key rather than wholesale, so a character with a
    canon entry still keeps any extracted attribute the entry does not
    mention -- the table is allowed to be partial.
    """
    canon = canon_for(novel_id, label, persona_id)
    if not canon:
        return extracted
    merged = dict(extracted)
    merged.update(canon)
    return merged
