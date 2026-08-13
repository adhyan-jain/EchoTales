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


def canon_for(novel_id: str, label: str) -> dict[str, str]:
    """Canonical appearance for this character, or an empty dict."""
    return CANON_APPEARANCE.get(novel_id, {}).get(label, {})


def apply_canon(novel_id: str, label: str, extracted: dict[str, str]) -> dict[str, str]:
    """Overlay canon onto extracted attributes.

    Canon wins key by key rather than wholesale, so a character with a
    canon entry still keeps any extracted attribute the entry does not
    mention -- the table is allowed to be partial.
    """
    canon = canon_for(novel_id, label)
    if not canon:
        return extracted
    merged = dict(extracted)
    merged.update(canon)
    return merged
