"""Read-set tracking for incremental invalidation (plans.md Section 6 Phase 7).

Every derived artifact records which graph facts it consulted. When a later
event changes some facts, invalidation is the intersection of the changed set
with each artifact's read set -- so a chapter-190 reveal invalidates the few
artifacts that actually depended on the affected entity rather than forcing a
reprocess of 190 chapters.

Three cache tiers, in increasing order of volatility:

- ``TEXT``   -- mentions, spans, embeddings. Derived from text alone, so never
                invalidated by graph events.
- ``GRAPH``  -- resolutions, ``state_of`` results. Invalidated when an event
                touches a fact in the read set.
- ``RENDER`` -- audio segments, panel images. Invalidated by upstream state
                changes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from echotales.core.enums import TargetKind


class CacheTier(StrEnum):
    TEXT = "TEXT"
    GRAPH = "GRAPH"
    RENDER = "RENDER"

    @property
    def invalidated_by_graph_events(self) -> bool:
        return self is not CacheTier.TEXT


def fact_ref(kind: str, ident: str | int, *parts: str) -> str:
    """Build a stable reference to one graph fact.

    Strings rather than integer row ids on purpose: read sets are written to
    the event log and compared across runs, so they must survive a rebuild of
    the database in which autoincrement ids would shift.
    """
    tail = ":".join(str(p) for p in parts)
    return f"{kind}:{ident}" + (f":{tail}" if tail else "")


def entity_ref(kind: TargetKind, target_id: str) -> str:
    return fact_ref(kind.value.lower(), target_id)


def alias_ref(novel_id: str, alias_norm: str) -> str:
    return fact_ref("alias", novel_id, alias_norm)


def observable_ref(fact: object) -> str:
    """A stable id for one temporal fact, for the `observation` table.

    The observation table keys on `(observer_id, fact_ref)`, and until
    2026-09-23 nothing produced a `fact_ref` because nothing ever wrote an
    observation (EVOLUTION 4.80). The ref has to be derivable from the fact
    itself rather than from a row id: the same assertion re-derived by a
    re-resolve must land on the same ref, or a character's knowledge silently
    resets every time the pipeline runs.

    Deliberately excludes interval, learned-at position and truth status --
    those are *when and how* the fact is held, and an observer who witnessed
    an event does not un-witness it because the interval was later refined.
    """
    from echotales.core.models import AliasBinding, Attribute, Relation

    if isinstance(fact, AliasBinding):
        return fact_ref("alias", fact.target_id, normalize(fact.alias))
    if isinstance(fact, Attribute):
        return fact_ref("attr", fact.target_id, fact.key, fact.value)
    if isinstance(fact, Relation):
        return fact_ref("rel", fact.src_self, fact.type, fact.dst_self)
    raise TypeError(f"no observable ref defined for {type(fact).__name__}")


def normalize(text: str) -> str:
    """Casefolded, whitespace-collapsed, for ref stability across renderings."""
    return " ".join(text.split()).casefold()


def segment_ref(segment_id: str) -> str:
    return fact_ref("segment", segment_id)


def hash_read_set(refs: Iterable[str]) -> str:
    """Order-independent digest of a read set.

    Sorted before hashing so two artifacts that consulted the same facts in a
    different order share a hash and are recognised as equivalent.
    """
    joined = "\n".join(sorted(set(refs)))
    return hashlib.blake2b(joined.encode("utf-8"), digest_size=16).hexdigest()


class ReadSetRecorder:
    """Collects the facts consulted while computing one derived artifact.

    Used as a context manager around a `state_of` call or a resolution
    decision; the resulting refs are stored alongside the artifact.
    """

    def __init__(self) -> None:
        self._refs: set[str] = set()

    def record(self, ref: str) -> None:
        self._refs.add(ref)

    def record_many(self, refs: Iterable[str]) -> None:
        self._refs.update(refs)

    def record_entity(self, kind: TargetKind, target_id: str) -> None:
        self._refs.add(entity_ref(kind, target_id))

    @property
    def refs(self) -> list[str]:
        return sorted(self._refs)

    @property
    def digest(self) -> str:
        return hash_read_set(self._refs)

    def __enter__(self) -> ReadSetRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@dataclass(slots=True, frozen=True)
class EpistemicLeakageResult:
    is_valid: bool
    leaked_facts: tuple[str, ...] = ()
    reason: str = ""


class EpistemicLeakageValidator:
    """Structural validator checking prompts and plan specifications for secret leaks."""

    def validate(
        self, gen_state: object, text_to_check: str
    ) -> EpistemicLeakageResult:
        forbidden_facts: tuple[str, ...] = getattr(gen_state, "forbidden_facts", ())
        if not forbidden_facts:
            return EpistemicLeakageResult(is_valid=True)

        normalized_text = " " + text_to_check.casefold() + " "
        leaks: list[str] = []

        for forbidden in forbidden_facts:
            forbidden_clean = forbidden.strip().casefold()
            if not forbidden_clean or len(forbidden_clean) < 3:
                continue
            # Structural substring/boundary check
            if forbidden_clean in normalized_text:
                leaks.append(forbidden)

        if leaks:
            return EpistemicLeakageResult(
                is_valid=False,
                leaked_facts=tuple(leaks),
                reason=f"Detected {len(leaks)} forbidden epistemic leak(s): {', '.join(leaks)}",
            )

        return EpistemicLeakageResult(is_valid=True)

