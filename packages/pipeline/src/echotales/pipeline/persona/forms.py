"""A character's *current form*, which is not the same as their body.

`persona/split.py` already models the case where a character permanently
becomes someone else to look at: a rebirth, a stolen body, an epoch boundary
after which every panel should use the new appearance. That machinery is
deliberately heavy -- it mints a persona, binds it from a story position,
and everything downstream follows it forever.

**Transformations are the opposite shape.** A cultivator who turns into a
beast mid-fight, sprouts six zombie arms for one exchange, or shifts halfway
and back again within a page is not a new body: it is the same persona
wearing a temporary form, and it must revert without leaving a trace. Using
the body machinery for it would be wrong in both directions -- a permanent
binding for a temporary state, and a persona split for something the story
treats as one continuous character.

So a form is a **per-panel overlay**: detected from the panel's own prose,
applied on top of the character's standing appearance, and gone the moment
the prose stops saying it. Three things follow from that:

1. **Reversion is free.** A panel whose blocks do not mention the
   transformation simply has no overlay. Nothing has to detect "he changed
   back", which is the detection that would otherwise be missed constantly
   -- prose announces a transformation loudly and reverts to human in
   silence.
2. **Identity survives.** Voice casting binds to the persona
   (`voice/runner.py`), never to the form, so a transformed character keeps
   their voice -- which is also the right answer for the twin-alias case,
   where the disguise changes the name and not the person.
3. **Partial forms are first class.** "Six arms sprouted from his back" is
   not "he became a monster"; the human description still applies, with the
   arms added. `FormOverlay.replaces_body` is what separates the two.

A long-term transformation -- one that lasts arcs rather than exchanges --
is a *body*, and belongs in `persona/split.py` with a canon entry. The line
between them is duration, and duration is a judgement this module does not
attempt: it describes what the current passage says, and nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FormOverlay:
    """A temporary appearance layered over a character's standing look."""

    name: str
    #: Appended to the character's appearance clause in the prompt.
    clause: str
    #: True when the form replaces the human description rather than adding
    #: to it -- a full beast is not a man with fur.
    replaces_body: bool = False
    #: Danbooru-style tags this form needs, and negatives it must lift. A
    #: transformed character legitimately has claws or extra arms, and the
    #: standing negative prompt forbids exactly those.
    tags: tuple[str, ...] = ()
    lifts_negatives: tuple[str, ...] = ()


#: Ordered: the first pattern that matches wins, so a partial transformation
#: is tested before the full one it contains ("half-transformed into a
#: beast" must not read as "beast").
FORMS: tuple[tuple[re.Pattern[str], FormOverlay], ...] = (
    (
        re.compile(
            r"\b(?:half[- ]transformed|partial(?:ly)? transform\w*|"
            r"mid[- ]transformation)\b",
            re.I,
        ),
        FormOverlay(
            "partial",
            "caught mid-transformation, half human and half beast, "
            "one arm monstrous",
            tags=("monster boy",),
            lifts_negatives=("extra limbs", "extra arms"),
        ),
    ),
    (
        # Extra arms are RI's zombie signature and are usually *added* to an
        # otherwise human figure, which is why this is not `replaces_body`.
        re.compile(
            r"\b(?:six|eight|four|multiple|several)\s+(?:zombie\s+)?arms\b"
            r"|\barms sprouted\b|\bextra arms\b",
            re.I,
        ),
        FormOverlay(
            "many-armed",
            "multiple additional arms sprouting from the back",
            tags=("multiple arms", "extra arms"),
            lifts_negatives=("extra limbs", "extra arms"),
        ),
    ),
    (
        re.compile(r"\b(?:immortal zombie|zombified|became a zombie|zombie form)\b", re.I),
        FormOverlay(
            "zombie",
            "corpse-pale skin, sunken eyes, undead flesh, towering frame",
            replaces_body=True,
            tags=("undead",),
            lifts_negatives=("rotting flesh", "undead", "corpse"),
        ),
    ),
    (
        re.compile(
            r"\b(?:transformed into|turned into|shifted into|took the form of)\s+"
            r"(?:a|an|his|her|the)?\s*(?:giant\s+)?(?:beast|wolf|tiger|serpent|"
            r"dragon|ape|bear)\b",
            re.I,
        ),
        FormOverlay(
            "beast",
            "transformed into a great beast, fur and claws, bestial head",
            replaces_body=True,
            tags=("monster", "furry"),
            lifts_negatives=("animal head", "fur", "claws", "monster", "creature"),
        ),
    ),
)


@dataclass(slots=True)
class FormReport:
    """What the prompt builder needs to render a transformation."""

    overlay: FormOverlay | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.overlay is not None

    def apply_to(self, appearance: str) -> str:
        """The character's appearance clause under this form."""
        if self.overlay is None:
            return appearance
        if self.overlay.replaces_body:
            return self.overlay.clause
        return f"{appearance}, {self.overlay.clause}" if appearance else self.overlay.clause

    def filtered_negative(self, negative: str) -> str:
        """`negative` with the terms this form legitimately needs removed.

        **Without this a transformation cannot render at all.** The standing
        negative prompt forbids extra limbs, claws and undead flesh, which
        is right for every ordinary panel and is precisely the content of
        these panels.
        """
        if self.overlay is None:
            return negative
        lifted = {term.casefold() for term in self.overlay.lifts_negatives}
        kept = [
            part.strip()
            for part in negative.split(",")
            if part.strip() and part.strip().casefold() not in lifted
        ]
        return ", ".join(kept)


def detect_form(text: str) -> FormReport:
    """The transformation this passage describes, if any.

    Reads the panel's own prose only. A form is in effect for exactly as
    long as the text says so -- see the module docstring on why reversion is
    deliberately not detected.
    """
    for pattern, overlay in FORMS:
        if pattern.search(text or ""):
            return FormReport(overlay=overlay, tags=list(overlay.tags))
    return FormReport()
