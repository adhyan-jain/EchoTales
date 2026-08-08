"""Contradiction detection over committed links (plans.md §6 Phase 6, revised).

**The gazetteer compounds wrong decisions exactly as well as right ones.**

That is the cost of the compounding mechanism, and it is not hypothetical. A
wrong `LINK` at chapter 30 adds a bad surface form to an entity's alias set;
Aho-Corasick then exact-matches that form for the rest of the volume; the
pre-filter force-links on an exact alias match; and the error becomes
self-reinforcing. Nothing in the forward pass can undo it, because every later
observation only *adds* evidence to the entity that already absorbed it.

So a backward pass runs after every processing window. It re-scores committed
links against evidence accumulated *since* the link was made, and where a link
no longer holds it emits a `split` event and returns the case to the deferred
queue.

Three contradiction classes, each detectable only in hindsight:

**Co-presence discovered later.** At chapter 30 two surface forms had never
appeared together. By chapter 90 they share a scene doing different things —
which proves they were never one persona.

**Conflicting surface forms.** An entity accumulates two rigid names that
normalise differently and never co-refer. Absorbing both is the signature of a
merge that should not have happened.

**Attribute contradictions.** Stated gender flips, or mutually exclusive ranks
held simultaneously. These are assertions, not inferences, so a conflict is
strong evidence rather than noise.

Without this, "retroactive correction rate" is unreportable: the event log
records only growth and never correction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import pairwise

from echotales.core.enums import EventType, ResolutionMethod, TargetKind
from echotales.core.models import DiscoursePosition, Mention, ResolutionEvent
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key
from echotales.pipeline.resolve.retrieve import EntityProfile

log = logging.getLogger(__name__)

#: Two PRESENT mentions closer than this in one chapter count as simultaneous.
_COPRESENCE_WINDOW = 200

#: An entity holding more than this many mutually non-corefering rigid names is
#: suspect. Two is normal (a name plus an epithet); five is a merge.
_MAX_DISTINCT_NAMES = 4

#: Attribute keys whose values are mutually exclusive, so a change is a
#: contradiction rather than an update.
_EXCLUSIVE_ATTRIBUTES = frozenset({"gender", "sex", "species", "bloodline"})


class ContradictionKind(StrEnum):
    CO_PRESENCE = "CO_PRESENCE"
    CONFLICTING_NAMES = "CONFLICTING_NAMES"
    ATTRIBUTE_CONFLICT = "ATTRIBUTE_CONFLICT"


@dataclass(slots=True)
class Contradiction:
    kind: ContradictionKind
    target_id: str
    detail: str
    evidence_positions: list[DiscoursePosition] = field(default_factory=list)
    #: Surface forms implicated, used to propose the split.
    surfaces: list[str] = field(default_factory=list)
    confidence: float = 0.8


@dataclass(slots=True)
class ContradictionReport:
    window: int = 0
    entities_checked: int = 0
    contradictions: int = 0
    splits_emitted: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    affected: list[str] = field(default_factory=list)

    def summary(self) -> str:
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(self.by_kind.items())) or "none"
        return (
            f"contradiction sweep (window {self.window}): "
            f"{self.entities_checked:,} entities checked, "
            f"{self.contradictions} contradiction(s), {self.splits_emitted} split(s)\n"
            f"  by kind: {kinds}"
        )


def detect_co_presence(
    target_id: str, mentions: list[Mention]
) -> Contradiction | None:
    """Two surface forms of one entity present together, doing different things.

    Only `PRESENT` mentions count — a name merely spoken aloud in dialogue says
    nothing about who is in the room, and counting those would fire on every
    conversation about an absent character.
    """
    present = sorted(
        (m for m in mentions if m.reference_mode.is_physically_present),
        key=lambda m: (m.chapter, m.offset),
    )
    for a, b in pairwise(present):
        if a.chapter != b.chapter or a.text == b.text:
            continue
        if comparison_key(a.text) == comparison_key(b.text):
            continue
        if b.offset - a.offset <= _COPRESENCE_WINDOW:
            return Contradiction(
                kind=ContradictionKind.CO_PRESENCE,
                target_id=target_id,
                detail=(
                    f"{a.text!r} and {b.text!r} both present in ch {a.chapter:g} "
                    f"within {b.offset - a.offset} chars"
                ),
                evidence_positions=[a.position, b.position],
                surfaces=[a.text, b.text],
                confidence=0.85,
            )
    return None


def detect_conflicting_names(
    target_id: str, profile: EntityProfile
) -> Contradiction | None:
    """An entity that has absorbed too many distinct rigid names.

    Distinctness is measured on the comparison key, so honorific and article
    variants of one name are not counted separately — those are exactly the
    forms that *should* collapse.
    """
    keys: dict[str, str] = {}
    for alias in profile.aliases:
        key = comparison_key(alias)
        if key:
            keys.setdefault(key, alias)

    if len(keys) <= _MAX_DISTINCT_NAMES:
        return None

    return Contradiction(
        kind=ContradictionKind.CONFLICTING_NAMES,
        target_id=target_id,
        detail=(
            f"entity holds {len(keys)} distinct names after normalisation; "
            f"more than {_MAX_DISTINCT_NAMES} suggests an incorrect merge"
        ),
        surfaces=sorted(keys.values()),
        confidence=0.6,
    )


def detect_attribute_conflict(
    target_id: str, store: Store
) -> Contradiction | None:
    """Mutually exclusive attribute values asserted for one entity.

    Restricted to keys where a change genuinely cannot happen. A rank or a
    location changing over time is an ordinary update; a stated species
    changing is a merge artefact.
    """
    seen: dict[str, tuple[str, DiscoursePosition]] = {}
    for attribute in store.get_attributes(TargetKind.SELF, target_id):
        if attribute.key.casefold() not in _EXCLUSIVE_ATTRIBUTES:
            continue
        previous = seen.get(attribute.key)
        if previous is None:
            seen[attribute.key] = (attribute.value, attribute.learned_at_pos)
            continue
        if previous[0].casefold() != attribute.value.casefold():
            return Contradiction(
                kind=ContradictionKind.ATTRIBUTE_CONFLICT,
                target_id=target_id,
                detail=(
                    f"{attribute.key} asserted as {previous[0]!r} and "
                    f"{attribute.value!r} for one entity"
                ),
                evidence_positions=[previous[1], attribute.learned_at_pos],
                confidence=0.9,
            )
    return None


def sweep(
    novel_id: str,
    store: Store,
    profiles: dict[str, EntityProfile],
    *,
    window: int = 0,
    emit_events: bool = True,
) -> tuple[list[Contradiction], ContradictionReport]:
    """Re-check every committed entity against accumulated evidence.

    Runs after each processing window. Findings are emitted as `split` events
    and the caller returns the affected cases to the deferred queue — the
    detector proposes, adjudication disposes.
    """
    report = ContradictionReport(window=window)
    found: list[Contradiction] = []

    mentions_by_target: dict[str, list[Mention]] = {}
    for mention in store.get_mentions(novel_id, resolved_only=True):
        if mention.target_id:
            mentions_by_target.setdefault(mention.target_id, []).append(mention)

    for target_id, profile in profiles.items():
        report.entities_checked += 1
        mentions = mentions_by_target.get(target_id, [])

        for contradiction in (
            detect_co_presence(target_id, mentions),
            detect_conflicting_names(target_id, profile),
            detect_attribute_conflict(target_id, store),
        ):
            if contradiction is None:
                continue
            found.append(contradiction)
            report.contradictions += 1
            report.by_kind[contradiction.kind.value] = (
                report.by_kind.get(contradiction.kind.value, 0) + 1
            )
            if target_id not in report.affected:
                report.affected.append(target_id)

            if emit_events:
                _emit_split(store, novel_id, contradiction, mentions)
                report.splits_emitted += 1

    store.conn.commit()
    return found, report


def _emit_split(
    store: Store,
    novel_id: str,
    contradiction: Contradiction,
    mentions: list[Mention],
) -> None:
    """Record a `split` event.

    The event carries the evidence that triggered it, so a reviewer at chapter
    190 can see why a chapter-30 link was withdrawn. This is the only path by
    which the log records correction rather than growth.
    """
    cause = (
        contradiction.evidence_positions[-1]
        if contradiction.evidence_positions
        else (mentions[-1].position if mentions else DiscoursePosition(chapter=0))
    )
    seq = store.next_seq()
    store.append_event(
        ResolutionEvent(
            id=f"{novel_id}:{contradiction.target_id}:split:{seq}",
            seq=seq,
            type=EventType.SPLIT,
            payload={
                "target_id": contradiction.target_id,
                "kind": contradiction.kind.value,
                "detail": contradiction.detail,
                "surfaces": contradiction.surfaces,
            },
            cause_pos=cause,
            method=ResolutionMethod.SCORED,
            confidence=contradiction.confidence,
        )
    )


def retract_alias_bindings(
    store: Store,
    novel_id: str,
    contradiction: Contradiction,
    at: DiscoursePosition,
) -> int:
    """Retract the alias bindings implicated in a contradiction.

    Retraction rather than interval-closing, deliberately: the binding was
    never correct, so "stopped being true" would misrepresent history. A reader
    standing before `at` still sees the mistaken binding, which is what makes
    "what did the system believe at chapter 100" answerable.
    """
    retracted = 0
    for surface in contradiction.surfaces:
        for binding in store.find_alias_bindings(novel_id, surface):
            if binding.target_id != contradiction.target_id:
                continue
            rows = store.conn.execute(
                "SELECT id FROM alias_binding WHERE novel_id=? AND alias_norm=?"
                " AND target_id=? AND retracted_chapter IS NULL",
                (novel_id, comparison_key(surface) or surface.casefold(), binding.target_id),
            ).fetchall()
            for row in rows:
                store.retract_alias(int(row["id"]), at)
                retracted += 1
    store.conn.commit()
    return retracted
