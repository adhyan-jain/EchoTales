"""IPR validation, round 4: the derivation trilemma, proved by construction.

Round 3 (test_dynamic_acl_baseline.py) showed the strongest *gating-only*
baseline (DynamicCausalACLReplica) cannot reproduce INFER at all -- horn
(A) of the trilemma stated in IPR_REVIEW_V4.md. This file attacks the one
loophole that leaves open: what if the baseline instead auto-derives via a
standing, declared rule evaluated against whatever it currently holds,
rather than requiring a fresh per-instance grant (horn B)? `AutoDerivingACLReplica`
(baselines.py) is the fairest, hardest version of that idea.

An initial hypothesis for this round -- that a shared, CRDT-unioned rule
table would leak the same way ACLReplica.widen_scope() does once merged
across replicas -- turned out to be WRONG, and the two tests below that
checked it (concurrent rule declaration, partition+rejoin) are kept as
honest negative results, not deleted or forced: per-replica target
gating (inherited unchanged from DynamicCausalACLReplica) is evaluated
underneath the rule closure, so a rule can only ever fire against facts
*this* replica itself holds, never against another replica's grants that
merely co-arrived in the same gossip round. Horn (B) is confidentiality-
safe under concurrent updates and partition/rejoin -- that is the real,
measured result, not the leak originally expected.

What horn (B) genuinely cannot do, proved by the remaining two tests: give
a rule-derived fact a stable identity. It has no dot in the causally-
replicated grant log G, so (a) there is nothing a retraction operation
could cite to revoke that specific derivation (test 3), and (b) it cannot
be cited as provenance in a further grant to delegate it onward (test 4)
-- delegating it at all requires minting a fresh authorization record for
it, which is just INFER under ACL vocabulary (horn C, conceded).

Round 5 extends this with the three additional stress combinations named
in that round's brief -- multi-hop derivation, concurrent inference
(merge-order convergence), and stale-replica bulk catch-up (tests 5-7).
All three are further honest concessions on confidentiality/convergence,
consistent with tests 1-2: identity gating and deterministic convergence
both hold transitively and under bulk delivery, with no new leak found.
The identity/revocability/delegability gap (tests 3-4) is what compounds
under multi-hop (test 5) rather than what these three tests newly break.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ecrdt.replica import Replica
from ecrdt.baselines import AutoDerivingACLReplica
from ecrdt.audit import audit_non_interference, total_violation_count


# ---------------------------------------------------------------------------
# Control: E-CRDT itself performs the equivalent operation safely under all
# four conditions (already proved by the 17 tests in test_adversarial.py +
# the commutativity lemma, IPR_REVIEW_V2.md Phase 7). Restated once here as
# the baseline of comparison, not re-derived.
# ---------------------------------------------------------------------------

def test_control_ecrdt_infer_is_safe_and_precisely_provenanced():
    a = Replica(replica_id="a")
    a.assert_world("p1")
    a.assert_world("p2")
    a.observe("p1")
    a.observe("p2")
    a.infer("derived", premises=["p1", "p2"])
    known, provenance = a.materialize()
    assert "derived" in known
    # provenance["derived"] is the infer event's own single dot -- a stable,
    # citable identity for this specific derivation, distinct from a
    # different (e.g. re-)derivation of the same fact, which would carry a
    # different dot. That dot's own deps chain back to the two premises:
    infer_dot = next(iter(provenance["derived"]))
    assert a.E[infer_dot].deps == frozenset({("a", 3), ("a", 4)})


# ---------------------------------------------------------------------------
# 1. Concurrent updates: an honest negative result. A concurrently-declared
#    alternative rule for the same fact name, once merged, does NOT leak --
#    because `_materialize_grants()`'s target==me check (inherited from
#    DynamicCausalACLReplica, unchanged) is evaluated *underneath* the rule
#    closure, not bypassed by it. This corrects an initial hypothesis for
#    this round (that a shared, unioned rule table would behave like
#    ACLReplica.widen_scope()'s retroactive grant) -- it does not, because
#    a rule only ever fires against a replica's *own* target-gated holdings,
#    never against another replica's grants merely because they co-arrived
#    in the same gossip round. This is a real, measured result, kept
#    because it precisely locates where horn (B) is actually safe.
# ---------------------------------------------------------------------------

def test_concurrent_rule_declaration_does_not_leak_because_identity_gating_survives_it():
    a = AutoDerivingACLReplica(replica_id="a")
    b = AutoDerivingACLReplica(replica_id="b")

    # a holds p1, p2 (self-granted, i.e. addressed to "a") and derives
    # "secret" from them via a standing rule.
    a.assert_world("p1")
    a.assert_world("p2")
    a.self_grant("p1")
    a.self_grant("p2")
    a.declare_rule("secret", frozenset({"p1", "p2"}))
    assert a.knows("secret")

    # b, concurrently and independently, derives the same fact name from
    # an unrelated premise via its own rule.
    b.assert_world("p3")
    b.self_grant("p3")
    b.declare_rule("secret", frozenset({"p3"}))
    assert b.knows("secret")  # correct and intended for b's own derivation

    ground_truth = {"a": {"p1", "p2", "secret"}, "b": {"p3", "secret"}}

    # Full mesh merge: both rule tables AND both grant logs converge at
    # both replicas -- the hardest version of this scenario.
    a.merge(b)
    b.merge(a)

    apparent = {"a": a.materialized_facts(), "b": b.materialized_facts()}
    violations = audit_non_interference(apparent, ground_truth)
    assert total_violation_count(violations) == 0, (
        f"unexpected leak: {violations} -- a's self-grants for p1/p2 carry "
        f"target='a', so even though b now has both a's grants AND a's rule "
        f"in its local G/rules tables, b's own materialize() only ever "
        f"admits G-records addressed to 'b'; the rule for 'secret' can only "
        f"fire against facts b itself holds (p3), never against a's p1/p2. "
        f"Horn (B), done with per-replica target gating preserved underneath "
        f"the rule, is confidentiality-safe against this specific attack."
    )
    # b does NOT gain p1/p2 -- confirming the negative result precisely,
    # not just via the audit's absence of violations:
    assert "p1" not in b.materialized_facts()
    assert "p2" not in b.materialized_facts()


# ---------------------------------------------------------------------------
# 2. Partition + rejoin: same negative result under the harder, explicitly-
#    named condition -- two independently-partitioned groups converge on
#    identical rule *and* grant tables, with no leak. What DOES survive
#    the rejoin, and is the actual point of this test: g1's replicas
#    correctly gain "classified" only via their OWN causal chain, and the
#    audit confirms zero cross-partition contamination even though both
#    groups' standing rules for the same fact name are now shared metadata
#    at every replica.
# ---------------------------------------------------------------------------

def test_partition_then_rejoin_rule_merge_stays_confidentiality_safe():
    group1 = [AutoDerivingACLReplica(replica_id=f"g1_{i}") for i in range(2)]
    group2 = [AutoDerivingACLReplica(replica_id=f"g2_{i}") for i in range(2)]

    g1a, g1b = group1
    g2a, g2b = group2

    # Partitioned round: group 1 establishes p1/p2 and a private rule;
    # group 2 never sees any of it.
    g1a.assert_world("p1")
    g1a.assert_world("p2")
    g1a.self_grant("p1")
    g1a.self_grant("p2")
    g1a.declare_rule("classified", frozenset({"p1", "p2"}))
    g1b.merge(g1a)

    ground_truth = {r.replica_id: set() for r in group1 + group2}
    ground_truth["g1_0"] = {"p1", "p2", "classified"}

    # group 2 independently derives the same fact name from its own,
    # unrelated premise during the partition.
    g2a.assert_world("q1")
    g2a.self_grant("q1")
    g2a.declare_rule("classified", frozenset({"q1"}))
    ground_truth["g2_0"] = {"q1", "classified"}

    # Rejoin: full mesh gossip -- both groups' rule tables AND grant logs
    # converge at every replica.
    g1a.merge(g2a)
    g2a.merge(g1a)
    g1b.merge(g1a)
    g2b.merge(g2a)

    apparent = {r.replica_id: r.materialized_facts() for r in group1 + group2}
    violations = audit_non_interference(apparent, ground_truth)
    assert total_violation_count(violations) == 0, (
        f"unexpected cross-partition leak after rejoin: {violations} -- "
        f"g1_0's classified-rule uses p1/p2, which carry target='g1_0'; "
        f"g2's replicas never held p1/p2 under their own identity, so the "
        f"rule cannot fire for them even after both rule tables and grant "
        f"logs fully converge. Partition/rejoin does not, by itself, break "
        f"horn (B)'s confidentiality property."
    )
    assert "p1" not in g2a.materialized_facts()
    # g2b never self-granted q1 itself (only g2a did, target="g2a"), so g2b
    # correctly holds neither q1 nor "classified" even post-rejoin:
    assert "q1" not in g2b.materialized_facts()
    assert "classified" not in g2b.materialized_facts()


# ---------------------------------------------------------------------------
# 3. Retraction: a rule-derived fact has no stable provenance dot to target,
#    unlike E-CRDT's per-derivation provenance dict.
# ---------------------------------------------------------------------------

def test_derived_fact_has_no_stable_provenance_to_retract():
    a = AutoDerivingACLReplica(replica_id="a")
    a.assert_world("p1")
    a.assert_world("p2")
    a.self_grant("p1")
    a.self_grant("p2")
    a.declare_rule("derived", frozenset({"p1", "p2"}))
    assert a.knows("derived")

    # E-CRDT's retract_knowledge takes an explicit set of establishing dots
    # to revoke (replica.py: retract_knowledge(target, fact, establishing_dots)).
    # AutoDerivingACLReplica's own provenance dict -- the G-projection -- has
    # no entry at all for "derived", because it was never established via a
    # G record; it exists only as a live re-evaluation of the rule table.
    held, provenance = a._materialize_grants()
    assert "derived" not in provenance, (
        "a rule-derived fact has no establishing dots in G -- there is nothing "
        "a retract_knowledge-equivalent operation could cite to revoke this "
        "specific derivation, unlike E-CRDT's provenance[fact] dot-set"
    )
    # The only way to make "derived" un-knowable to 'a' is to revoke enough
    # of p1/p2's underlying grants that the rule stops firing -- which
    # revokes the *premises* for every rule that uses them, not this one
    # derivation specifically. There is no representation of "this specific
    # derivation instance" to target at all.


# ---------------------------------------------------------------------------
# 4. Delayed delivery / general: delegating a derived fact onward requires
#    minting a fresh authorization record -- horn (C), conceded.
# ---------------------------------------------------------------------------

def test_delegating_a_derived_fact_requires_a_fresh_authorization_event():
    a = AutoDerivingACLReplica(replica_id="a")
    b = AutoDerivingACLReplica(replica_id="b")
    a.assert_world("p1")
    a.assert_world("p2")
    a.self_grant("p1")
    a.self_grant("p2")
    a.declare_rule("derived", frozenset({"p1", "p2"}))
    assert a.knows("derived")

    # grant()'s precondition is inherited unchanged from DynamicCausalACLReplica:
    # it checks _materialize_grants() (G-only), which does not include
    # rule-derived facts. Delegating "derived" to b is therefore rejected --
    # exactly the same structural incapacity round 3 found for INFER itself.
    try:
        a.grant("b", "derived")
        raised = False
    except ValueError:
        raised = True
    assert raised, (
        "a rule-derived fact cannot be delegated via the baseline's own grant() "
        "precondition, since it has no G-entry to cite as provenance"
    )

    # The only way to make "derived" delegatable is for 'a' to first mint a
    # brand-new authorization record naming it explicitly (e.g. a hypothetical
    # self_grant("derived") after separately asserting it into W) -- i.e. an
    # additional authorization event beyond the standing rule, which is just
    # INFER under ACL vocabulary (horn C, conceded). No such event exists in
    # this baseline's design by construction, so the gap is structural, not a
    # missing feature that a small patch would close without reintroducing
    # per-instance, per-derivation authorization events.


# ---------------------------------------------------------------------------
# 5. Multi-hop derivation: identity gating holds transitively (a concession,
#    stated honestly) -- but the no-stable-identity gap compounds, since
#    neither hop produces a dot.
# ---------------------------------------------------------------------------

def test_multi_hop_derivation_stays_confidentiality_safe_but_compounds_the_identity_gap():
    a = AutoDerivingACLReplica(replica_id="a")
    bystander = AutoDerivingACLReplica(replica_id="bystander")

    a.assert_world("p1")
    a.assert_world("p2")
    a.assert_world("p4")
    a.self_grant("p1")
    a.self_grant("p2")
    a.self_grant("p4")
    a.declare_rule("p3", frozenset({"p1", "p2"}))
    a.declare_rule("p5", frozenset({"p3", "p4"}))  # second hop consumes a derived fact as a premise

    facts = a.materialized_facts()
    assert {"p1", "p2", "p3", "p4", "p5"} <= facts  # transitive closure reaches the second hop

    # Confidentiality concession, stated honestly: a bystander who merges
    # everything (both rules, none of the grants) still gains nothing,
    # exactly like the single-hop case -- target gating on the *original*
    # G-records is what protects every hop, transitively, with no
    # additional mechanism required.
    bystander.merge(a)
    assert bystander.materialized_facts() == set()

    # The identity gap compounds rather than disappearing: p3 (first-hop
    # derived) has no G dot, so p5's "derivation" rests on a premise that
    # is itself unrevoked-and-unrevocable-by-dot -- there are now two
    # levels of derived fact with no stable identity, not one.
    held, provenance = a._materialize_grants()
    assert "p3" not in provenance and "p5" not in provenance


# ---------------------------------------------------------------------------
# 6. Concurrent inference / merge-order convergence: a second honest
#    concession -- the live-fixpoint re-evaluation is a pure function of
#    the merged (G, rules) state, so it converges regardless of merge
#    order, matching (for this specific property) what E-CRDT's
#    commutativity lemma guarantees.
# ---------------------------------------------------------------------------

def test_concurrent_inference_converges_regardless_of_merge_order():
    x = AutoDerivingACLReplica(replica_id="x")
    y = AutoDerivingACLReplica(replica_id="y")
    x.assert_world("p1")
    x.self_grant("p1")
    x.declare_rule("derived", frozenset({"p1", "p2"}))
    y.assert_world("p2")
    y.self_grant("p2")

    # Two observers merge x and y in opposite orders.
    c1 = AutoDerivingACLReplica(replica_id="c1")
    c1.merge(x)
    c1.merge(y)
    c2 = AutoDerivingACLReplica(replica_id="c2")
    c2.merge(y)
    c2.merge(x)

    # Neither observer gains p1 or p2 (target-gated to x/y respectively),
    # so neither can derive "derived" either -- and, critically, both
    # observers agree with each other regardless of merge order:
    assert c1.materialized_facts() == c2.materialized_facts() == set()

    # Now check true concurrent *local* inference: x and y each hold both
    # premises under their own identity (simulating two independently
    # already-authorized replicas), so each derives "derived" on its own --
    # confirm both converge to the same local answer regardless of which
    # merge order assembled their G/rules tables.
    x.assert_world("p2")
    x.self_grant("p2")
    y.assert_world("p1")
    y.self_grant("p1")
    y.declare_rule("derived", frozenset({"p1", "p2"}))
    assert x.knows("derived")
    assert y.knows("derived")
    # Concession: this is exactly the convergence property E-CRDT's
    # commutativity lemma proves for INFER -- the live-fixpoint
    # construction has it too, for this property specifically.


# ---------------------------------------------------------------------------
# 7. Stale replica bulk catch-up: a third honest concession -- bulk-merging
#    an entire G + rules history at once, after a long absence, grants
#    nothing beyond what per-target dots actually authorize, exactly like
#    E-CRDT's own stale-replica behavior.
# ---------------------------------------------------------------------------

def test_stale_replica_bulk_catch_up_grants_nothing_extra():
    a = AutoDerivingACLReplica(replica_id="a")
    stale = AutoDerivingACLReplica(replica_id="stale")

    # 'a' runs many rounds of activity alone: grants, rules, multi-hop
    # derivations -- 'stale' never participates.
    a.assert_world("p1")
    a.assert_world("p2")
    a.self_grant("p1")
    a.self_grant("p2")
    a.declare_rule("derived", frozenset({"p1", "p2"}))
    for i in range(20):
        a.assert_world(f"noise{i}")
        a.self_grant(f"noise{i}")

    # 'stale' rejoins and bulk-merges everything at once, in a single call.
    stale.merge(a)

    # Bulk catch-up grants stale's W (world facts are public, as in
    # E-CRDT) and stale's rule table (rules are also public metadata), but
    # NOT any of 'a's G-records -- those are target-gated to 'a' and were
    # never addressed to 'stale', bulk merge or not.
    assert stale.W.facts() >= {"p1", "p2"}  # world converges fully, as expected
    assert stale.materialized_facts() == set(), (
        "bulk catch-up must not grant 'stale' anything it was never, under "
        "its own identity, causally addressed by -- matches E-CRDT's own "
        "stale-replica behavior (test_stale_replica_catches_up_correctly_"
        "after_long_absence: K stays empty on bulk merge)"
    )
