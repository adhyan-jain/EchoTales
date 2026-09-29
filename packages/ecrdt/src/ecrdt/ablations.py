"""Phase 4: ablated variants isolating which mechanism actually produces
the safety/efficiency effect measured for full E-CRDT.

A. no_causal_dag   -> baselines.NaiveUnionReplica (K_i := W)
B. static_acl      -> baselines.ACLReplica (attribute check, no causal gating)
C. no_provenance   -> NoProvenanceReplica: same event-DAG structure as
                      Replica, but materialize() does NOT verify an
                      INFER event's deps against ever_established -- it
                      trusts actor/target match alone, exactly like
                      observe/communicate already do. Under honest
                      workloads this behaves identically to full E-CRDT;
                      the difference only shows up once a forged/invalid
                      event enters the log (a buggy replica, or the
                      Byzantine scenario in test_adversarial.py), which
                      is exactly what this ablation is for.
D. no_compaction   -> full Replica, simply never calling compact_for_target;
                      measured via bench_scaling/compaction demo directly,
                      no separate class needed.
E. flat_per_agent  -> FlatPerAgentCRDTReplica: the "obvious" naive
                      combination -- literally make each agent's own
                      knowledge set K_i itself a replicated CRDT (an
                      OR-Set) and merge everyone's K freely alongside W.
                      This is what "just CRDT it" collapses to once you
                      try to replicate knowledge directly instead of
                      projecting it from a causal DAG.
F. full            -> replica.Replica, unmodified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Set, Tuple

from .model import Event
from .orset import Dot, ORSet
from .replica import _topo_order


@dataclass
class NoProvenanceReplica:
    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)
    E: Dict[Dot, Event] = field(default_factory=dict)

    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    def assert_world(self, fact: str) -> Event:
        dot = self._new_dot()
        e = Event(dot=dot, kind="assert_world", fact=fact, actor=self.replica_id)
        self.E[dot] = e
        self.W.add(fact, dot)
        return e

    def observe(self, fact: str) -> Event:
        if not self.W.contains(fact):
            raise ValueError(f"cannot OBSERVE {fact!r}")
        dot = self._new_dot()
        e = Event(dot=dot, kind="observe", fact=fact, actor=self.replica_id, deps=self.W.live_dots(fact))
        self.E[dot] = e
        return e

    def communicate(self, target: str, fact: str) -> Event:
        known, _ = self.materialize()
        if fact not in known:
            raise ValueError(f"cannot COMMUNICATE {fact!r}")
        dot = self._new_dot()
        e = Event(dot=dot, kind="communicate", fact=fact, actor=self.replica_id, target=target)
        self.E[dot] = e
        return e

    def infer(self, fact: str, premises) -> Event:
        # ABLATED: no precondition check against materialize() at all --
        # this class exists precisely to demonstrate what happens without
        # provenance-closure verification, including under buggy/forged
        # creation-side calls that a real API would normally reject.
        dot = self._new_dot()
        e = Event(dot=dot, kind="infer", fact=fact, actor=self.replica_id)
        self.E[dot] = e
        return e

    def merge(self, other: "NoProvenanceReplica") -> None:
        self.W = self.W.join(other.W)
        for dot, e in other.E.items():
            self.E.setdefault(dot, e)

    def materialize(self) -> Tuple[Set[str], Dict[str, FrozenSet[Dot]]]:
        me = self.replica_id
        established: Dict[str, Set[Dot]] = {}
        for e in _topo_order(self.E):
            if e.kind == "observe" and e.actor == me:
                established.setdefault(e.fact, set()).add(e.dot)
            elif e.kind == "communicate" and e.target == me:
                established.setdefault(e.fact, set()).add(e.dot)
            elif e.kind == "infer" and e.actor == me:
                # NO closure check here -- the ablation.
                established.setdefault(e.fact, set()).add(e.dot)
        K = {f for f, dots in established.items() if dots}
        return K, {f: frozenset(d) for f, d in established.items()}

    def knows(self, fact: str) -> bool:
        K, _ = self.materialize()
        return fact in K


@dataclass
class FlatPerAgentCRDTReplica:
    """The 'obvious combination' baseline: knowledge itself is just
    another replicated CRDT set, merged freely between whichever pair of
    replicas happens to sync, with no gating at all."""

    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)
    K: ORSet = field(default_factory=ORSet)  # each agent's own "knowledge" OR-Set

    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    def assert_world(self, fact: str) -> None:
        self.W.add(fact, self._new_dot())

    def learn_locally(self, fact: str) -> None:
        """A real, local learning event (the agent's own honest OBSERVE)."""
        self.K.add(fact, self._new_dot())

    def merge(self, other: "FlatPerAgentCRDTReplica") -> None:
        self.W = self.W.join(other.W)
        self.K = self.K.join(other.K)  # <-- the ablation: K is merged just like W

    def knows(self, fact: str) -> bool:
        return self.K.contains(fact)

    def materialized_facts(self) -> Set[str]:
        return self.K.facts()


@dataclass
class ClosureOnlyReplica:
    """Ablation D: provenance-closure checking WITHOUT identity gating.

    Every replica computes the SAME global 'trusted' set: an event is
    trusted iff all of its deps are themselves trusted (recursive closure
    from assert_world roots), regardless of whose actor/target field it
    carries. There is no per-replica projection at all -- K is identical
    for every replica that has merged the same E. This isolates whether
    closure-checking alone (without gating admission by requester
    identity) gives any confidentiality property. Expectation: it should
    NOT -- closure checking answers "is this claim well-supported",  not
    "who is allowed to know it", so it should degenerate toward the same
    failure mode as naive union once a well-formed workload has few
    actually-invalid events to reject.
    """

    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)
    E: Dict[Dot, Event] = field(default_factory=dict)

    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    def assert_world(self, fact: str) -> Event:
        dot = self._new_dot()
        e = Event(dot=dot, kind="assert_world", fact=fact, actor=self.replica_id)
        self.E[dot] = e
        self.W.add(fact, dot)
        return e

    def observe(self, fact: str) -> Event:
        if not self.W.contains(fact):
            raise ValueError(f"cannot OBSERVE {fact!r}")
        dot = self._new_dot()
        e = Event(dot=dot, kind="observe", fact=fact, actor=self.replica_id, deps=self.W.live_dots(fact))
        self.E[dot] = e
        return e

    def communicate(self, target: str, fact: str) -> Event:
        trusted = self.trusted_facts()
        if fact not in trusted:
            raise ValueError(f"cannot COMMUNICATE {fact!r}")
        dot = self._new_dot()
        # deps = whatever trusted dots exist for this fact (no identity restriction)
        supporting = {d for d, e in self.E.items() if e.fact == fact}
        e = Event(dot=dot, kind="communicate", fact=fact, actor=self.replica_id, target=target,
                   deps=frozenset(supporting))
        self.E[dot] = e
        return e

    def merge(self, other: "ClosureOnlyReplica") -> None:
        self.W = self.W.join(other.W)
        for dot, e in other.E.items():
            self.E.setdefault(dot, e)

    def trusted_facts(self) -> Set[str]:
        """Global closure: an event is trusted iff every dep is trusted.
        No actor/target check anywhere -- the ablation."""
        trusted_dots: Set[Dot] = set()
        for e in _topo_order(self.E):
            if e.kind in ("assert_world", "retract_world"):
                trusted_dots.add(e.dot)
                continue
            if e.deps <= trusted_dots or not e.deps:
                trusted_dots.add(e.dot)
        return {self.E[d].fact for d in trusted_dots if self.E[d].kind in ("observe", "communicate", "infer")}

    def knows(self, fact: str) -> bool:
        return fact in self.trusted_facts()

    def materialized_facts(self) -> Set[str]:
        return self.trusted_facts()
