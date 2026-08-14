"""Active scene participant tracking and mob detection (xyz.md Step 2).

Two things a scene-level view can answer that a chapter-level one can't:

**Who is in the room right now.** Speaker attribution and voice casting both
eventually need this -- a bare unresolved dialogue line in a scene with
exactly two people present is a very different problem from the same line in
a scene with fifteen. `present_cast()` (`anaphora/local.py`) already answers
"physically present" for one set of mentions; this module scopes that per
`NarrativeSegment` rather than per chapter, since a chapter routinely covers
several scenes with different casts.

**Background crowds, without minting a fake individual.** "A group of
disciples" describes real people a panel needs to draw, but it is not one
continuity of consciousness -- there is no `Self` for it to be. Mirrors the
anonymous-voice-slot precedent (`speakers/runner.py::_assign_anonymous_slots`):
the lightest thing that could work, scoped to the scene, never written as a
graph row. `detect_mobs()` therefore returns plain descriptors, not `Mention`s
-- there is deliberately no path from here into the mention/entity graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echotales.core.models import Chapter, Mention, NarrativeSegment, Span
from echotales.pipeline.anaphora.local import present_cast

#: Role nouns worth reporting as a background crowd for panel casting.
#: Deliberately a fixed vocabulary rather than reusing `alias_type.py`'s
#: broader `_ROLE_NOUNS` list -- that list exists to catch a *singular*
#: descriptor ("the innkeeper") as non-character; a mob phrase additionally
#: needs a plural, collective-shaped role, and most of that list (e.g.
#: "doctor", "landlord") does not read as a crowd even pluralised.
_MOB_ROLE_NOUNS = (
    "disciples", "guards", "elders", "soldiers", "servants", "cultivators",
    "students", "villagers", "citizens", "clansmen", "warriors", "monks",
    "nuns", "attendants", "subordinates", "followers", "retainers",
    "bandits", "spectators", "onlookers", "crowd", "mob", "troops",
)

#: Quantifiers that mark a plural role noun as a described *group* rather
#: than, say, a list of named individuals ("the disciples Wang and Li").
_MOB_QUANTIFIER = (
    r"(?:a|an|the|several|many|dozens of|hundreds of|thousands of|"
    r"a group of|a crowd of|a bunch of|countless|numerous|surrounding)"
)

_MOB_RE = re.compile(
    rf"\b{_MOB_QUANTIFIER}\s+(?:surrounding\s+|nearby\s+)?"
    # One optional modifier word between the quantifier and the role noun --
    # "the clan elders", "the experienced elders" -- real RI phrasing that a
    # strictly-adjacent quantifier+noun match missed entirely (§4.31 item 11:
    # the ancestral-hall scene's repeated "the clan elders" never fired).
    # Bounded to exactly one word, not an open-ended list, to avoid the
    # vocabulary-growth trap EVOLUTION.md already flagged once.
    rf"(?:\w+\s+)?({'|'.join(_MOB_ROLE_NOUNS)})\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class MobDescriptor:
    """One detected background-crowd phrase. Not a `Mention` -- see module docstring."""

    text: str
    role: str
    offset: int
    block_index: int


def detect_mobs(text: str, block_index: int = 0) -> list[MobDescriptor]:
    """Find collective-noun crowd phrases in one span or block of text."""
    return [
        MobDescriptor(
            text=m.group(0), role=m.group(1).lower(), offset=m.start(), block_index=block_index
        )
        for m in _MOB_RE.finditer(text)
    ]


@dataclass(slots=True)
class ActiveScene:
    """Who's present, and what background crowds are described, in one scene."""

    segment_id: str
    chapter: float
    block_from: int
    block_to: int
    active_selves: set[str] = field(default_factory=set)
    mobs: list[MobDescriptor] = field(default_factory=list)


def build_active_scenes(
    chapter: Chapter,
    mentions: list[Mention],
    segments: list[NarrativeSegment],
    spans: list[Span],
) -> list[ActiveScene]:
    """One `ActiveScene` per narrative segment touching this chapter.

    Segment bounds are block indices (`NarrativeSegment`'s own docstring, and
    `Mention.block_index`/`Span.block_index` -- the three already share this
    coordinate system, so no translation is needed here).
    """
    scenes: list[ActiveScene] = []
    for seg in segments:
        if seg.chapter_from > chapter.number or seg.chapter_to < chapter.number:
            continue
        lo = seg.offset_from if seg.chapter_from == chapter.number else 0
        hi = seg.offset_to if seg.chapter_to == chapter.number else max(
            (s.block_index for s in spans), default=0
        )

        seg_mentions = [m for m in mentions if lo <= m.block_index <= hi]
        mobs: list[MobDescriptor] = []
        for span in spans:
            if lo <= span.block_index <= hi:
                mobs.extend(detect_mobs(span.text, span.block_index))

        scenes.append(
            ActiveScene(
                segment_id=seg.id,
                chapter=chapter.number,
                block_from=lo,
                block_to=hi,
                active_selves=present_cast(seg_mentions),
                mobs=mobs,
            )
        )
    return scenes
