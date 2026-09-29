"""Causal OR-Set for the world layer W.

Standard construction (Shapiro et al. 2011; optimized dot/context form per
Bieniusa et al. 2012, "An optimized conflict-free replicated set"). No novelty
is claimed for this file -- it is the well-understood join-semilattice used
to give W strong eventual consistency. The novel material is in replica.py
(the K_i materialization / non-interference layer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Set, Tuple

Dot = Tuple[str, int]  # (replica_id, local_counter)


@dataclass
class ORSet:
    """Add/remove set with causal (dot, context) tombstone semantics.

    elements: fact_id -> set of live dots asserting it
    context:  replica_id -> highest counter from that replica this
              ORSet has causally observed (a version vector)
    """

    elements: Dict[str, Set[Dot]] = field(default_factory=dict)
    context: Dict[str, int] = field(default_factory=dict)

    def _covers(self, dot: Dot) -> bool:
        replica, counter = dot
        return counter <= self.context.get(replica, 0)

    def add(self, fact_id: str, dot: Dot) -> None:
        self.elements.setdefault(fact_id, set()).add(dot)
        replica, counter = dot
        self.context[replica] = max(self.context.get(replica, 0), counter)

    def remove(self, fact_id: str, observed_dots: FrozenSet[Dot]) -> None:
        """Add-wins remove: drop exactly the dots this op observed as live."""
        live = self.elements.get(fact_id)
        if not live:
            return
        live -= set(observed_dots)
        if not live:
            self.elements.pop(fact_id, None)

    def contains(self, fact_id: str) -> bool:
        return bool(self.elements.get(fact_id))

    def live_dots(self, fact_id: str) -> FrozenSet[Dot]:
        return frozenset(self.elements.get(fact_id, set()))

    def facts(self) -> Set[str]:
        return {f for f, dots in self.elements.items() if dots}

    def join(self, other: "ORSet") -> "ORSet":
        """Commutative, associative, idempotent join -> join-semilattice.

        merged[f] = (A[f] & B[f])
                  | (A[f] - dots_covered_by(B.context))
                  | (B[f] - dots_covered_by(A.context))
        """
        out = ORSet()
        out.context = {
            r: max(self.context.get(r, 0), other.context.get(r, 0))
            for r in set(self.context) | set(other.context)
        }
        facts = set(self.elements) | set(other.elements)
        for f in facts:
            a = self.elements.get(f, set())
            b = other.elements.get(f, set())
            kept = set(a & b)
            kept |= {d for d in a - b if not other._covers(d)}
            kept |= {d for d in b - a if not self._covers(d)}
            if kept:
                out.elements[f] = kept
        return out

    def size_bytes(self) -> int:
        """Rough serialized-size estimate for bandwidth accounting."""
        dot_bytes = sum(len(dots) * 12 for dots in self.elements.values())
        ctx_bytes = len(self.context) * 12
        return dot_bytes + ctx_bytes
