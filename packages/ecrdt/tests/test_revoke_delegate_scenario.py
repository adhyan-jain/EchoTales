"""The killer-question scenario as a regression suite, pinning the exact
claims `scenario_revoke_delegate.py` prints. Full narrative context and the
IPR-cell-facing writeup: `scenario_revoke_delegate.py`'s module docstring and
its `print_report()` output.

Scenario: OBSERVE(P1), OBSERVE(P2), INFER(P1,P2 -> F), REVOKE(F),
DELEGATE(F -> B) -- plus partition/concurrent-update/rejoin, plus the
airtight same-replica double-derivation case.

Killer question: can "standard derived-data authorization" (US7734649
shape) or "ECAC-style causal authorization" represent and safely revoke or
delegate exactly one local derivation instance without issuing a new
external authorization event? Answer pinned here: no, for both, each for a
distinct, precisely characterized reason.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ecrdt.baselines import AutoDerivingACLReplica, StandardDerivedDataAuthReplica
from ecrdt.replica import Replica

# ---------------------------------------------------------------------------
# Single-derivation scenario, one replica.
# ---------------------------------------------------------------------------

def test_system1_infer_succeeds_but_revoke_is_not_instance_scoped():
    a = StandardDerivedDataAuthReplica(replica_id="a")
    a.assert_world("p1", visible_to=frozenset({"a"}))
    a.assert_world("p2", visible_to=frozenset({"a"}))
    a.infer("f", premises=["p1", "p2"])
    assert a.knows("f")

    a.revoke("f")
    # Narrowing the only attribute slot for "f" to empty means "shared with
    # everyone" under this baseline's own visibility convention -- revoke
    # does not merely fail to be instance-scoped, it actively widens access.
    assert a.knows("f"), (
        "revoke() on an exclusively-self-scoped derived fact narrows "
        "visible_to to the empty set, which this baseline's ACLReplica.knows() "
        "convention treats as 'shared' -- confirming revoke has no way to "
        "express 'no longer visible to anyone' for a derived fact at all"
    )


def test_system1_delegate_correctly_excludes_unnamed_bystander_when_only_one_derivation_exists():
    a = StandardDerivedDataAuthReplica(replica_id="a")
    a.assert_world("p1", visible_to=frozenset({"a"}))
    a.assert_world("p2", visible_to=frozenset({"a"}))
    a.infer("f", premises=["p1", "p2"])
    assert a.knows("f")
    assert a.scope.get("f") == frozenset({"a"})  # still restricted -- clean setup, independent of revoke's side effects above

    a.delegate("f", "b")
    assert a.scope.get("f") == frozenset({"a", "b"})  # widen_scope unions in exactly the named target

    bystander = StandardDerivedDataAuthReplica(replica_id="bystander")
    bystander.merge(a)
    # Measured, not assumed: when only ONE derivation of "f" exists, a named
    # delegate() call correctly excludes an unnamed bystander -- widen_scope
    # adds exactly the named target, nothing more. The real limitation (next
    # test) shows up only once a SECOND derivation of the same name exists.
    assert not bystander.knows("f")


def test_system1_delegate_is_not_scoped_to_one_derivation_once_a_second_exists():
    a = StandardDerivedDataAuthReplica(replica_id="a")
    a.assert_world("p1", visible_to=frozenset({"a"}))
    a.assert_world("p2", visible_to=frozenset({"a"}))
    a.infer("f", premises=["p1", "p2"])  # derivation #1, scope={"a"}
    a.assert_world("p5", visible_to=frozenset({"a", "trusted_only"}))
    a.infer("f", premises=["p5"])        # derivation #2, a DIFFERENT restriction, same name -- overwrites #1's scope value
    assert a.scope.get("f") == frozenset({"a", "trusted_only"})  # only #2's classification survives; #1's is gone without a trace

    a.delegate("f", "b")
    # There was never a way to say "delegate #1 to b" vs "delegate #2 to b" --
    # the call can only ever act on whichever classification currently
    # occupies the one attribute slot for the name "f".
    assert a.scope.get("f") == frozenset({"a", "trusted_only", "b"}), (
        "delegate() grants 'b' access to whatever 'f' currently means (here, "
        "derivation #2's classification, since #1's was already overwritten) -- "
        "there is no per-derivation target to address a delegation to"
    )


def test_system2_infer_succeeds_revoke_has_no_target_delegate_requires_extra_event():
    a = AutoDerivingACLReplica(replica_id="a")
    a.assert_world("p1")
    a.assert_world("p2")
    a.self_grant("p1")
    a.self_grant("p2")
    a.declare_rule("f", frozenset({"p1", "p2"}))
    assert a.knows("f")

    _, provenance = a._materialize_grants()
    assert "f" not in provenance, (
        "a rule-derived fact has no G-dot -- there is nothing a revoke "
        "operation could cite, matching test_derivation_impossibility.py's "
        "test_derived_fact_has_no_stable_provenance_to_retract"
    )

    raised = False
    try:
        a.grant("b", "f")
    except ValueError:
        raised = True
    assert raised, (
        "delegating a rule-derived fact is rejected outright by grant()'s own "
        "precondition -- the only fix is minting a fresh authorization record "
        "for 'f' first, i.e. exactly one new external authorization event"
    )


def test_system3_revoke_and_delegate_are_precise_and_free():
    a = Replica(replica_id="a")
    a.assert_world("p1")
    a.assert_world("p2")
    a.observe("p1")
    a.observe("p2")
    a.infer("f", premises=["p1", "p2"])
    known, provenance = a.materialize()
    assert "f" in known
    infer_dots = provenance["f"]

    a.retract_knowledge(target="a", fact="f", establishing_dots=infer_dots)
    known_after, _ = a.materialize()
    assert "f" not in known_after, "retract_knowledge cites the exact infer dot -- precise revocation"

    a.infer("f", premises=["p1", "p2"])
    a.communicate("b", "f")  # delegation, as a single ordinary event -- no extra step required
    known_final, _ = a.materialize()
    assert "f" in known_final, "delegation does not consume the delegator's own knowledge"


# ---------------------------------------------------------------------------
# Partition / concurrent update / rejoin: same fact name, different premises,
# different replicas.
# ---------------------------------------------------------------------------

def test_system1_concurrent_divergent_derivations_are_indistinguishable_after_merge():
    a = StandardDerivedDataAuthReplica(replica_id="a")
    c = StandardDerivedDataAuthReplica(replica_id="c")
    a.assert_world("p1", visible_to=frozenset({"a"}))
    a.assert_world("p2", visible_to=frozenset({"a"}))
    a.infer("f", premises=["p1", "p2"])
    c.assert_world("q1", visible_to=frozenset({"c"}))
    c.infer("f", premises=["q1"])
    a.merge(c)
    c.merge(a)
    # Both derivations now share exactly one scope["f"] entry (union), with
    # no record distinguishing which replica's derivation contributed what.
    assert a.scope.get("f") == c.scope.get("f") == frozenset({"a", "c"})


def test_system2_concurrent_divergent_derivations_stay_confidentiality_safe_but_have_no_identity():
    a = AutoDerivingACLReplica(replica_id="a")
    c = AutoDerivingACLReplica(replica_id="c")
    a.assert_world("p1")
    a.assert_world("p2")
    a.self_grant("p1")
    a.self_grant("p2")
    a.declare_rule("f", frozenset({"p1", "p2"}))
    c.assert_world("q1")
    c.self_grant("q1")
    c.declare_rule("f", frozenset({"q1"}))
    a.merge(c)
    c.merge(a)
    assert a.knows("f") and c.knows("f")  # each derives independently, safely (no leak)
    _, prov_a = a._materialize_grants()
    _, prov_c = c._materialize_grants()
    assert "f" not in prov_a and "f" not in prov_c, (
        "safe under concurrency (matching test_concurrent_rule_declaration_"
        "does_not_leak_because_identity_gating_survives_it), but neither "
        "replica's derivation has an identity to revoke, concurrently "
        "derived or not"
    )


def test_system3_concurrent_divergent_derivations_carry_distinct_dots_and_revoke_precisely():
    a = Replica(replica_id="a")
    c = Replica(replica_id="c")
    a.assert_world("p1")
    a.assert_world("p2")
    a.observe("p1")
    a.observe("p2")
    a.infer("f", premises=["p1", "p2"])
    c.assert_world("q1")
    c.observe("q1")
    c.infer("f", premises=["q1"])
    a.merge(c)
    c.merge(a)
    _known_a, prov_a = a.materialize()
    _known_c, prov_c = c.materialize()
    assert prov_a["f"] != prov_c["f"], "distinct dots for distinct derivations, even sharing a fact name"

    a.retract_knowledge(target="a", fact="f", establishing_dots=prov_a["f"])
    known_a_after, _ = a.materialize()
    known_c_after, _ = c.materialize()
    assert "f" not in known_a_after
    assert "f" in known_c_after, "revoking a's derivation must not touch c's independently-established one"


# ---------------------------------------------------------------------------
# The airtight case: ONE replica, TWO derivations of the same fact name,
# from disjoint premises. Removes any ambiguity about which replica's id
# happens to sit in which attribute.
# ---------------------------------------------------------------------------

def test_system1_same_replica_double_derivation_cannot_revoke_just_one():
    a = StandardDerivedDataAuthReplica(replica_id="a")
    a.assert_world("p1", visible_to=frozenset({"a"}))
    a.assert_world("p2", visible_to=frozenset({"a"}))
    a.infer("f", premises=["p1", "p2"])  # derivation #1
    a.assert_world("p3", visible_to=frozenset({"a"}))
    a.assert_world("p4", visible_to=frozenset({"a"}))
    a.infer("f", premises=["p3", "p4"])  # derivation #2, same name, disjoint premises
    a.revoke("f")
    # Revoking narrows {"a"} to frozenset(), which this baseline's own
    # convention treats as "shared with everyone" -- worse than a no-op.
    assert a.knows("f"), (
        "a single revoke() call cannot target just one of two same-named "
        "derivations -- there is exactly one attribute slot, and narrowing "
        "it to empty widens rather than narrows visibility under this "
        "baseline's own semantics"
    )


def test_system2_same_replica_double_derivation_has_no_per_firing_identity():
    a = AutoDerivingACLReplica(replica_id="a")
    a.assert_world("p1")
    a.assert_world("p2")
    a.self_grant("p1")
    a.self_grant("p2")
    a.declare_rule("f", frozenset({"p1", "p2"}))
    a.assert_world("p3")
    a.assert_world("p4")
    a.self_grant("p3")
    a.self_grant("p4")
    a.declare_rule("f", frozenset({"p3", "p4"}))
    assert a.knows("f")
    _, provenance = a._materialize_grants()
    assert "f" not in provenance, (
        "two standing rules for the same name, both satisfiable by a's own "
        "holdings -- the live fixpoint has no notion of 'which rule fired', "
        "so there is no object to address a per-derivation revoke to at all"
    )


def test_system3_same_replica_double_derivation_revokes_precisely():
    a = Replica(replica_id="a")
    a.assert_world("p1")
    a.assert_world("p2")
    a.observe("p1")
    a.observe("p2")
    a.infer("f", premises=["p1", "p2"])  # derivation #1
    _, prov1 = a.materialize()
    deriv1_dots = prov1["f"]

    a.assert_world("p3")
    a.assert_world("p4")
    a.observe("p3")
    a.observe("p4")
    a.infer("f", premises=["p3", "p4"])  # derivation #2, same name, disjoint premises
    _known2, prov2 = a.materialize()
    assert len(prov2["f"]) == 2, "both infer events mint distinct dots, even for the same fact name"

    a.retract_knowledge(target="a", fact="f", establishing_dots=deriv1_dots)
    known3, _ = a.materialize()
    assert "f" in known3, (
        "revoking derivation #1's dot alone must leave derivation #2's dot "
        "live -- 'f' correctly remains known via the surviving derivation, "
        "the exact case systems 1 and 2 cannot represent at all"
    )
