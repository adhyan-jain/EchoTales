"""Special-case detectors (plans.md Section 6 Phase 6).

These run in parallel with scoring and produce **events**, not links. They are
what make the temporal and epistemic model earn its complexity: without them a
transferred title silently merges two holders, an impostor is recorded as
genuine, and a reveal never propagates backwards.

Each detector maps onto a distinct event type, and the mapping matters:

| Detector   | Event            | Meaning |
|------------|------------------|---------|
| transfer   | `rebind`         | the title moved to a new holder |
| deception  | binding `CLAIMED`| asserted, not established |
| reveal     | `merge`          | two records were always one entity |
| death      | `close_interval` | the persona binding ends |
| reputation | `reputation_spread` | the audience scope widened |

Note what is *not* here: a retraction. "Was never true" is emitted only when a
deception is exposed, and it is deliberately a different operation from closing
an interval (non-negotiable #5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from echotales.core.enums import EventType, TruthStatus
from echotales.pipeline.mentions.lexicon import Lexicon

_NAME = r"[A-Z][\w’'\-]*(?:\s+[A-Z][\w’'\-]*){0,3}"


class DetectorKind(StrEnum):
    TRANSFER = "TRANSFER"
    DECEPTION = "DECEPTION"
    REVEAL = "REVEAL"
    DEATH = "DEATH"
    RESURRECTION = "RESURRECTION"
    REPUTATION = "REPUTATION"


@dataclass(frozen=True, slots=True)
class DetectorHit:
    kind: DetectorKind
    event_type: EventType
    subject: str
    object: str | None
    evidence: str
    offset: int
    confidence: float
    truth_status: TruthStatus | None = None


# --- transfer ---------------------------------------------------------------
# "X inherited the title", "the new Sect Master", "X succeeded Y".
_TRANSFER = re.compile(
    r"(?:(?P<subject>" + _NAME + r")\s+)?"
    r"(?:inherited the title|succeeded|took over as|was appointed|became the next|"
    r"ascended to the position|passed the mantle|the new)\b"
    r"(?:\s+(?P<object>" + _NAME + r"))?",
    re.IGNORECASE,
)

# --- deception --------------------------------------------------------------
_DECEPTION = re.compile(
    r"(?:(?P<subject>" + _NAME + r")\s+)?"
    r"(?:claimed to be|posing as|disguised as|pretending to be|"
    r"under the guise of|assumed the identity of|impersonating|going by the name)"
    r"(?:\s+(?P<object>" + _NAME + r"))?",
    re.IGNORECASE,
)

# --- reveal -----------------------------------------------------------------
# The highest-value detector: this is the case a first-appearance constraint
# would forbid outright.
_REVEAL = re.compile(
    r"(?:(?P<subject>" + _NAME + r")\s+)?"
    r"(?:was none other than|had always been|his true name was|her true name was|"
    r"his real identity|her real identity|in truth,? (?:he|she) was|"
    r"also known as|formerly called|turned out to be)"
    r"(?:\s+(?P<object>" + _NAME + r"))?",
    re.IGNORECASE,
)

# --- death / departure ------------------------------------------------------
_DEATH = re.compile(
    r"(?P<subject>" + _NAME + r")\s+(?:\w+\s+){0,2}?"
    r"(?:died|perished|fell|was killed|was slain|breathed (?:his|her) last|"
    r"passed away|met (?:his|her) end|was no more)\b"
)

_RESURRECTION = re.compile(
    r"(?P<subject>" + _NAME + r")\s+(?:\w+\s+){0,2}?"
    r"(?:was reborn|returned from the dead|revived|resurrected|rose again|"
    r"came back to life)\b",
    re.IGNORECASE,
)

# --- reputation -------------------------------------------------------------
_REPUTATION = re.compile(
    r"(?P<subject>" + _NAME + r")(?:'s)?\s+(?:\w+\s+){0,3}?"
    r"(?:name (?:was |had )?(?:spread|become known|resounded)|"
    r"became (?:famous|renowned|known) (?:throughout|across|in)|"
    r"reputation (?:spread|grew)|was now known (?:throughout|across))",
    re.IGNORECASE,
)


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    return text or None


def detect_transfers(text: str, lexicon: Lexicon | None = None) -> list[DetectorHit]:
    """Find title transfers.

    A transfer closes the previous holder's interval and opens a new one. It is
    emphatically not a retraction: the previous holder genuinely held the title,
    and a query at an earlier position must still say so.
    """
    out: list[DetectorHit] = []
    for match in _TRANSFER.finditer(text):
        subject = _clean(match.group("subject"))
        obj = _clean(match.group("object"))
        if not subject and not obj:
            continue
        out.append(
            DetectorHit(
                kind=DetectorKind.TRANSFER,
                event_type=EventType.REBIND,
                subject=subject or obj or "",
                object=obj if subject else None,
                evidence=match.group(0).strip(),
                offset=match.start(),
                confidence=0.7,
            )
        )
    return out


def detect_deceptions(text: str, lexicon: Lexicon | None = None) -> list[DetectorHit]:
    """Find asserted-but-unverified identities.

    Emits a binding with `truth_status=CLAIMED` rather than `TRUE`. The
    distinction is what lets the graph later record either that the claim was
    exposed (retraction) or that it was correct after all, without having to
    guess now.
    """
    out: list[DetectorHit] = []
    for match in _DECEPTION.finditer(text):
        subject = _clean(match.group("subject"))
        obj = _clean(match.group("object"))
        if not subject and not obj:
            continue
        out.append(
            DetectorHit(
                kind=DetectorKind.DECEPTION,
                event_type=EventType.LINK,
                subject=subject or "",
                object=obj,
                evidence=match.group(0).strip(),
                offset=match.start(),
                confidence=0.75,
                truth_status=TruthStatus.CLAIMED,
            )
        )
    return out


def detect_reveals(text: str, lexicon: Lexicon | None = None) -> list[DetectorHit]:
    """Find disclosures that two records are one entity.

    Highest-value detector in the set. A reveal binds a fact backwards in story
    time while the reader only learns it now -- which is exactly why story time
    and knowledge time are separate axes, and why first-attestation is a soft
    prior rather than a hard constraint.
    """
    out: list[DetectorHit] = []
    for match in _REVEAL.finditer(text):
        subject = _clean(match.group("subject"))
        obj = _clean(match.group("object"))
        if not subject and not obj:
            continue
        out.append(
            DetectorHit(
                kind=DetectorKind.REVEAL,
                event_type=EventType.MERGE,
                subject=subject or "",
                object=obj,
                evidence=match.group(0).strip(),
                offset=match.start(),
                # High: these phrases are near-unambiguous in this genre.
                confidence=0.85,
            )
        )
    return out


def detect_deaths(text: str, lexicon: Lexicon | None = None) -> list[DetectorHit]:
    """Find deaths and departures.

    Closes the persona binding. Death is frequently impermanent in this genre,
    so the binding is closed rather than the entity deleted -- a later
    resurrection opens a new binding, and the gap between them is a legitimate
    state (ABSENT) rather than a contradiction.
    """
    out: list[DetectorHit] = []
    for match in _DEATH.finditer(text):
        subject = _clean(match.group("subject"))
        if not subject:
            continue
        out.append(
            DetectorHit(
                kind=DetectorKind.DEATH,
                event_type=EventType.DEATH,
                subject=subject,
                object=None,
                evidence=match.group(0).strip(),
                offset=match.start(),
                confidence=0.7,
            )
        )
    for match in _RESURRECTION.finditer(text):
        subject = _clean(match.group("subject"))
        if not subject:
            continue
        out.append(
            DetectorHit(
                kind=DetectorKind.RESURRECTION,
                event_type=EventType.RESURRECTION,
                subject=subject,
                object=None,
                evidence=match.group(0).strip(),
                offset=match.start(),
                confidence=0.7,
            )
        )
    return out


def detect_reputation(text: str, lexicon: Lexicon | None = None) -> list[DetectorHit]:
    """Find widening audience scope.

    Audience is emergent from the event log rather than a stored property, so
    this is how it grows: a name known in one region becoming known everywhere
    changes which observers a later `state_of` query should return it for.
    """
    out: list[DetectorHit] = []
    for match in _REPUTATION.finditer(text):
        subject = _clean(match.group("subject"))
        if not subject:
            continue
        out.append(
            DetectorHit(
                kind=DetectorKind.REPUTATION,
                event_type=EventType.REPUTATION_SPREAD,
                subject=subject,
                object=None,
                evidence=match.group(0).strip(),
                offset=match.start(),
                confidence=0.6,
            )
        )
    return out


ALL_DETECTORS = (
    detect_transfers,
    detect_deceptions,
    detect_reveals,
    detect_deaths,
    detect_reputation,
)


def run_detectors(text: str, lexicon: Lexicon | None = None) -> list[DetectorHit]:
    """Run every detector over a piece of text, ordered by position."""
    hits: list[DetectorHit] = []
    for detector in ALL_DETECTORS:
        hits.extend(detector(text, lexicon))
    hits.sort(key=lambda h: h.offset)
    return hits
