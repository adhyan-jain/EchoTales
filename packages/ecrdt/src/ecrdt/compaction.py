"""Provenance compaction: collapse causally-stable disclosure chains.

Once an event is *causally stable* (every replica in the system has it in
their causal past -- the standard stability test used for tombstone GC in
delta-CRDTs / RGA), the exact multi-hop chain that established a fact for a
replica no longer matters for future materialization: only the boolean
"was it established" plus the dot that would be targeted by a future
RETRACT_KNOWLEDGE matters. So a stable chain

    assert_world(f) -> observe(A, f) -> communicate(A->B, f) -> communicate(B->C, f)

is compacted, for a materializer at C, into a single synthetic event

    communicate(A->C, f)   [tag: compacted, original_hops=3]

This is safe (Theorem 3, README) *only* for stable events: an event that is
still concurrently reachable by a not-yet-delivered RETRACT could still be
undone, so compaction must not run ahead of stability, exactly as CRDT
tombstone GC must not run ahead of causal stability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

from .model import Event
from .orset import Dot


@dataclass
class CompactionResult:
    compacted_events: Dict[Dot, Event]
    bytes_before: int
    bytes_after: int
    events_before: int
    events_after: int


def causally_stable(events: Dict[Dot, Event], replica_ids: List[str], seen: Dict[str, Dict[str, int]]) -> Set[Dot]:
    """An event is stable once every replica's context has causally observed it.

    `seen[r]` is replica r's own per-origin-replica counter high-watermark
    (its ORSet/event-log context). A dot (origin, c) is stable iff
    min over r in replica_ids of seen[r].get(origin, 0) >= c.
    """
    stable: Set[Dot] = set()
    for dot in events:
        origin, c = dot
        if all(seen.get(r, {}).get(origin, 0) >= c for r in replica_ids):
            stable.add(dot)
    return stable


def compact_for_target(events: Dict[Dot, Event], target: str, stable: Set[Dot]) -> CompactionResult:
    """Collapse stable disclosure chains terminating at `target` into single
    synthetic communicate/observe events, per fact, keeping only the
    earliest-establishing chain's endpoint. Non-stable events (still
    contestable) are kept exactly as-is.
    """
    bytes_before = sum(e.size_bytes() for e in events.values())
    events_before = len(events)

    kept: Dict[Dot, Event] = {}
    terminal_for_target: Dict[str, Event] = {}

    for dot, e in events.items():
        is_terminal_for_target = (
            (e.kind == "observe" and e.actor == target)
            or (e.kind == "communicate" and e.target == target)
            or (e.kind == "infer" and e.actor == target)
        )
        if dot not in stable or not is_terminal_for_target:
            kept[dot] = e
            continue
        prior = terminal_for_target.get(e.fact)
        if prior is None or dot < prior.dot:
            terminal_for_target[e.fact] = e

    for fact, e in terminal_for_target.items():
        compacted = Event(
            dot=e.dot,
            kind=e.kind,
            fact=e.fact,
            actor=e.actor,
            target=e.target,
            deps=frozenset(),  # chain history discarded; existence is retained
        )
        kept[e.dot] = compacted

    bytes_after = sum(e.size_bytes() for e in kept.values())
    return CompactionResult(
        compacted_events=kept,
        bytes_before=bytes_before,
        bytes_after=bytes_after,
        events_before=events_before,
        events_after=len(kept),
    )
