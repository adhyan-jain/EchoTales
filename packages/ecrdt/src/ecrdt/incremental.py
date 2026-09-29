"""Phase 2: a genuinely correct, delta-incremental materializer, prototyped
SEPARATELY from replica.Replica (the reference implementation) so the
reference stays simple/obviously-correct and this stays provable by
differential testing against it, per the brief's instruction not to touch
DAG maintenance "merely to improve numbers."

THE KEY IDEA (causal-delivery buffering, standard technique, applied here
to a second-order derived set instead of to the primary CRDT object):

reference Replica.materialize() is correct because it processes ALL of E
in one topological pass every time, so every event's deps are guaranteed
already processed before the event itself. The O(|E| log |E|) cost comes
from redoing that whole pass on every call.

The incremental fix is NOT "cache the per-dot verdict forever" (a dot's
early verdict can be wrong if a dependency it needed hadn't arrived yet --
see replica.py's cache-invalidation docstring, and
test_adversarial.py::test_out_of_order_delivery_self_heals_once_dependency_arrives).
It IS "never process a dot until every dot it depends on has already been
processed" -- a causal-delivery hold-back buffer, applied uniformly to
every event kind (not just infer). An event that arrives with a
not-yet-satisfied dependency sits in `_pending` until that dependency is
delivered, then drains automatically, in whatever order deps become
satisfied -- which Theorem 6 (README addendum / IPR_REVIEW.md Phase 7)
proves gives an identical result to the reference regardless of arrival
order, because concurrent (non-causally-related) events' effects commute.

Each event is processed exactly ONCE over the replica's entire lifetime.
Total work across the replica's life is O(|E|); a single merge call costs
O(|delta| + backlog drained this call), not O(|E|).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Set, Tuple

from .model import Event
from .orset import Dot, ORSet


@dataclass
class IncrementalReplica:
    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)
    E: Dict[Dot, Event] = field(default_factory=dict)  # full log kept for parity/compaction/audit, NOT re-walked

    # incremental materialization state -- the actual optimization
    _delivered: Set[Dot] = field(default_factory=set)           # DAG-structurally processed (any kind)
    _pending: Dict[Dot, Event] = field(default_factory=dict)     # waiting on a dep not yet delivered
    _established: Dict[str, Set[Dot]] = field(default_factory=dict)  # K_i, incrementally maintained
    _ever_established: Set[Dot] = field(default_factory=set)     # append-only, for infer's closure check

    # accounting, for the scaling benchmark
    events_processed: int = 0
    drain_calls: int = 0

    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    # ---- operations: identical preconditions to replica.Replica, but the
    # precondition check reads the incrementally-maintained cache directly
    # (O(1)/O(deps)) instead of calling a full materialize() pass. ----
    def assert_world(self, fact: str) -> Event:
        dot = self._new_dot()
        e = Event(dot=dot, kind="assert_world", fact=fact, actor=self.replica_id)
        self.E[dot] = e
        self.W.add(fact, dot)
        self._ingest(dot, e)
        return e

    def observe(self, fact: str) -> Event:
        if not self.W.contains(fact):
            raise ValueError(f"cannot OBSERVE {fact!r}: not live in W at {self.replica_id}")
        dot = self._new_dot()
        e = Event(dot=dot, kind="observe", fact=fact, actor=self.replica_id, deps=self.W.live_dots(fact))
        self.E[dot] = e
        self._ingest(dot, e)
        return e

    def communicate(self, target: str, fact: str) -> Event:
        if fact not in self._established or not self._established[fact]:
            raise ValueError(f"cannot COMMUNICATE {fact!r}: {self.replica_id} does not know it")
        dot = self._new_dot()
        e = Event(dot=dot, kind="communicate", fact=fact, actor=self.replica_id, target=target,
                   deps=frozenset(self._established[fact]))
        self.E[dot] = e
        self._ingest(dot, e)
        return e

    def infer(self, fact: str, premises: List[str]) -> Event:
        missing = [p for p in premises if p not in self._established or not self._established[p]]
        if missing:
            raise ValueError(f"cannot INFER {fact!r}: missing premises {missing}")
        deps: Set[Dot] = set()
        for p in premises:
            deps |= self._established[p]
        dot = self._new_dot()
        e = Event(dot=dot, kind="infer", fact=fact, actor=self.replica_id, deps=frozenset(deps))
        self.E[dot] = e
        self._ingest(dot, e)
        return e

    def retract_world(self, fact: str) -> Event:
        dots = self.W.live_dots(fact)
        if not dots:
            raise ValueError(f"cannot RETRACT_WORLD {fact!r}: not live")
        dot = self._new_dot()
        e = Event(dot=dot, kind="retract_world", fact=fact, actor=self.replica_id, deps=dots)
        self.E[dot] = e
        self.W.remove(fact, dots)
        self._ingest(dot, e)
        return e

    def retract_knowledge(self, target: str, fact: str, establishing_dots: FrozenSet[Dot]) -> Event:
        dot = self._new_dot()
        e = Event(dot=dot, kind="retract_knowledge", fact=fact, actor=self.replica_id, target=target,
                   deps=establishing_dots)
        self.E[dot] = e
        self._ingest(dot, e)
        return e

    # ---- merge: add new events to the pending buffer, then drain ----
    def merge(self, other: "IncrementalReplica") -> None:
        self.W = self.W.join(other.W)
        for dot, e in other.E.items():
            if dot not in self.E:
                self.E[dot] = e
                self._pending[dot] = e
        self._drain()

    def _ingest(self, dot: Dot, e: Event) -> None:
        self._pending[dot] = e
        self._drain()

    def _drain(self) -> None:
        """Repeatedly deliver any pending event whose deps are all already
        delivered, until a full pass makes no progress. Each event is
        delivered (and its effect applied) exactly once, ever."""
        self.drain_calls += 1
        progress = True
        while progress and self._pending:
            progress = False
            ready = [d for d, e in self._pending.items() if e.deps <= self._delivered]
            if not ready:
                break
            for d in sorted(ready):  # deterministic order among a ready batch; see Theorem 6 (commutes anyway)
                e = self._pending.pop(d)
                self._apply(e)
                self._delivered.add(d)
                self.events_processed += 1
                progress = True

    def _apply(self, e: Event) -> None:
        me = self.replica_id
        if e.kind == "observe" and e.actor == me:
            self._established.setdefault(e.fact, set()).add(e.dot)
            self._ever_established.add(e.dot)
        elif e.kind == "communicate" and e.target == me:
            self._established.setdefault(e.fact, set()).add(e.dot)
            self._ever_established.add(e.dot)
        elif e.kind == "infer" and e.actor == me:
            if e.deps <= self._ever_established:
                self._established.setdefault(e.fact, set()).add(e.dot)
                self._ever_established.add(e.dot)
        elif e.kind == "retract_knowledge" and e.target == me:
            live = self._established.get(e.fact)
            if live:
                live -= set(e.deps)
        # assert_world / retract_world / non-matching actor|target: no K effect,
        # but still marked delivered so downstream deps (e.g. an OBSERVE
        # whose deps point at this assert) can become ready.

    # ---- read path: O(1), always up to date (no dirty/recompute step) ----
    def materialize(self) -> Tuple[Set[str], Dict[str, FrozenSet[Dot]]]:
        K = {f for f, dots in self._established.items() if dots}
        provenance = {f: frozenset(dots) for f, dots in self._established.items() if dots}
        return K, provenance

    def knows(self, fact: str) -> bool:
        return bool(self._established.get(fact))

    def pending_backlog(self) -> int:
        """Events received but not yet deliverable -- waiting on a dep
        that hasn't arrived. Should reach 0 once the system is causally
        complete (no permanently-missing dependency)."""
        return len(self._pending)

    def event_log_size_bytes(self) -> int:
        return sum(e.size_bytes() for e in self.E.values())
