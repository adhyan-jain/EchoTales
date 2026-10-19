import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ecrdt.replica import Replica
from ecrdt.baselines import NaiveUnionReplica, ACLReplica
from ecrdt.audit import audit_non_interference, total_violation_count
from ecrdt.orset import ORSet


def test_world_convergence_commutative_idempotent():
    a = Replica(replica_id="a")
    b = Replica(replica_id="b")
    a.assert_world("f1")
    b.assert_world("f2")
    a.assert_world("f3")

    a2, b2 = Replica(replica_id="a"), Replica(replica_id="b")
    a2.E, a2.W, a2._counter = dict(a.E), a.W, a._counter
    b2.E, b2.W, b2._counter = dict(b.E), b.W, b._counter

    a.merge(b)
    b.merge(a2)

    # order-independent join: both directions converge to the same W
    assert a.W.facts() == b.W.facts() == {"f1", "f2", "f3"}

    # idempotence: merging again changes nothing
    before = set(a.W.facts())
    a.merge(b)
    assert a.W.facts() == before


def test_assert_alone_does_not_grant_knowledge():
    """ASSERT_WORLD updates canon; it is not, by itself, an OBSERVE."""
    a = Replica(replica_id="a")
    a.assert_world("f1")
    assert a.W.contains("f1")
    K, _ = a.materialize()
    assert "f1" not in K


def test_merge_cannot_grant_unearned_knowledge():
    """Core property (Theorem 2 / epistemic non-interference): merging in a
    replica that has more of W, or more of *its own* knowledge, must never
    populate another replica's K with facts it has no disclosure path to."""
    a = Replica(replica_id="a")
    b = Replica(replica_id="b")

    a.assert_world("secret")
    a.observe("secret")
    assert a.knows("secret")

    b.merge(a)  # b now has "secret" in W (world converges)...
    assert b.W.contains("secret")
    assert not b.knows("secret")  # ...but not in K_b (epistemic divergence)


def test_communicate_grants_knowledge_with_provenance():
    a = Replica(replica_id="a")
    b = Replica(replica_id="b")
    a.assert_world("f1")
    a.observe("f1")
    a.communicate("b", "f1")

    b.merge(a)
    assert b.knows("f1")
    _, prov = b.materialize()
    assert "f1" in prov and len(prov["f1"]) >= 1


def test_infer_requires_all_premises_known():
    a = Replica(replica_id="a")
    a.assert_world("p1")
    a.observe("p1")
    try:
        a.infer("derived", ["p1", "p2"])
        assert False, "expected ValueError: p2 unknown"
    except ValueError:
        pass
    a.assert_world("p2")
    a.observe("p2")
    a.infer("derived", ["p1", "p2"])
    assert a.knows("derived")


def test_infer_does_not_leak_to_others():
    a = Replica(replica_id="a")
    b = Replica(replica_id="b")
    a.assert_world("p1")
    a.observe("p1")
    a.infer("private_belief", ["p1"])
    assert a.knows("private_belief")

    b.merge(a)
    # "private_belief" was never asserted into W and a never communicated it
    assert not b.W.contains("private_belief")
    assert not b.knows("private_belief")


def test_retract_knowledge_is_add_wins_under_concurrency():
    a = Replica(replica_id="a")
    b = Replica(replica_id="b")
    a.assert_world("f1")
    a.observe("f1")
    a.communicate("b", "f1")
    b.merge(a)
    _, prov = b.materialize()
    dots = prov["f1"]

    # a concurrently revokes b's old knowledge...
    a.retract_knowledge("b", "f1", dots)
    # ...but b independently re-observes it (concurrent, causally later
    # from b's perspective) before merging the retraction
    b.observe("f1")

    b.merge(a)
    assert b.knows("f1"), "a concurrent re-establishment must survive an older retraction (add-wins)"


def test_retraction_removes_stale_knowledge_when_not_concurrent():
    a = Replica(replica_id="a")
    b = Replica(replica_id="b")
    a.assert_world("f1")
    a.observe("f1")
    a.communicate("b", "f1")
    b.merge(a)
    assert b.knows("f1")
    _, prov = b.materialize()
    dots = prov["f1"]

    a.retract_knowledge("b", "f1", dots)
    b.merge(a)
    assert not b.knows("f1")


def test_naive_baseline_leaks_everything():
    a = NaiveUnionReplica(replica_id="a")
    b = NaiveUnionReplica(replica_id="b")
    a.assert_world("secret")
    b.merge(a)
    assert b.knows("secret")  # by construction: K_i := W


def test_acl_baseline_retroactive_widen_is_a_measurable_leak():
    a = ACLReplica(replica_id="a")
    b = ACLReplica(replica_id="b")
    a.assert_world("secret", visible_to=frozenset({"a"}))
    b.merge(a)
    assert not b.knows("secret")  # correctly scoped, initially

    ground_truth = {"a": {"secret"}, "b": set()}
    apparent = {"a": a.materialized_facts(), "b": b.materialized_facts()}
    assert total_violation_count(audit_non_interference(apparent, ground_truth)) == 0

    # widen scope after the fact -- an attribute mutation, not a causal
    # disclosure event
    b.widen_scope("secret", frozenset({"b"}))
    assert b.knows("secret")

    apparent = {"a": a.materialized_facts(), "b": b.materialized_facts()}
    violations = audit_non_interference(apparent, ground_truth)
    assert violations.get("b") == {"secret"}, "widening scope must show up as an unauthorized-knowledge leak against ground truth"


def test_orset_join_is_commutative_associative_idempotent():
    stores = [ORSet() for _ in range(3)]
    for i, s in enumerate(stores):
        for k in range(3):
            s.add(f"f{i}_{k}", (f"r{i}", k))

    m1 = stores[0].join(stores[1]).join(stores[2])
    m2 = stores[2].join(stores[0]).join(stores[1])
    m3 = stores[0].join(stores[1].join(stores[2]))
    assert m1.facts() == m2.facts() == m3.facts()

    idem = m1.join(m1)
    assert idem.facts() == m1.facts()


def test_ecrdt_zero_unauthorized_leaks_under_random_workload():
    """Randomized differential test: whatever the random workload, E-CRDT's
    apparent knowledge must never exceed ground-truth disclosure."""
    rng = random.Random(99)
    ids = [f"r{i}" for i in range(5)]
    reps = {r: Replica(replica_id=r) for r in ids}
    ground_truth = {r: set() for r in ids}
    facts = [f"f{i}" for i in range(20)]

    for _ in range(300):
        r = rng.choice(ids)
        op = rng.choice(["assert", "observe", "communicate", "merge"])
        if op == "assert":
            f = rng.choice(facts)
            if f not in reps[r].W.facts():
                reps[r].assert_world(f)
        elif op == "observe":
            live = list(reps[r].W.facts())
            if live:
                f = rng.choice(live)
                try:
                    reps[r].observe(f)
                    ground_truth[r].add(f)
                except ValueError:
                    pass
        elif op == "communicate":
            known, _ = reps[r].materialize()
            other = rng.choice([x for x in ids if x != r])
            if known:
                f = rng.choice(sorted(known))
                reps[r].communicate(other, f)
                ground_truth[other].add(f)
        else:
            a, b = rng.sample(ids, 2)
            reps[a].merge(reps[b])

    apparent = {r: reps[r].materialize()[0] for r in ids}
    violations = audit_non_interference(apparent, ground_truth)
    assert total_violation_count(violations) == 0, f"unauthorized knowledge propagation detected: {violations}"
