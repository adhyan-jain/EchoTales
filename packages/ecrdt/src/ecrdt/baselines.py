"""Three baselines the E-CRDT is benchmarked against.

1. NaiveUnionReplica -- "plain CRDT": W replicates via the same causal
   OR-Set, and K_i is simply defined as K_i = W (whatever converges into the
   world set is, by definition, known to everyone who synced it). This is
   the null hypothesis: ordinary CRDT union with no epistemic layer at all.

2. ACLReplica -- "CRDT + ACL", i.e. exactly the combination the research
   brief says must NOT count as novel, so it needs a working, fair
   implementation to compare against. Every fact carries a static
   `visible_to: frozenset[str]` scope tag fixed at ASSERT_WORLD time (the
   same shape as a Ritschel-style `scope` field or a Policy-CRDT policy
   object). W replicates fully via the causal OR-Set (as in most real ACL+
   CRDT deployments, replication and authorization are separate concerns);
   K_i(query time) = {f in W : i in visible_to[f] or scope[f] == "shared"}.

   The scope tag can be *widened* after the fact (`widen_scope`), which is
   the standard, supported operation in attribute-based access control.
   Because ACL membership is an attribute check against the converged
   store rather than a causally-delivered event, widening a scope
   retroactively grants every already-synced replica access to history it
   was never causally sent -- this is the concrete, measurable gap E-CRDT
   closes (see bench.py scenario `acl_retroactive_grant`).

3. DynamicCausalACLReplica -- the strongest fair reconstruction attempt:
   ordinary CRDT (the same OR-Set as above) + ordinary causal delivery +
   ordinary ACL semantics, with grants themselves delivered as immutable,
   causally-dotted records (no local attribute mutation, no retroactive
   widening at all). This is the "obvious combination" a competent
   engineer would reach for if told "gate access by causal history, not by
   a mutable attribute" without having seen E-CRDT -- it deliberately has
   no INFER-equivalent, since plain ACL vocabulary has no notion of "I
   derived this from what I already hold." See test_dynamic_acl_baseline.py
   for the measured result (it matches E-CRDT's 0-leak confidentiality
   property) and the concrete operation it cannot perform.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Set, Tuple

from .orset import Dot, ORSet
from .replica import _topo_order


@dataclass
class NaiveUnionReplica:
    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)

    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    def assert_world(self, fact: str) -> None:
        self.W.add(fact, self._new_dot())

    def retract_world(self, fact: str) -> None:
        self.W.remove(fact, self.W.live_dots(fact))

    def merge(self, other: "NaiveUnionReplica") -> None:
        self.W = self.W.join(other.W)

    def knows(self, fact: str) -> bool:
        return self.W.contains(fact)

    def materialized_facts(self) -> Set[str]:
        return self.W.facts()


@dataclass
class ACLReplica:
    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)
    scope: Dict[str, FrozenSet[str]] = field(default_factory=dict)  # fact -> visible_to (empty == shared)

    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    def assert_world(self, fact: str, visible_to: FrozenSet[str] = frozenset()) -> None:
        self.W.add(fact, self._new_dot())
        self.scope[fact] = visible_to

    def widen_scope(self, fact: str, new_visible_to: FrozenSet[str]) -> None:
        """Attribute mutation in place -- no causal event, no delivery."""
        self.scope[fact] = self.scope.get(fact, frozenset()) | new_visible_to

    def retract_world(self, fact: str) -> None:
        self.W.remove(fact, self.W.live_dots(fact))

    def merge(self, other: "ACLReplica") -> None:
        self.W = self.W.join(other.W)
        for f, vis in other.scope.items():
            self.scope[f] = self.scope.get(f, frozenset()) | vis

    def knows(self, fact: str) -> bool:
        if not self.W.contains(fact):
            return False
        vis = self.scope.get(fact, frozenset())
        return (not vis) or (self.replica_id in vis)

    def materialized_facts(self) -> Set[str]:
        return {f for f in self.W.facts() if self.knows(f)}


@dataclass(frozen=True)
class GrantEvent:
    """An ACL grant, reified as an immutable causally-dotted record -- the
    ACL analogue of an E-CRDT Event, deliberately restricted to a single
    kind (there is no GRANT-equivalent of INFER)."""

    dot: Dot
    fact: str
    granter: str
    target: str
    deps: FrozenSet[Dot] = field(default_factory=frozenset)


@dataclass
class DynamicCausalACLReplica:
    """CRDT + causal delivery + ACL, with grants gated by causal history
    instead of a mutable attribute -- the hardest-to-beat baseline the
    research brief's Step 4 asks for. A grant is minted only if the
    granter's own materialized access already includes the fact (the same
    precondition shape as E-CRDT's COMMUNICATE), and a replica's access is
    a pure projection over the causally-replicated grant log `G`, exactly
    as K_i is a pure projection over E in replica.py. The one thing this
    baseline structurally cannot express is INFER: there is no operation
    for "derive a new fact from facts I already hold" that doesn't require
    an external party to mint a new grant for that specific derived fact --
    see test_dynamic_acl_baseline.py for the concrete counterexample.
    """

    replica_id: str
    _counter: int = 0
    W: ORSet = field(default_factory=ORSet)
    G: Dict[Dot, GrantEvent] = field(default_factory=dict)

    def _new_dot(self) -> Dot:
        self._counter += 1
        return (self.replica_id, self._counter)

    def assert_world(self, fact: str) -> None:
        self.W.add(fact, self._new_dot())

    def retract_world(self, fact: str) -> None:
        self.W.remove(fact, self.W.live_dots(fact))

    def self_grant(self, fact: str) -> GrantEvent:
        """The ACL analogue of OBSERVE: a replica's own standing access to
        a fact it can see live in W. Precondition mirrors observe()."""
        if not self.W.contains(fact):
            raise ValueError(f"cannot self-grant {fact!r}: not live in W at {self.replica_id}")
        dot = self._new_dot()
        g = GrantEvent(dot=dot, fact=fact, granter=self.replica_id, target=self.replica_id)
        self.G[dot] = g
        return g

    def grant(self, target: str, fact: str) -> GrantEvent:
        """Precondition: granter must itself already hold access -- the
        same fairness constraint as E-CRDT's COMMUNICATE precondition."""
        held, provenance = self._materialize_grants()
        if fact not in held:
            raise ValueError(f"cannot GRANT {fact!r}: {self.replica_id} does not hold it")
        dot = self._new_dot()
        g = GrantEvent(
            dot=dot, fact=fact, granter=self.replica_id, target=target,
            deps=frozenset(provenance[fact]),
        )
        self.G[dot] = g
        return g

    def merge(self, other: "DynamicCausalACLReplica") -> None:
        self.W = self.W.join(other.W)
        for dot, g in other.G.items():
            self.G.setdefault(dot, g)

    def _materialize_grants(self) -> Tuple[Set[str], Dict[str, FrozenSet[Dot]]]:
        """Pure projection over the causally-replicated grant log G, gated
        by target identity -- structurally identical in shape to
        replica.Replica.materialize()'s observe/communicate handling, with
        no infer-equivalent branch to admit."""
        me = self.replica_id
        held: Dict[str, Set[Dot]] = {}
        for g in _topo_order(self.G):  # type: ignore[arg-type]
            if g.target == me:
                held.setdefault(g.fact, set()).add(g.dot)
        K = {f for f, dots in held.items() if dots}
        return K, {f: frozenset(d) for f, d in held.items()}

    def knows(self, fact: str) -> bool:
        held, _ = self._materialize_grants()
        return fact in held

    def materialized_facts(self) -> Set[str]:
        held, _ = self._materialize_grants()
        return held


@dataclass
class StandardDerivedDataAuthReplica(ACLReplica):
    """"Standard derived-data authorization" -- the US7734649 shape, not a
    strawman: a fixed composition rule assigns a derived data element's
    access classification from its inputs' classifications at derivation
    time, stored as a mutable per-fact attribute (`scope`, inherited from
    ACLReplica), with no causal event log and no per-derivation identity at
    all. This is deliberately the *simplest* fair reconstruction of that
    patent's disclosed mechanism, scaled down to this experiment's
    3-operation scenario (OBSERVE/INFER/REVOKE/DELEGATE) -- see
    `scenario_revoke_delegate.py` for the side-by-side comparison this
    class exists to support.

    Composition rule: derived scope = intersection of premise scopes (the
    conventional "least privilege" composition -- a derived fact should not
    be visible to someone who could not see every input it came from). An
    empty scope on any premise (the shared/public convention used
    throughout this baseline suite) is treated as "no restriction" for the
    intersection, i.e. it does not narrow the result -- matching
    ACLReplica's own `scope[f] == frozenset()` == shared convention.
    """

    def infer(self, derived_fact: str, premises: list[str]) -> None:
        """Precondition: this replica must itself know every premise --
        the same fairness constraint every other system's INFER-equivalent
        in this suite uses. No dot, no deps, no provenance: the derived
        fact's scope is computed once, now, and overwrites whatever was
        there before if this fact name was already derived differently."""
        for p in premises:
            if not self.knows(p):
                raise ValueError(f"cannot INFER {derived_fact!r}: {self.replica_id} does not know {p!r}")
        restrictive = [self.scope.get(p, frozenset()) for p in premises if self.scope.get(p, frozenset())]
        derived_scope: FrozenSet[str] = frozenset.intersection(*restrictive) if restrictive else frozenset()
        self.assert_world(derived_fact, visible_to=derived_scope)
        # assert_world already adds `self` to W with a fresh dot for
        # replication purposes (W must still converge across replicas so
        # this is a fair comparison), but that dot is never consulted by
        # knows()/materialized_facts() -- only `scope` is. This is the
        # concrete manifestation of "no per-derivation identity": the dot
        # exists only to make the fact replicate, not to name this
        # derivation instance.

    def revoke(self, fact: str) -> None:
        """The only lever this system has: narrow `scope[fact]` to exclude
        this replica. This is NOT scoped to one derivation instance -- it
        is a mutation of the fact-name-keyed attribute, so it revokes
        every replica's view of every derivation that currently shares
        this fact name, and (being ordinary CRDT-metadata merge, inherited
        from ACLReplica.merge) a concurrent widen_scope() from elsewhere
        can re-open it regardless of intent, exactly like the confidentiality
        leak ACLReplica.widen_scope() already demonstrates for asserted
        (non-derived) facts."""
        current = self.scope.get(fact, frozenset())
        self.scope[fact] = current - frozenset({self.replica_id})

    def delegate(self, fact: str, target: str) -> None:
        """The only lever this system has: widen `scope[fact]` to include
        `target` -- a single mutable-attribute write, immediately visible
        to `target` (no event to deliver), and, per ACLReplica's own
        documented gap, retroactively visible to every replica that already
        synced this fact via W, not merely the one being delegated to."""
        self.widen_scope(fact, frozenset({target}))


@dataclass
class AutoDerivingACLReplica(DynamicCausalACLReplica):
    """Round 4: the fairest, hardest attempt at horn (B) of the derivation
    trilemma (IPR_REVIEW_V4.md) -- a standing, CRDT-replicated *rule* (not
    a fresh per-instance grant) lets a replica treat a derived fact as held
    whenever it currently holds every premise. `rules[fact]` is a set of
    alternative premise-sets (any one satisfied is sufficient), replicated
    by straight union on merge, exactly like any other CRDT metadata --
    deliberately not gated by a causal-delivery check against the specific
    premises being combined for *this* replica, since adding that gate
    would just be re-inventing INFER's closure check under a new name
    (horn C, conceded).

    Confidentiality itself turns out safe here, even under a concurrently-
    declared alternative rule for the same fact name and even under
    partition/rejoin (test_derivation_impossibility.py, tests 1-2, kept as
    honest negative results): `_materialize_grants()`'s target==me gating,
    inherited unchanged, sits underneath the rule closure, so a rule can
    only ever fire against facts *this* replica itself holds under its own
    identity -- never against another replica's grants that merely
    co-arrived in the same merge. What this construction genuinely cannot
    do, without conceding horn (C), is give a rule-derived fact a stable
    identity:

    1. A rule-derived fact has no dot in G at all -- so it cannot be
       cited as `deps` in a further `grant()` call, cannot be individually
       revoked (no establishing-dot to target), and cannot be
       distinguished from a different, later derivation of the same fact
       name from different premises (test_derivation_impossibility.py,
       tests 3-4). `grant()`'s own precondition
       (inherited unchanged) already rejects delegating a fact that has no
       G-entry, so delegating a derived fact at all requires first minting
       a fresh authorization record for it -- an additional authorization
       event, exactly the clause this round is proving.
    """

    rules: Dict[str, Set[FrozenSet[str]]] = field(default_factory=dict)

    def declare_rule(self, derived_fact: str, premises: FrozenSet[str]) -> None:
        self.rules.setdefault(derived_fact, set()).add(frozenset(premises))

    def merge(self, other: "AutoDerivingACLReplica") -> None:
        super().merge(other)
        for fact, rule_set in other.rules.items():
            self.rules.setdefault(fact, set()).update(rule_set)

    def materialized_facts(self) -> Set[str]:
        """G-held facts, closed under standing rules evaluated against
        *currently* held facts -- a pure, deterministic fixpoint over the
        merged (G, rules) state, recomputed fresh every call (no cached
        per-derivation verdict, no dot identity for the result)."""
        held, _ = self._materialize_grants()
        derived: Set[str] = set(held)
        changed = True
        while changed:
            changed = False
            for fact, rule_set in self.rules.items():
                if fact in derived:
                    continue
                if any(premises <= derived for premises in rule_set):
                    derived.add(fact)
                    changed = True
        return derived

    def knows(self, fact: str) -> bool:
        return fact in self.materialized_facts()
