"""Replica state R_i = (W, E, materialize) and the merge algorithm.

K_i is not stored directly; it is *materialized* on demand (or cached) as a
pure function of (E, i). This is the structural choice that gives epistemic
non-interference: merge always deals in the full causal event DAG E (which
is public metadata -- "what happened, and to/by whom" -- and converges like
any CRDT), but the *content* a replica is entitled to hold, K_i, is a local
projection gated by "is `i` the subject or addressee of this event", not an
attribute check against a converged store. See README.md Theorem 2.

Threat model (stated explicitly, matching standard CRDT literature): replicas
are non-Byzantine. An operation's preconditions (e.g. COMMUNICATE requires
the sender to already hold the fact) are enforced locally by the issuing
replica's own API before an Event is minted, exactly as a CRDT assumes
well-formed local operations, not adversarial ones. Byzantine-robust
extension (signed events) is noted as future work, not attempted here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from .model import Event
from .orset import Dot, ORSet


def _topo_order(events: Dict[Dot, Event]) -> List[Event]:
    """Kahn's algorithm over the deps DAG; ties broken by dot for determinism."""
    indeg = {d: 0 for d in events}
    children: Dict[Dot, List[Dot]] = {d: [] for d in events}
    for d, e in events.items():
        for dep in e.deps:
            if dep in events:
                indeg[d] += 1
                children[dep].append(d)
    ready = sorted([d for d, k in indeg.items() if k == 0])
    order: List[Event] = []
    while ready:
        d = ready.pop(0)
        order.append(events[d])
        for c in sorted(children[d]):
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
        ready.sort()
    if len(order) != len(events):
        raise ValueError("event DAG has a cycle or dangling dependency")
    return order


@dataclass
class Replica:
    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)
    E: Dict[Dot, Event] = field(default_factory=dict)
    # local knowledge of *other* facts' payloads is out of scope; we track
    # fact ids only, matching the abstraction in the brief.
    _facts_seen_locally: Set[str] = field(default_factory=set)
    # Pure memoization of materialize(), invalidated whenever E changes.
    # NOTE: this is *not* delta-incremental materialization. A dot that
    # fails an INFER/RETRACT precondition because a dependency has not
    # arrived yet must be re-examined on every subsequent full recompute
    # once that dependency lands (see test_adversarial.py, delayed
    # delivery scenarios) -- caching only the *final* per-dot verdict
    # would silently break that self-healing property. Full delta
    # materialization that preserves it needs a pending/watermark queue
    # for not-yet-satisfiable nodes; not implemented this session (see
    # AUDIT.md "weakest point").
    _dirty: bool = True
    _cache: Optional[Tuple[Set[str], Dict[str, FrozenSet[Dot]]]] = field(default=None, repr=False)
    materialize_calls: int = 0
    materialize_full_recomputes: int = 0

    # ---- operations -------------------------------------------------
    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    def assert_world(self, fact: str) -> Event:
        dot = self._new_dot()
        e = Event(dot=dot, kind="assert_world", fact=fact, actor=self.replica_id)
        self.E[dot] = e
        self.W.add(fact, dot)
        self._dirty = True
        return e

    def observe(self, fact: str) -> Event:
        """Precondition: fact must be a live fact in this replica's view of W."""
        if not self.W.contains(fact):
            raise ValueError(f"cannot OBSERVE {fact!r}: not live in W at {self.replica_id}")
        assert_dots = self.W.live_dots(fact)
        dot = self._new_dot()
        e = Event(dot=dot, kind="observe", fact=fact, actor=self.replica_id, deps=assert_dots)
        self.E[dot] = e
        self._facts_seen_locally.add(fact)
        self._dirty = True
        return e

    def communicate(self, target: str, fact: str) -> Event:
        """Precondition: sender must already know `fact` (fact in materialized K)."""
        known, provenance = self.materialize()
        if fact not in known:
            raise ValueError(f"cannot COMMUNICATE {fact!r}: {self.replica_id} does not know it")
        dot = self._new_dot()
        e = Event(
            dot=dot,
            kind="communicate",
            fact=fact,
            actor=self.replica_id,
            target=target,
            deps=frozenset(provenance[fact]),
        )
        self.E[dot] = e
        self._dirty = True
        return e

    def infer(self, fact: str, premises: List[str]) -> Event:
        """Precondition: actor must already know every premise."""
        known, provenance = self.materialize()
        missing = [p for p in premises if p not in known]
        if missing:
            raise ValueError(f"cannot INFER {fact!r}: missing premises {missing}")
        deps: Set[Dot] = set()
        for p in premises:
            deps |= provenance[p]
        dot = self._new_dot()
        e = Event(dot=dot, kind="infer", fact=fact, actor=self.replica_id, deps=frozenset(deps))
        self.E[dot] = e
        self._dirty = True
        return e

    def retract_world(self, fact: str) -> Event:
        dots = self.W.live_dots(fact)
        if not dots:
            raise ValueError(f"cannot RETRACT_WORLD {fact!r}: not live")
        dot = self._new_dot()
        e = Event(dot=dot, kind="retract_world", fact=fact, actor=self.replica_id, deps=dots)
        self.E[dot] = e
        self.W.remove(fact, dots)
        self._dirty = True
        return e

    def retract_knowledge(self, target: str, fact: str, establishing_dots: FrozenSet[Dot]) -> Event:
        """Revoke a specific replica's knowledge of `fact` (add-wins: a later,
        concurrent OBSERVE/COMMUNICATE/INFER for that replica survives)."""
        dot = self._new_dot()
        e = Event(
            dot=dot,
            kind="retract_knowledge",
            fact=fact,
            actor=self.replica_id,
            target=target,
            deps=establishing_dots,
        )
        self.E[dot] = e
        self._dirty = True
        return e

    # ---- merge --------------------------------------------------------
    def merge(self, other: "Replica") -> None:
        self.W = self.W.join(other.W)
        new_dots = [dot for dot in other.E if dot not in self.E]
        for dot in new_dots:
            self.E[dot] = other.E[dot]
        if new_dots:
            self._dirty = True

    # ---- materialization (the projection K_i = view(E, i)) ------------
    def materialize(self) -> Tuple[Set[str], Dict[str, FrozenSet[Dot]]]:
        """Return (K_i, provenance) where provenance[f] is the set of *this
        replica's own* establishing dots for fact f, surviving retraction.

        This is the sole read path into "what does replica i know". It is a
        pure function of (self.E, self.replica_id) -- merging in someone
        else's W or someone else's K never writes here directly.

        Memoized: recomputes the full O(|E|) pass only when E has changed
        since the last call (self._dirty). Repeated reads of a settled
        state are O(1).
        """
        self.materialize_calls += 1
        if not self._dirty and self._cache is not None:
            return self._cache
        self.materialize_full_recomputes += 1
        me = self.replica_id
        established: Dict[str, Set[Dot]] = {}
        ever_established: Set[Dot] = set()
        for e in _topo_order(self.E):
            if e.kind == "observe" and e.actor == me:
                established.setdefault(e.fact, set()).add(e.dot)
                ever_established.add(e.dot)
            elif e.kind == "communicate" and e.target == me:
                established.setdefault(e.fact, set()).add(e.dot)
                ever_established.add(e.dot)
            elif e.kind == "infer" and e.actor == me:
                if all(dep in ever_established for dep in e.deps):
                    established.setdefault(e.fact, set()).add(e.dot)
                    ever_established.add(e.dot)
            elif e.kind == "retract_knowledge" and e.target == me:
                live = established.get(e.fact)
                if live:
                    live -= set(e.deps)
        K = {f for f, dots in established.items() if dots}
        provenance = {f: frozenset(dots) for f, dots in established.items() if dots}
        self._cache = (K, provenance)
        self._dirty = False
        return K, provenance

    def knows(self, fact: str) -> bool:
        K, _ = self.materialize()
        return fact in K

    # ---- accounting -----------------------------------------------------
    def event_log_size_bytes(self) -> int:
        return sum(e.size_bytes() for e in self.E.values())

    def event_context(self) -> Dict[str, int]:
        """High-watermark counter per origin replica across the *event log*
        (superset of W.context, which only tracks assert/retract dots)."""
        ctx: Dict[str, int] = {}
        for (origin, counter) in self.E:
            ctx[origin] = max(ctx.get(origin, 0), counter)
        return ctx
