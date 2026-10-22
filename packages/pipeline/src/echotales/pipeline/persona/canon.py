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

#: Hand-authored appearance, **now empty on purpose** (decisions D5, 2026-10-22).
#:
#: These tables held Fang Yuan's and Klein's looks typed by hand and silently won over the book's text. For Klein
#: they said "deep grey" eyes and a "black formal trench coat" while chapter 1 says "Black hair, brown eyes, a linen
#: shirt, thinly built", so every v2 render drew grey eyes; Audrey and Melissa were hand-written too. The reader pass
#: (`reader/facts_pass.py`) now reads appearance from the text with an evidence quote, dated to the chapter that
#: states it. An override a person wants belongs in the correction log, where it is visible and reversible, not in
#: source code. The structures remain so `canon_for`/`apply_canon` keep their signatures; the wiki tier still applies.
#:
#: novel_id -> canonical label -> appearance attributes (`appearance_extract.APPEARANCE_KEYS`).
CANON_APPEARANCE: dict[str, dict[str, dict[str, str]]] = {}

#: novel_id -> canonical label -> body number -> attributes. Empty for the same reason as `CANON_APPEARANCE`.
CANON_BY_BODY: dict[str, dict[str, dict[int, dict[str, str]]]] = {}


def _body_index(persona_id: str | None) -> int | None:
    """The body number encoded in a persona id, if there is one."""
    if not persona_id or ":body" not in persona_id:
        return None
    try:
        return int(persona_id.rsplit(":body", 1)[1])
    except ValueError:
        return None


def canon_for(
    novel_id: str, label: str, persona_id: str | None = None, *, wiki: bool = True
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

    base = dict(load_wiki_canon(novel_id).get(label, {})) if wiki else {}
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
    *,
    position: float | None = None,
    first_appearance: float | None = None,
) -> dict[str, str]:
    """Overlay canon onto extracted attributes.

    Canon wins key by key rather than wholesale, so a character with a
    canon entry still keeps any extracted attribute the entry does not
    mention -- the table is allowed to be partial.

    B4 (CHIMERA backlog): `wiki_canon.py`'s docstring promises that every
    imported trait is dated to the character's first appearance, but the
    import carries no date. When BOTH `position` and `first_appearance` are
    given, the wiki tier is dropped before the character first appears (the
    hand-authored table is body-aware and unaffected). Omitting either keeps
    the shipped, undated behaviour. This is only the dating rule: the wiki
    describes the character as a whole-novel reader remembers them and is
    still body-blind (no per-body wiki traits exist), which stays open.
    """
    wiki = not (position is not None and first_appearance is not None and position < first_appearance)
    canon = canon_for(novel_id, label, persona_id, wiki=wiki)
    if not canon:
        return extracted
    merged = dict(extracted)
    merged.update(canon)
    return merged
