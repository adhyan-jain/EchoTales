"""Delivery-marker extraction (plans.md Section 6 Phase 4).

Non-negotiable #10: **delivery markers override scene-level sentiment.**

The canonical case is a protagonist repeatedly described as "expressionless"
during the most violent scenes in the novel. A scene-level sentiment model
reads the surrounding carnage and assigns a dramatic, high-arousal voice.
That is exactly wrong: the text is telling us he is flat, and the contrast
between the flatness and the carnage *is* the characterisation. Rendering him
dramatic destroys the effect the prose was built around.

So markers are extracted separately, carry an explicit `polarity`, and are
applied after scene sentiment rather than blended with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class DeliveryPolarity(StrEnum):
    """How a marker should modulate synthesis."""

    #: Suppress affect. Overrides scene sentiment outright.
    FLAT = "FLAT"
    #: Raise arousal (volume, pitch range, rate).
    HEIGHTENED = "HEIGHTENED"
    #: Lower volume, keep affect.
    HUSHED = "HUSHED"
    #: Affect present but negatively valenced.
    COLD = "COLD"
    #: Warm / positive valence.
    WARM = "WARM"
    #: Uncertain, hesitant delivery.
    HESITANT = "HESITANT"


# Ordered longest-first within each group so "said coldly" wins over "said".
_MARKERS: dict[str, DeliveryPolarity] = {
    # Flat -- these are the ones that must override scene sentiment.
    "expressionless": DeliveryPolarity.FLAT,
    "expressionlessly": DeliveryPolarity.FLAT,
    "without any emotion": DeliveryPolarity.FLAT,
    "without emotion": DeliveryPolarity.FLAT,
    "emotionlessly": DeliveryPolarity.FLAT,
    "emotionless": DeliveryPolarity.FLAT,
    "indifferently": DeliveryPolarity.FLAT,
    "indifferent": DeliveryPolarity.FLAT,
    "flatly": DeliveryPolarity.FLAT,
    "blandly": DeliveryPolarity.FLAT,
    "impassively": DeliveryPolarity.FLAT,
    "calmly": DeliveryPolarity.FLAT,
    "placidly": DeliveryPolarity.FLAT,
    "evenly": DeliveryPolarity.FLAT,
    "dispassionately": DeliveryPolarity.FLAT,
    "nonchalantly": DeliveryPolarity.FLAT,
    "casually": DeliveryPolarity.FLAT,
    # Heightened
    "shouted": DeliveryPolarity.HEIGHTENED,
    "screamed": DeliveryPolarity.HEIGHTENED,
    "shrieked": DeliveryPolarity.HEIGHTENED,
    "roared": DeliveryPolarity.HEIGHTENED,
    "bellowed": DeliveryPolarity.HEIGHTENED,
    "yelled": DeliveryPolarity.HEIGHTENED,
    "exclaimed": DeliveryPolarity.HEIGHTENED,
    "burst out": DeliveryPolarity.HEIGHTENED,
    "loudly": DeliveryPolarity.HEIGHTENED,
    "furiously": DeliveryPolarity.HEIGHTENED,
    "angrily": DeliveryPolarity.HEIGHTENED,
    "excitedly": DeliveryPolarity.HEIGHTENED,
    "urgently": DeliveryPolarity.HEIGHTENED,
    "frantically": DeliveryPolarity.HEIGHTENED,
    # Hushed
    "whispered": DeliveryPolarity.HUSHED,
    "murmured": DeliveryPolarity.HUSHED,
    "muttered": DeliveryPolarity.HUSHED,
    "mumbled": DeliveryPolarity.HUSHED,
    "softly": DeliveryPolarity.HUSHED,
    "quietly": DeliveryPolarity.HUSHED,
    "under his breath": DeliveryPolarity.HUSHED,
    "under her breath": DeliveryPolarity.HUSHED,
    "in a low voice": DeliveryPolarity.HUSHED,
    "faintly": DeliveryPolarity.HUSHED,
    # Cold
    "coldly": DeliveryPolarity.COLD,
    "icily": DeliveryPolarity.COLD,
    "sneered": DeliveryPolarity.COLD,
    "scoffed": DeliveryPolarity.COLD,
    "snorted": DeliveryPolarity.COLD,
    "mockingly": DeliveryPolarity.COLD,
    "sarcastically": DeliveryPolarity.COLD,
    "disdainfully": DeliveryPolarity.COLD,
    "contemptuously": DeliveryPolarity.COLD,
    "grimly": DeliveryPolarity.COLD,
    "darkly": DeliveryPolarity.COLD,
    "harshly": DeliveryPolarity.COLD,
    "sternly": DeliveryPolarity.COLD,
    # Warm
    "warmly": DeliveryPolarity.WARM,
    "gently": DeliveryPolarity.WARM,
    "kindly": DeliveryPolarity.WARM,
    "cheerfully": DeliveryPolarity.WARM,
    "happily": DeliveryPolarity.WARM,
    "laughed": DeliveryPolarity.WARM,
    "chuckled": DeliveryPolarity.WARM,
    "smiled": DeliveryPolarity.WARM,
    "smilingly": DeliveryPolarity.WARM,
    # Hesitant
    "hesitantly": DeliveryPolarity.HESITANT,
    "hesitated": DeliveryPolarity.HESITANT,
    "stammered": DeliveryPolarity.HESITANT,
    "uncertainly": DeliveryPolarity.HESITANT,
    "nervously": DeliveryPolarity.HESITANT,
    "awkwardly": DeliveryPolarity.HESITANT,
    "reluctantly": DeliveryPolarity.HESITANT,
}

_MARKER_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in sorted(_MARKERS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DeliveryMarker:
    text: str
    polarity: DeliveryPolarity
    start: int
    end: int


#: Quoted speech, in the several quote styles this project's sources use.
_QUOTED_RE = re.compile(r"[\u201c\u201d\"\u2018\u2019'][^\u201c\u201d\"]*?[\u201c\u201d\"]")


def _speech_tag_only(text: str) -> str:
    """The text with quoted speech blanked out, offsets preserved.

    **A delivery marker is a property of the speech tag, never of the line
    itself.** RI ch1 block 0 is a besieging cultivator shouting "Fang Yuan,
    quietly hand over the Spring Autumn Cicada and I'll give you a quick
    death!" -- "quietly" is what he is *demanding*, not how he says it, and
    matching inside the quote marked the line HUSHED and whispered a siege
    threat. Six of chapter 1's twenty-seven dialogue lines were mis-marked
    this way.

    Blanked rather than removed so every reported offset still indexes the
    caller's original string.
    """
    return _QUOTED_RE.sub(lambda m: " " * len(m.group(0)), text)


def extract_delivery_markers(text: str) -> list[DeliveryMarker]:
    """Find delivery markers in a narration span.

    Overlapping matches are resolved longest-first by the alternation ordering,
    so "in a low voice" is not reduced to "low".
    """
    out: list[DeliveryMarker] = []
    taken: list[tuple[int, int]] = []
    for match in _MARKER_RE.finditer(_speech_tag_only(text)):
        start, end = match.span()
        if any(s <= start < e or s < end <= e for s, e in taken):
            continue
        taken.append((start, end))
        out.append(
            DeliveryMarker(
                text=match.group(0),
                polarity=_MARKERS[match.group(0).casefold()],
                start=start,
                end=end,
            )
        )
    return out


def dominant_polarity(markers: list[DeliveryMarker]) -> DeliveryPolarity | None:
    """Pick the marker that should drive synthesis.

    FLAT wins outright when present. That is the whole point of the rule: a
    line tagged both "calmly" and appearing in a violent scene must render
    flat, and a naive majority vote or averaging would let the surrounding
    drama back in through the side door.
    """
    if not markers:
        return None
    for marker in markers:
        if marker.polarity is DeliveryPolarity.FLAT:
            return DeliveryPolarity.FLAT
    return markers[0].polarity
