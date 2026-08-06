"""Rule-based narrative-boundary markers (plans.md §6 Phase 2).

**Which phenomena appear is a property of the individual novel, not of its
genre.** This distinction is easy to get wrong and expensive when you do:

- *Dream realms* are a device of one specific novel in this corpus. They are
  **not** a cultivation-genre feature — most cultivation novels have no dream
  mechanic at all.
- *Transferable titles* really are broadly cultivation-typical, but a given
  novel may never transfer one.
- *Regression loops*, *system windows* and *constellation epithets* belong to
  other traditions entirely.

So the patterns below are **defaults, not universals**. `MarkerSet` makes them
per-novel, and a novel without a given device should simply carry no patterns
for it — a detector hunting for dream entries in a novel that has none produces
only false positives, and each one mints a spurious timeline that later facts
get attached to.

Where a device *is* present, it is usually signalled with a fixed formula, and
that regularity is what makes rule-first detection viable. An LLM pass covers
the implicit boundaries.

**Asymmetric thresholds** (plans.md §6 Phase 2, revised):

- *Explicitly signalled* boundaries → aggressive detection, low threshold.
  Missing one merges a separate-timeline persona into the main-timeline self,
  and that bad binding then poisons the gazetteer for the rest of the volume.
- *Implicitly signalled* boundaries → conservative, high confidence required.
  A false positive costs one spurious timeline; a miss costs one temporal
  misattribution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from echotales.core.enums import NarrativeLayer, SegmentType


class MarkerKind(StrEnum):
    ENTER_DREAM = "ENTER_DREAM"
    EXIT_DREAM = "EXIT_DREAM"
    ENTER_FLASHBACK = "ENTER_FLASHBACK"
    EXIT_FLASHBACK = "EXIT_FLASHBACK"
    ENTER_VISION = "ENTER_VISION"
    TIME_SKIP = "TIME_SKIP"
    SCENE_BREAK = "SCENE_BREAK"


@dataclass(frozen=True, slots=True)
class Marker:
    kind: MarkerKind
    block_index: int
    offset: int
    text: str
    confidence: float


def _compile(patterns: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


# Dream-realm entry. In RI this is a fixed formula, which is why it is treated
# as high confidence rather than suggestive.
_ENTER_DREAM = _compile(
    (
        r"\bhis vision (?:changed|blurred|darkened|shifted)\b",
        r"\bher vision (?:changed|blurred|darkened|shifted)\b",
        r"\bentered the dream realm\b",
        r"\bwas pulled into (?:the |a )?dream\b",
        r"\bthe dream realm (?:began|started|unfolded)\b",
        r"\bfell into (?:a |the )?dream\b",
        r"\bactivated the .{0,30}dream .{0,20}gu\b",
        r"\bthe scene before (?:him|her) (?:changed|shifted|transformed)\b",
        r"\bwhen (?:he|she) opened (?:his|her) eyes (?:again )?,? (?:he|she) (?:was|found)\b",
    )
)

_EXIT_DREAM = _compile(
    (
        r"\bthe dream (?:realm )?(?:faded|ended|collapsed|shattered|dissolved)\b",
        r"\b(?:he|she) (?:awoke|awakened|woke up)\b",
        r"\b(?:left|exited|withdrew from) the dream realm\b",
        r"\bthe memory faded\b",
        r"\breturned to reality\b",
        r"\bthe vision (?:faded|ended|cleared)\b",
        r"\bback in the real world\b",
    )
)

# Flashback openers. Temporal adverbials plus pluperfect framing.
_ENTER_FLASHBACK = _compile(
    (
        r"\b(?:many |several |a few )?(?:years|months|days|decades|centuries) (?:ago|earlier|before)\b",
        r"\bback (?:then|when)\b",
        r"\bin (?:his|her|their) (?:previous|past|former) life\b",
        r"\b(?:he|she) recalled (?:that|how|the)\b",
        r"\b(?:he|she) remembered (?:that|how|the)\b",
        r"\bmemories? (?:of|from) .{0,40}(?:surfaced|resurfaced|flooded|returned)\b",
        r"\bat that time\b",
        r"\bthinking back\b",
        r"\bonce upon a time\b",
        r"\bin (?:those|olden) days\b",
    )
)

_EXIT_FLASHBACK = _compile(
    (
        r"\b(?:returning|back) to the present\b",
        r"\bthe memory (?:faded|ended|receded)\b",
        r"\b(?:his|her) thoughts returned\b",
        r"\bsnapped? (?:back )?(?:out of|to) (?:it|his|her)\b",
        r"\bpresent day\b",
    )
)

_ENTER_VISION = _compile(
    (
        r"\ba vision (?:appeared|formed|came)\b",
        r"\bsaw (?:a |the )?(?:vision|prophecy|omen)\b",
        r"\bthe (?:prophecy|divination) (?:showed|revealed)\b",
        r"\bin (?:his|her) mind's eye\b",
        r"\bforesaw\b",
    )
)

# Time skips. Distinct from flashbacks: the story moves *forward* past
# unobserved events, and the graph needs a marker so later state changes are
# not misread as contradictions.
_TIME_SKIP = _compile(
    (
        r"\b(?:three|four|five|six|seven|eight|nine|ten|\d+) (?:years|months|days|weeks) (?:later|passed|went by)\b",
        r"\b(?:a|one|two) (?:year|month|day|week|decade)s? (?:later|passed|went by)\b",
        r"\btime (?:passed|flew|flowed)\b",
        r"\bin the blink of an eye,? .{0,30}(?:years|months|days)\b",
        r"\bbefore (?:he|she|they) knew it,? .{0,30}(?:years|months|days)\b",
        r"\bthe following (?:year|month|spring|summer|autumn|winter)\b",
        r"\bseasons? (?:changed|passed)\b",
    )
)

_SCENE_BREAK = re.compile(r"^\s*(?:\*\s*\*\s*\*|-{3,}|—{3,}|=+|~+|#+)\s*$")


#: Confidence tiers. Explicit devices are signalled by fixed formulae and are
#: detected aggressively; implicit ones need corroboration because their cues
#: double as ordinary narration.
_EXPLICIT_CONFIDENCE = 0.85
_IMPLICIT_CONFIDENCE = 0.5

_ALL_PATTERNS: tuple[tuple[MarkerKind, re.Pattern[str], float], ...] = (
    # Explicitly signalled: a fixed formula announces the transition. Detected
    # aggressively -- a miss merges a separate-timeline persona into the main
    # self and poisons the gazetteer thereafter.
    (MarkerKind.ENTER_DREAM, _ENTER_DREAM, _EXPLICIT_CONFIDENCE),
    (MarkerKind.EXIT_DREAM, _EXIT_DREAM, 0.8),
    (MarkerKind.ENTER_VISION, _ENTER_VISION, 0.7),
    (MarkerKind.TIME_SKIP, _TIME_SKIP, 0.75),
    # Implicitly signalled: "years ago" appears in ordinary dialogue constantly,
    # so these stay below the promotion threshold on their own.
    (MarkerKind.ENTER_FLASHBACK, _ENTER_FLASHBACK, _IMPLICIT_CONFIDENCE),
    (MarkerKind.EXIT_FLASHBACK, _EXIT_FLASHBACK, _IMPLICIT_CONFIDENCE),
)

#: Devices that are novel-specific rather than genre-wide. Enabled per novel.
#:
#: Dream realms in particular are a device of one novel in this corpus, not a
#: cultivation-genre feature. Hunting for them in a novel that has none yields
#: only false positives, each of which mints a spurious timeline.
OPTIONAL_KINDS: frozenset[MarkerKind] = frozenset(
    {MarkerKind.ENTER_DREAM, MarkerKind.EXIT_DREAM, MarkerKind.ENTER_VISION}
)

#: Devices present in essentially any prose narrative.
UNIVERSAL_KINDS: frozenset[MarkerKind] = frozenset(
    {
        MarkerKind.ENTER_FLASHBACK,
        MarkerKind.EXIT_FLASHBACK,
        MarkerKind.TIME_SKIP,
        MarkerKind.SCENE_BREAK,
    }
)


@dataclass(frozen=True, slots=True)
class MarkerSet:
    """Which narrative devices to look for in a given novel.

    Defaults to universal devices only. A novel that actually uses dreams or
    visions opts in, rather than every novel paying the false-positive cost of
    detectors for devices it does not have.
    """

    enabled: frozenset[MarkerKind] = UNIVERSAL_KINDS

    @classmethod
    def universal(cls) -> MarkerSet:
        return cls(enabled=UNIVERSAL_KINDS)

    @classmethod
    def with_devices(cls, *kinds: MarkerKind) -> MarkerSet:
        return cls(enabled=UNIVERSAL_KINDS | frozenset(kinds))

    @classmethod
    def all_devices(cls) -> MarkerSet:
        return cls(enabled=UNIVERSAL_KINDS | OPTIONAL_KINDS)

    def allows(self, kind: MarkerKind) -> bool:
        return kind in self.enabled


#: Backwards-compatible default. Enables every device, which is right for the
#: one novel in this corpus that uses dreams and harmless-but-noisy elsewhere.
#: Prefer passing an explicit `MarkerSet` per novel.
DEFAULT_MARKER_SET = MarkerSet.all_devices()


def find_markers(
    text: str,
    block_index: int = 0,
    marker_set: MarkerSet | None = None,
) -> list[Marker]:
    """Find narrative-boundary markers in one block of text.

    `marker_set` restricts detection to devices the novel actually uses.
    """
    active = marker_set or DEFAULT_MARKER_SET

    if _SCENE_BREAK.match(text.strip()):
        return [
            Marker(
                kind=MarkerKind.SCENE_BREAK,
                block_index=block_index,
                offset=0,
                text=text.strip(),
                confidence=1.0,
            )
        ]

    out: list[Marker] = []
    for kind, pattern, confidence in _ALL_PATTERNS:
        if not active.allows(kind):
            continue
        for match in pattern.finditer(text):
            out.append(
                Marker(
                    kind=kind,
                    block_index=block_index,
                    offset=match.start(),
                    text=match.group(0),
                    confidence=confidence,
                )
            )
    out.sort(key=lambda m: m.offset)
    return out


ENTRY_KINDS = frozenset(
    {MarkerKind.ENTER_DREAM, MarkerKind.ENTER_FLASHBACK, MarkerKind.ENTER_VISION}
)
EXIT_KINDS = frozenset({MarkerKind.EXIT_DREAM, MarkerKind.EXIT_FLASHBACK})

LAYER_FOR_ENTRY: dict[MarkerKind, tuple[SegmentType, NarrativeLayer]] = {
    MarkerKind.ENTER_DREAM: (SegmentType.DREAM_OTHER, NarrativeLayer.DREAM_OTHER),
    MarkerKind.ENTER_FLASHBACK: (SegmentType.FLASHBACK_OWN, NarrativeLayer.FLASHBACK_OWN),
    MarkerKind.ENTER_VISION: (SegmentType.VISION, NarrativeLayer.VISION),
}

EXIT_FOR_ENTRY: dict[MarkerKind, MarkerKind] = {
    MarkerKind.ENTER_DREAM: MarkerKind.EXIT_DREAM,
    MarkerKind.ENTER_FLASHBACK: MarkerKind.EXIT_FLASHBACK,
    MarkerKind.ENTER_VISION: MarkerKind.EXIT_FLASHBACK,
}
