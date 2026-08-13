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
            # Canonically *plain* -- the character is described as ordinary
            # looking, and a striking face would be as wrong as a cute one.
            "distinguishing_features": (
                "plain ordinary features, cold expressionless stare, "
                "utterly ruthless demeanour"
            ),
            "typical_attire": "simple robes with wide sleeves",
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
    """
    base = dict(CANON_APPEARANCE.get(novel_id, {}).get(label, {}))
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
