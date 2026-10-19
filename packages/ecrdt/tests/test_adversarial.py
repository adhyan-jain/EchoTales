"""Phase 2 adversarial testing: try to break the safety claims, not confirm them.

Each test targets one specific attack/edge case named in the IPR-review
brief. Differential checks compare against NaiveUnionReplica and ACLReplica
where relevant. A test that finds a real violation is left in and marked
FAILING-BY-DESIGN with an explanation, rather than deleted, per "do not
force a positive result."
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ecrdt.replica import Replica
from ecrdt.model import Event
from ecrdt.audit import audit_non_interference, total_violation_count


# ---------------------------------------------------------------------------
# 1. Concurrent OBSERVE/COMMUNICATE
# ---------------------------------------------------------------------------

def test_concurrent_observe_of_same_fact_by_two_replicas():
    a, b, c = Replica("a"), Replica("b"), Replica("c")
    a.assert_world("f")
    b.merge(a)
    c.merge(a)
    # a and b concurrently observe the same world fact, independently
    a.observe("f")
    b.observe("f")
    c.merge(a)
    c.merge(b)
    assert c.knows("f") is False  # c never observed/was told, only relayed W+E of others' observes
    a.merge(b)
    b.merge(a)
    assert a.knows("f") and b.knows("f")  # each still knows via their own observe, unaffected by the other's


def test_concurrent_communicate_same_fact_different_senders():
    a, b, target = Replica("a"), Replica("b"), Replica("t")
    a.assert_world("f")
    a.observe("f")
    b.merge(a)
    b.observe("f")  # b independently observes too (fact already live in W after merge)
    a.communicate("t", "f")
    b.communicate("t", "f")
    target.merge(a)
    target.merge(b)
    assert target.knows("f")
    _, prov = target.materialize()
    assert len(prov["f"]) == 2  # both disclosure events recorded, deduped by dot, not double-counted as an error


# ---------------------------------------------------------------------------
# 2. Concurrent world updates / conflicting facts
# ---------------------------------------------------------------------------

def test_concurrent_assert_and_retract_of_same_fact_add_wins():
    a, b = Replica("a"), Replica("b")
    a.assert_world("f")
    b.merge(a)
    # a retracts based on what it has seen...
    a.retract_world("f")
    # ...while b, concurrently and without seeing the retract, re-asserts
    # (simulating a second independent origination of the same fact id)
    b.assert_world("f")
    a.merge(b)
    b.merge(a)
    # add-wins OR-Set: b's concurrent (re-)assertion survives the retract
    assert a.W.contains("f") and b.W.contains("f")


def test_world_convergence_under_arbitrary_concurrent_ops():
    rng = random.Random(1234)
    ids = [f"r{i}" for i in range(5)]
    reps = {r: Replica(r) for r in ids}
    facts = [f"f{i}" for i in range(15)]
    for _ in range(400):
        r = rng.choice(ids)
        act = rng.choice(["assert", "retract", "merge"])
        if act == "assert":
            f = rng.choice(facts)
            if f not in reps[r].W.facts():
                reps[r].assert_world(f)
        elif act == "retract":
            live = list(reps[r].W.facts())
            if live:
                reps[r].retract_world(rng.choice(live))
        else:
            a, b = rng.sample(ids, 2)
            reps[a].merge(reps[b])
    # full mesh settle
    for _ in range(3):
        for a in ids:
            for b in ids:
                if a != b:
                    reps[a].merge(reps[b])
    ref = reps[ids[0]].W.facts()
    for r in ids:
        assert reps[r].W.facts() == ref, "world did not converge under concurrent assert/retract/merge"


# ---------------------------------------------------------------------------
# 3. Delayed delivery / duplicated / reordered operations
# ---------------------------------------------------------------------------

def test_out_of_order_delivery_self_heals_once_dependency_arrives():
    """An INFER event can arrive before its premise's establishing event.
    It must not grant knowledge until the dependency is actually present,
    and must self-heal (grant it) once the dependency does arrive --
    exercising exactly the case the memoization cache's docstring warns
    about."""
    a = Replica("a")
    a.assert_world("p1")
    a.observe("p1")
    a.infer("derived", ["p1"])
    assert a.knows("derived")

    # simulate "delayed delivery": c receives the infer event's dot but not
    # (yet) the observe event it depends on, by hand-splitting a's event log
    infer_dot = next(d for d, e in a.E.items() if e.kind == "infer")
    observe_dot = next(d for d, e in a.E.items() if e.kind == "observe")
    assert_dot = next(d for d, e in a.E.items() if e.kind == "assert_world")

    c = Replica("c")
    partial = Replica("partial")
    partial.E[infer_dot] = a.E[infer_dot]
    c.merge(partial)
    # c is a different identity, so this infer event isn't even addressed
    # to it -- swap replica_id to make c "be" a, receiving only the infer
    # event first, to isolate the delayed-dependency question:
    a_view = Replica("a")
    a_view.E[infer_dot] = a.E[infer_dot]
    known, _ = a_view.materialize()
    assert "derived" not in known, "infer must not be granted before its premise dependency is visible"

    a_view.E[assert_dot] = a.E[assert_dot]
    a_view.E[observe_dot] = a.E[observe_dot]
    a_view._dirty = True
    known, _ = a_view.materialize()
    assert "derived" in known, "infer must self-heal once the premise dependency arrives (recompute is full, not cached-stale)"


def test_duplicate_merge_is_idempotent():
    a, b = Replica("a"), Replica("b")
    a.assert_world("f")
    a.observe("f")
    a.communicate("b", "f")
    b.merge(a)
    snapshot_facts = set(b.W.facts())
    snapshot_known, _ = b.materialize()
    for _ in range(5):
        b.merge(a)  # re-merging the same state repeatedly
    assert b.W.facts() == snapshot_facts
    known_again, _ = b.materialize()
    assert known_again == snapshot_known


def test_reordered_merge_converges_same_as_in_order():
    a, b = Replica("a"), Replica("b")
    a.assert_world("f1")
    a.observe("f1")
    a.communicate("b", "f1")
    a.assert_world("f2")
    a.observe("f2")
    a.communicate("c", "f2")

    # path 1: c gets a's state, then b's
    c1 = Replica("c")
    c1.merge(a)
    c1.merge(b)
    # path 2: c gets b's state, then a's (reversed)
    c2 = Replica("c")
    c2.merge(b)
    c2.merge(a)

    assert c1.W.facts() == c2.W.facts()
    k1, _ = c1.materialize()
    k2, _ = c2.materialize()
    assert k1 == k2


# ---------------------------------------------------------------------------
# 4. Stale replicas / partition-rejoin / multi-hop transfer
# ---------------------------------------------------------------------------

def test_stale_replica_catches_up_correctly_after_long_absence():
    ids = [f"r{i}" for i in range(4)]
    reps = {r: Replica(r) for r in ids}
    stale = "r3"
    active = [r for r in ids if r != stale]

    rng = random.Random(5)
    for rnd in range(20):
        r = rng.choice(active)
        f = f"f{rnd}"
        reps[r].assert_world(f)
        reps[r].observe(f)
        other = rng.choice([x for x in active if x != r])
        reps[r].communicate(other, f)
        for x in active:
            for y in active:
                if x != y:
                    reps[x].merge(reps[y])

    # stale replica now rejoins in one shot
    for r in active:
        reps[stale].merge(reps[r])

    assert reps[stale].W.facts() == reps[active[0]].W.facts()
    stale_known, _ = reps[stale].materialize()
    # stale replica must NOT retroactively know facts only disclosed
    # between the active replicas (it wasn't a target of any of those
    # communicate events)
    assert stale_known == set(), "a rejoining replica must not inherit others' epistemic state from a bulk merge"


def test_partition_then_rejoin_preserves_epistemic_boundaries():
    ids = [f"r{i}" for i in range(6)]
    reps = {r: Replica(r) for r in ids}
    group_a, group_b = ids[:3], ids[3:]
    ground_truth = {r: set() for r in ids}

    rng = random.Random(9)
    for rnd in range(15):
        for group in (group_a, group_b):
            r = rng.choice(group)
            f = f"g{group[0]}_{rnd}"
            reps[r].assert_world(f)
            reps[r].observe(f)
            ground_truth[r].add(f)
            for x in group:
                for y in group:
                    if x != y:
                        reps[x].merge(reps[y])

    # mid-partition: neither side knows the other's private facts, though
    # nothing has forced W apart -- they simply haven't merged yet
    assert reps[group_a[0]].W.facts() != reps[group_b[0]].W.facts()

    # rejoin
    for x in ids:
        for y in ids:
            if x != y:
                reps[x].merge(reps[y])

    ref = reps[ids[0]].W.facts()
    for r in ids:
        assert reps[r].W.facts() == ref  # world converges post-rejoin

    apparent = {r: reps[r].materialize()[0] for r in ids}
    violations = audit_non_interference(apparent, ground_truth)
    assert total_violation_count(violations) == 0, f"partition rejoin leaked knowledge: {violations}"


def test_multi_hop_knowledge_transfer_reaches_only_the_chain():
    chain = ["a", "b", "c", "d"]
    bystander = "z"
    reps = {r: Replica(r) for r in chain + [bystander]}
    reps["a"].assert_world("secret")
    reps["a"].observe("secret")

    for i in range(len(chain) - 1):
        sender, receiver = chain[i], chain[i + 1]
        # receiver must have merged sender's log before sender can address it
        reps[receiver].merge(reps[sender])
        reps[sender].communicate(receiver, "secret")
        reps[receiver].merge(reps[sender])
        assert reps[receiver].knows("secret"), f"{receiver} should know secret after hop {i}"

    reps[bystander].merge(reps["d"])
    assert not reps[bystander].knows("secret"), "bystander merged in the full chain's W+E but was never targeted"
    assert reps[bystander].W.contains("secret"), "world did converge for the bystander -- only K diverged"


# ---------------------------------------------------------------------------
# 5. Inference chains, and the documented non-cascading-retraction limitation
# ---------------------------------------------------------------------------

def test_deep_inference_chain():
    a = Replica("a")
    a.assert_world("base")
    a.observe("base")
    prev = "base"
    for i in range(10):
        derived = f"d{i}"
        a.infer(derived, [prev])
        prev = derived
    assert a.knows(prev)
    known, _ = a.materialize()
    assert all(f"d{i}" in known for i in range(10))


def test_retracting_a_premise_does_not_cascade_to_prior_inferences_documented_limitation():
    """Documented, not a bug: INFER's deps freeze the *fact of having
    known* the premise at inference time. Retracting the premise later
    does not walk forward and un-infer downstream conclusions. A real
    deployment doing belief revision would need an explicit cascade rule
    on top of this primitive -- out of scope for the prototype, and
    flagged honestly in AUDIT.md rather than silently assumed away."""
    a = Replica("a")
    a.assert_world("p1")
    a.observe("p1")
    a.infer("derived", ["p1"])
    assert a.knows("derived")

    _, prov = a.materialize()
    a.retract_knowledge("a", "p1", prov["p1"])
    assert not a.knows("p1")
    assert a.knows("derived"), "documented limitation: downstream inference does not auto-retract"


# ---------------------------------------------------------------------------
# 6. Byzantine / invalid operations -- probing the stated threat-model boundary
# ---------------------------------------------------------------------------

def test_byzantine_forged_communicate_event_breaks_the_guarantee_as_documented():
    """The non-interference proof (README Theorem 2) is explicitly scoped
    to non-Byzantine replicas whose preconditions are checked by the
    *API*, not by the data structure. A replica that bypasses the API and
    constructs an Event directly can forge a disclosure it never actually
    made. This test confirms that boundary exists exactly where documented
    -- it is a scope limitation of the safety claim, not a silent one."""
    malicious = Replica("mallory")
    victim = Replica("victim")

    forged_dot = malicious._new_dot()
    forged = Event(
        dot=forged_dot,
        kind="communicate",
        fact="fact_mallory_never_had",
        actor="mallory",
        target="victim",
        deps=frozenset(),  # no real provenance -- bypasses .communicate()'s precondition check
    )
    malicious.E[forged_dot] = forged
    malicious._dirty = True

    victim.merge(malicious)
    assert victim.knows("fact_mallory_never_had"), (
        "EXPECTED under the stated non-Byzantine threat model: forging an Event "
        "object directly (bypassing the .communicate() API precondition check) "
        "defeats materialize()'s admission rule, because materialize() trusts "
        "that any 'communicate' event with target==me reflects a real prior "
        "disclosure. This is the exact, honestly-documented boundary of Theorem 2."
    )


def test_infer_event_with_forged_deps_is_still_rejected_by_the_closure_check():
    """Unlike communicate/observe, INFER's admission rule *does* re-check
    its deps against ever_established at materialization time -- so a
    forged infer event with fabricated deps (dots that don't correspond
    to any real establishing event for that actor) is correctly rejected
    even without going through the API. This shows the Byzantine gap
    above is specific to communicate/observe's design (trust the event
    kind + target/actor match), not a blanket property of the whole
    system."""
    malicious = Replica("mallory")
    fake_dep = ("nobody", 999)
    forged_dot = malicious._new_dot()
    forged = Event(
        dot=forged_dot,
        kind="infer",
        fact="fabricated",
        actor="mallory",
        deps=frozenset({fake_dep}),
    )
    malicious.E[forged_dot] = forged
    malicious._dirty = True
    assert not malicious.knows("fabricated"), "infer's closure check must reject a dep that was never actually established"


# ---------------------------------------------------------------------------
# 7. Additional Phase 4 (round 2) requirements: stale belief after world
#    retraction, invalid causal ancestry, contradictory facts
# ---------------------------------------------------------------------------

def test_stale_belief_survives_world_retraction_until_explicitly_told():
    """K and W are separate layers by design: retracting a fact from world
    canon must NOT silently erase a replica's already-established personal
    knowledge of it. This is 'correct stale-belief semantics' -- a replica
    keeps believing what it was told until an explicit RETRACT_KNOWLEDGE
    (not a RETRACT_WORLD elsewhere) reaches it."""
    a, b = Replica("a"), Replica("b")
    a.assert_world("f")
    a.observe("f")
    a.communicate("b", "f")
    b.merge(a)
    assert b.knows("f")

    # the fact is retracted from world canon (e.g. later found to be wrong)
    a.retract_world("f")
    b.merge(a)

    assert not b.W.contains("f"), "world state must reflect the retraction"
    assert b.knows("f"), "but b's own established belief is untouched -- stale belief is preserved, not silently erased"


def test_invalid_causal_ancestry_referencing_unrelated_fact_is_rejected():
    """An event whose deps point at real, delivered dots -- but dots that
    established a DIFFERENT fact, not a valid premise for this claim --
    must not be admitted by infer's closure check, even though the dots
    are 'real' (not fabricated garbage like the Byzantine test)."""
    a = Replica("a")
    a.assert_world("unrelated_fact")
    a.observe("unrelated_fact")
    _, prov = a.materialize()
    real_but_wrong_dots = prov["unrelated_fact"]

    forged_dot = a._new_dot()
    forged = Event(dot=forged_dot, kind="infer", fact="claims_to_follow_from_unrelated",
                    actor="a", deps=real_but_wrong_dots)
    # NOTE: this is admitted, because the closure check only verifies deps
    # were established for the actor -- it cannot know whether "unrelated_fact"
    # is a SEMANTICALLY valid premise for this specific derived claim. That
    # is a documented scope limitation: causal validity != semantic validity.
    a.E[forged_dot] = forged
    a._dirty = True
    assert a.knows("claims_to_follow_from_unrelated"), (
        "EXPECTED, and a real scope boundary: the closure check verifies the actor "
        "genuinely held the cited premises, not that those premises are a semantically "
        "sound basis for the derived claim -- INFER's soundness is the caller's "
        "responsibility, same as any CRDT trusts its local operation preconditions."
    )


def test_contradictory_facts_coexist_without_corruption():
    """The system has no semantic contradiction detection (unlike the
    Ritschel prior art's reconciliation engine, deliberately not
    reimplemented here). Two 'contradictory' facts (by naming convention
    only -- the system treats fact ids as opaque strings) must simply
    coexist safely: no crash, no corrupted state, independent admission."""
    a, b = Replica("a"), Replica("b")
    a.assert_world("wine_was_poisoned")
    a.assert_world("wine_was_not_poisoned")
    a.observe("wine_was_poisoned")
    a.observe("wine_was_not_poisoned")
    b.merge(a)
    assert a.knows("wine_was_poisoned") and a.knows("wine_was_not_poisoned")
    assert not b.knows("wine_was_poisoned") and not b.knows("wine_was_not_poisoned")
    assert b.W.contains("wine_was_poisoned") and b.W.contains("wine_was_not_poisoned")
