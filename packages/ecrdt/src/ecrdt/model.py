"""Core event/provenance model: P_i, the causal disclosure DAG.

Every operation in the spec (ASSERT_WORLD, OBSERVE, COMMUNICATE, INFER,
RETRACT_WORLD, RETRACT_KNOWLEDGE) is reified as an immutable Event keyed by
a unique Dot (replica_id, local_counter). Events form a grow-only causal
DAG: E' = E_i cup E_j is itself a trivial join-semilattice (set union).

The non-trivial part of the design lives in replica.py: the function that
*projects* this shared, fully-replicated DAG down into a replica-local
knowledge set K_i. That projection -- not the DAG merge -- is what must be
proven non-interfering.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional

from .orset import Dot

KINDS = frozenset(
    {
        "assert_world",
        "observe",
        "communicate",
        "infer",
        "retract_world",
        "retract_knowledge",
    }
)


@dataclass(frozen=True)
class Event:
    dot: Dot
    kind: str
    fact: str
    actor: str
    target: Optional[str] = None  # addressee, for communicate/retract_knowledge
    deps: FrozenSet[Dot] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown event kind {self.kind!r}")

    def size_bytes(self) -> int:
        # dot(12) + kind + fact ids + deps, rough estimate for bandwidth accounting
        return 12 + len(self.kind) + len(self.fact) + 12 + len(self.deps) * 12
