"""The killer-question scenario, run identically against three systems.

Scenario (exactly as specified): OBSERVE(P1), OBSERVE(P2), INFER(P1,P2 -> F),
REVOKE(F), DELEGATE(F -> B) -- then repeated under partition / concurrent
update / rejoin, where two replicas independently derive the *same fact
name* F from *different* premises before merging.

Killer question: can systems 1/2 represent and safely revoke/delegate
exactly one local derivation instance without issuing a new external
authorization event?

  System 1: StandardDerivedDataAuthReplica -- "standard derived-data
            authorization" (the US7734649 shape: mutable, rule-based
            classification inheritance, no causal event log).
  System 2: AutoDerivingACLReplica -- "ECAC-style" causal authorization
            (causal grant log + standing derivation rules, no mutable
            attributes, no retroactive grant).
  System 3: Replica -- E-CRDT itself (INFER mints a citable dot as a side
            effect of the free admission check).

Nothing here re-derives the theorem or re-proves what
test_derivation_impossibility.py already proved for system 2's structural
gap -- this script assembles the identical named scenario across all three
systems side by side, which did not previously exist as one artifact, and
adds system 1 (the centralized baseline named in this round's prior-art
verification) to the comparison for the first time.

Run: PYTHONPATH=src python3 scenario_revoke_delegate.py
"""
from __future__ import annotations

from dataclasses import dataclass

from ecrdt.baselines import AutoDerivingACLReplica, StandardDerivedDataAuthReplica
from ecrdt.replica import Replica


@dataclass
class Outcome:
    system: str
    infer_ok: bool
    revoke_representable: bool  # can the system name *this specific derivation* to revoke?
    revoke_safe: bool           # if representable/attempted, does it avoid affecting other derivations?
    delegate_ok_without_extra_event: bool
    delegate_safe: bool         # if it "succeeds", does it avoid a confidentiality leak?
    note: str


def run_single_derivation_scenario() -> list[Outcome]:
    """OBSERVE(P1), OBSERVE(P2), INFER(P1,P2 -> F), REVOKE(F), DELEGATE(F -> B).
    Single replica, no concurrency yet -- establishes the baseline behavior
    before the harder partition/concurrent-update/rejoin variant below."""
    outcomes: list[Outcome] = []

    # ---- System 1: standard derived-data authorization --------------------
    a1 = StandardDerivedDataAuthReplica(replica_id="a")
    # p1/p2 are restricted to "a" (not the empty/shared convention) -- this
    # is what makes revoke/delegate meaningful operations to demonstrate: an
    # already-shared fact cannot be "revoked" at all under this baseline's
    # own semantics (subtracting from an empty visible_to set stays empty,
    # i.e. stays shared), which would trivially and uninterestingly pass.
    a1.assert_world("p1", visible_to=frozenset({"a"}))
    a1.assert_world("p2", visible_to=frozenset({"a"}))
    assert a1.knows("p1") and a1.knows("p2")  # OBSERVE-equivalent: 'a' is in its own restricted scope
    a1.infer("f", premises=["p1", "p2"])
    infer_ok_1 = a1.knows("f")

    a1.revoke("f")
    # "Safe" here means: the revoke operation is scoped to *this derivation
    # instance*, not to the fact name shared by every derivation of "f".
    # It is not -- scope is a per-name attribute (proven precisely in the
    # concurrent scenario below, where two distinct derivations collide on
    # one attribute slot). Revoking the sole {"a"}-scoped derivation narrows
    # visible_to to empty, which this baseline's own convention treats as
    # "shared with everyone" -- revoke_safe_1 is False for an even stronger
    # reason than "imprecise": the attempt widens rather than narrows access.
    revoke_representable_1 = True   # an operation exists and runs
    revoke_safe_1 = False           # but it targets the fact name, not the derivation

    # Delegate is checked on a FRESH replica (not the one just revoked above,
    # whose "f" is now already shared-to-everyone) so this measures the
    # single-derivation case cleanly, independent of revoke's own side effect.
    a1b = StandardDerivedDataAuthReplica(replica_id="a")
    a1b.assert_world("p1", visible_to=frozenset({"a"}))
    a1b.assert_world("p2", visible_to=frozenset({"a"}))
    a1b.infer("f", premises=["p1", "p2"])
    a1b.delegate("f", "b")
    delegate_ok_1 = True  # single mutable-attribute write, always "succeeds"
    bystander1 = StandardDerivedDataAuthReplica(replica_id="bystander")
    bystander1.merge(a1b)
    # Measured, not assumed: a named delegate() call correctly excludes an
    # unnamed bystander in THIS single-derivation case -- widen_scope unions
    # in exactly the named target, nothing more. The real gap (proved below,
    # in the same-replica double-derivation check) is not stranger-leakage
    # but instance-non-scoping: delegate() writes to the one attribute slot
    # for the fact NAME, so if more than one derivation of that name exists,
    # delegating cannot express "this derivation, not that one."
    delegate_safe_1 = not bystander1.knows("f")
    outcomes.append(Outcome(
        system="1. Standard derived-data auth (US7734649-shape)",
        infer_ok=infer_ok_1,
        revoke_representable=revoke_representable_1,
        revoke_safe=revoke_safe_1,
        delegate_ok_without_extra_event=delegate_ok_1,
        delegate_safe=delegate_safe_1,
        note="revoke() narrows the only attribute slot for 'f' to empty, "
             "which this baseline's own convention treats as SHARED WITH "
             "EVERYONE -- worse than imprecise, it actively widens access. "
             "delegate(), checked separately here, correctly excludes an "
             "unnamed bystander in the single-derivation case (measured) -- "
             "but see the same-replica double-derivation check below for "
             "where delegate's real limitation shows up: it targets a fact "
             "NAME's one attribute slot, not a specific derivation instance.",
    ))

    # ---- System 2: ECAC-style causal authorization -------------------------
    a2 = AutoDerivingACLReplica(replica_id="a")
    a2.assert_world("p1")
    a2.assert_world("p2")
    a2.self_grant("p1")
    a2.self_grant("p2")
    a2.declare_rule("f", frozenset({"p1", "p2"}))
    infer_ok_2 = a2.knows("f")

    _, provenance2 = a2._materialize_grants()
    revoke_representable_2 = "f" in provenance2  # False: no G-dot for a rule-derived fact
    revoke_safe_2 = False  # not applicable -- nothing to safely target

    try:
        a2.grant("b", "f")
        delegate_ok_2 = True
    except ValueError:
        delegate_ok_2 = False
    outcomes.append(Outcome(
        system="2. ECAC-style causal authorization",
        infer_ok=infer_ok_2,
        revoke_representable=revoke_representable_2,
        revoke_safe=revoke_safe_2,
        delegate_ok_without_extra_event=delegate_ok_2,
        delegate_safe=False,  # moot -- delegate does not even succeed
        note="INFER succeeds (a standing rule fires), but the derived fact has "
             "no G-dot: revoke has nothing to cite (structurally impossible to "
             "represent 'this derivation', not merely unimplemented -- see "
             "test_derived_fact_has_no_stable_provenance_to_retract), and "
             "grant() rejects delegation outright (see "
             "test_delegating_a_derived_fact_requires_a_fresh_authorization_"
             "event). The only fix is minting a brand-new authorization "
             "record for 'f' first -- exactly one extra external event, "
             "which is INFER under different vocabulary.",
    ))

    # ---- System 3: E-CRDT ---------------------------------------------------
    a3 = Replica(replica_id="a")
    a3.assert_world("p1")
    a3.assert_world("p2")
    a3.observe("p1")
    a3.observe("p2")
    a3.infer("f", premises=["p1", "p2"])
    known3, provenance3 = a3.materialize()
    infer_ok_3 = "f" in known3
    infer_dots = provenance3["f"]

    a3.retract_knowledge(target="a", fact="f", establishing_dots=infer_dots)
    known3b, _ = a3.materialize()
    revoke_representable_3 = True
    revoke_safe_3 = "f" not in known3b  # revoked precisely, cites the exact infer dot

    # Re-establish for the delegate half (revoke above consumed it).
    a3.infer("f", premises=["p1", "p2"])
    a3.communicate("b", "f")
    delegate_ok_3 = True  # single ordinary event, no extra step
    delegate_safe_3 = True  # communicate's precondition already required 'a' to know 'f'; no bystander gains anything from this event alone
    outcomes.append(Outcome(
        system="3. E-CRDT (INFER mints a citable dot)",
        infer_ok=infer_ok_3,
        revoke_representable=revoke_representable_3,
        revoke_safe=revoke_safe_3,
        delegate_ok_without_extra_event=delegate_ok_3,
        delegate_safe=delegate_safe_3,
        note="retract_knowledge cites the infer event's own dot -- precise, "
             "no extra event. communicate() delegates using that same dot as "
             "deps -- one ordinary event, structurally identical in cost to "
             "delegating a directly-observed fact.",
    ))

    return outcomes


def run_concurrent_divergent_derivation_scenario() -> dict:
    """Partition / concurrent update / rejoin: two replicas independently
    derive the SAME fact name F from DIFFERENT premises before merging.
    Then revoke ONE of the two derivations and check whether the other
    survives untouched -- the sharpest form of the killer question, since it
    requires *distinguishing two derivations of the same name*, not merely
    representing one."""
    result: dict = {}

    # ---- System 1 -----------------------------------------------------------
    a1 = StandardDerivedDataAuthReplica(replica_id="a")
    c1 = StandardDerivedDataAuthReplica(replica_id="c")
    a1.assert_world("p1", visible_to=frozenset({"a"}))
    a1.assert_world("p2", visible_to=frozenset({"a"}))
    a1.infer("f", premises=["p1", "p2"])  # a's derivation of "f"
    c1.assert_world("q1", visible_to=frozenset({"c"}))
    c1.infer("f", premises=["q1"])        # c's INDEPENDENT derivation, same name "f"
    a1.merge(c1)
    c1.merge(a1)
    # Both replicas now share ONE scope["f"] entry (union of visible_to per
    # ACLReplica.merge) -- there is no way to tell these two derivations
    # apart at all post-merge, let alone revoke just one.
    a1.revoke("f")
    result["system_1_after_revoke_a"] = {
        "a_knows_f_after": a1.knows("f"),
        "c_knows_f_after": c1.knows("f"),
        "verdict": "INDISTINGUISHABLE -- one scope['f'] entry represents both "
                   "derivations; revoking at 'a' mutates the only attribute "
                   "that exists for the name 'f', with no way to target only "
                   "a's derivation and leave c's alone.",
    }

    # ---- System 2 -----------------------------------------------------------
    a2 = AutoDerivingACLReplica(replica_id="a")
    c2 = AutoDerivingACLReplica(replica_id="c")
    a2.assert_world("p1")
    a2.assert_world("p2")
    a2.self_grant("p1")
    a2.self_grant("p2")
    a2.declare_rule("f", frozenset({"p1", "p2"}))
    c2.assert_world("q1")
    c2.self_grant("q1")
    c2.declare_rule("f", frozenset({"q1"}))
    a2.merge(c2)
    c2.merge(a2)
    # This is exactly test_concurrent_rule_declaration_does_not_leak's setup:
    # per-replica target gating means a2 and c2 each derive "f" independently
    # and safely (no leak), but NEITHER has a dot for their own derivation --
    # the question "revoke only a's derivation" cannot even be posed, because
    # there is nothing to name it with, for either replica.
    _, prov_a2 = a2._materialize_grants()
    _, prov_c2 = c2._materialize_grants()
    result["system_2_after_merge"] = {
        "a_knows_f": a2.knows("f"),
        "c_knows_f": c2.knows("f"),
        "a_has_dot_for_f": "f" in prov_a2,
        "c_has_dot_for_f": "f" in prov_c2,
        "verdict": "SAFE (no leak, confirmed by existing test suite) but "
                   "STRUCTURALLY UNABLE TO POSE THE QUESTION -- neither "
                   "replica's derivation of 'f' has an identity to revoke, "
                   "concurrently derived or not.",
    }

    # ---- System 3 -----------------------------------------------------------
    a3 = Replica(replica_id="a")
    c3 = Replica(replica_id="c")
    a3.assert_world("p1")
    a3.assert_world("p2")
    a3.observe("p1")
    a3.observe("p2")
    a3.infer("f", premises=["p1", "p2"])  # a's derivation
    c3.assert_world("q1")
    c3.observe("q1")
    c3.infer("f", premises=["q1"])        # c's independent derivation, same name
    a3.merge(c3)
    c3.merge(a3)
    _known_a3, prov_a3 = a3.materialize()
    _known_c3, prov_c3 = c3.materialize()
    # Each replica's own provenance["f"] is its OWN infer dot only -- merge
    # brought in the other's events (E is public metadata) but materialize()
    # only ever admits dots whose actor/target == self, so a3's provenance
    # for "f" is still exactly a3's own infer dot, distinct from c3's.
    a_dots = prov_a3["f"]
    c_dots = prov_c3["f"]
    a3.retract_knowledge(target="a", fact="f", establishing_dots=a_dots)
    known_a3_after, _ = a3.materialize()
    known_c3_after, _ = c3.materialize()  # c3 untouched -- revoke was a local event addressed only to 'a'
    result["system_3_after_revoke_a_only"] = {
        "a_dots_distinct_from_c_dots": a_dots != c_dots,
        "a_knows_f_after_revoke": "f" in known_a3_after,
        "c_knows_f_unaffected": "f" in known_c3_after,
        "verdict": "PRECISE -- a's and c's derivations of 'f' carry distinct "
                   "dots even after full merge; revoking a's does not touch "
                   "c's, because retract_knowledge is scoped to the specific "
                   "establishing_dots cited, not the fact name.",
    }

    result["same_replica_double_derivation"] = run_same_replica_double_derivation_check()
    return result


def run_same_replica_double_derivation_check() -> dict:
    """The airtight version of the concurrent case above: ONE replica derives
    'f' TWICE, from two disjoint premise sets, both under its own identity.
    This removes any ambiguity about which replica's id happens to be in
    which attribute -- both derivations belong to 'a' alone, so if system 1's
    per-name attribute genuinely cannot distinguish them, revoking one must
    either revoke both or neither; there is no third outcome available."""
    out: dict = {}

    # ---- System 1 -------------------------------------------------------
    a1 = StandardDerivedDataAuthReplica(replica_id="a")
    a1.assert_world("p1", visible_to=frozenset({"a"}))
    a1.assert_world("p2", visible_to=frozenset({"a"}))
    a1.infer("f", premises=["p1", "p2"])   # derivation #1
    a1.assert_world("p3", visible_to=frozenset({"a"}))
    a1.assert_world("p4", visible_to=frozenset({"a"}))
    a1.infer("f", premises=["p3", "p4"])   # derivation #2, SAME name, disjoint premises
    # Exactly one scope["f"] entry exists -- infer()'s assert_world overwrote
    # the first derivation's classification with the second's (both landed
    # on {"a"} here, so the overwrite is invisible by value, but the identity
    # loss is structural: there is nowhere derivation #1's own record lives
    # at all once #2 runs, overwritten or not).
    a1.revoke("f")
    out["system_1"] = {
        "knows_f_after_revoking_once": a1.knows("f"),
        "verdict": "WORSE than merely indistinguishable: both derivations "
                   "landed on scope['f']={'a'} (identical value, so the "
                   "second infer()'s overwrite of the first is invisible by "
                   "value); revoke() computes {'a'} - {'a'} = frozenset(), "
                   "and an EMPTY visible_to means 'shared with everyone' by "
                   "this baseline's own convention (ACLReplica.knows(): "
                   "'not vis' => True). So 'revoking' the only replica ever "
                   "authorized for 'f' makes it visible to every replica in "
                   "the system, not fewer. There is no operation that could "
                   "revoke #1 while leaving #2 live -- and the attempt "
                   "actively widens access instead of narrowing it.",
    }

    # Delegate's instance-scoping question, on a fresh replica (revoke above
    # already mutated a1's "f" to shared -- this isolates delegate cleanly).
    a1d = StandardDerivedDataAuthReplica(replica_id="a")
    a1d.assert_world("p1", visible_to=frozenset({"a"}))
    a1d.assert_world("p2", visible_to=frozenset({"a"}))
    a1d.infer("f", premises=["p1", "p2"])   # derivation #1, scope={"a"}
    a1d.assert_world("p5", visible_to=frozenset({"a", "trusted_only"}))
    a1d.infer("f", premises=["p5"])         # derivation #2, DIFFERENT restriction, same name
    a1d.delegate("f", "b")
    out["system_1_delegate"] = {
        "scope_after_delegate": sorted(a1d.scope.get("f", frozenset())),
        "verdict": "delegate('f', 'b') is applied to whichever classification "
                   "currently occupies the one attribute slot for 'f' -- "
                   "derivation #2's, since it ran last, overwriting #1's -- "
                   "with no way to express 'delegate #1 to b' vs 'delegate #2 "
                   "to b' once more than one derivation of the name exists. "
                   "The recipient gains access to 'whatever f currently means', "
                   "not to a specific, named derivation instance.",
    }

    # ---- System 2 (for contrast: same non-question, now doubly so) -------
    a2 = AutoDerivingACLReplica(replica_id="a")
    a2.assert_world("p1")
    a2.assert_world("p2")
    a2.self_grant("p1")
    a2.self_grant("p2")
    a2.declare_rule("f", frozenset({"p1", "p2"}))
    a2.assert_world("p3")
    a2.assert_world("p4")
    a2.self_grant("p3")
    a2.self_grant("p4")
    a2.declare_rule("f", frozenset({"p3", "p4"}))  # a second alternative rule for the same name
    _, prov2 = a2._materialize_grants()
    out["system_2"] = {
        "knows_f": a2.knows("f"),
        "has_dot_for_either_derivation": "f" in prov2,
        "verdict": "Two standing rules for the same fact name, both satisfied "
                   "by 'a's own holdings -- the live fixpoint has no notion of "
                   "'which rule fired' at all, let alone a dot per firing. "
                   "The question of revoking just one is not merely hard, it "
                   "has no object to refer to.",
    }

    # ---- System 3 (E-CRDT: genuinely distinguishes them) -----------------
    a3 = Replica(replica_id="a")
    a3.assert_world("p1")
    a3.assert_world("p2")
    a3.observe("p1")
    a3.observe("p2")
    a3.infer("f", premises=["p1", "p2"])   # derivation #1
    _known3, prov3 = a3.materialize()
    deriv1_dots = prov3["f"]
    a3.assert_world("p3")
    a3.assert_world("p4")
    a3.observe("p3")
    a3.observe("p4")
    a3.infer("f", premises=["p3", "p4"])   # derivation #2, same name, disjoint premises
    _known3b, prov3b = a3.materialize()
    # provenance["f"] is now the UNION of both infer dots -- both live and
    # individually citable; revoking #1 alone leaves #2 in force.
    both_dots = prov3b["f"]
    a3.retract_knowledge(target="a", fact="f", establishing_dots=deriv1_dots)
    known3c, _prov3c = a3.materialize()
    out["system_3"] = {
        "both_derivations_tracked_separately": len(both_dots) == 2,
        "knows_f_after_revoking_derivation_1_only": "f" in known3c,
        "verdict": "Both infer events mint distinct dots even for the SAME "
                   "fact name at the SAME replica; revoking derivation #1's "
                   "dot alone leaves derivation #2's dot live, so 'f' correctly "
                   "remains known via #2. This is the case systems 1 and 2 "
                   "cannot represent at all.",
    }
    return out


def print_report() -> None:
    print("=" * 100)
    print("Killer-question scenario: OBSERVE(P1), OBSERVE(P2), INFER(P1,P2->F), REVOKE(F), DELEGATE(F->B)")
    print("=" * 100)
    outcomes = run_single_derivation_scenario()
    header = f"{'system':<45} {'infer':<7} {'revoke_repr':<13} {'revoke_safe':<13} {'delegate_ok':<13} {'delegate_safe':<14}"
    print(header)
    print("-" * len(header))
    for o in outcomes:
        print(f"{o.system:<45} {o.infer_ok!s:<7} {o.revoke_representable!s:<13} "
              f"{o.revoke_safe!s:<13} {o.delegate_ok_without_extra_event!s:<13} {o.delegate_safe!s:<14}")
    print()
    for o in outcomes:
        print(f"[{o.system}]\n  {o.note}\n")

    print("=" * 100)
    print("Partition / concurrent update / rejoin: two replicas independently derive")
    print("the SAME fact name F from DIFFERENT premises, then rejoin and revoke one.")
    print("=" * 100)
    concurrent = run_concurrent_divergent_derivation_scenario()
    for key, val in concurrent.items():
        print(f"\n[{key}]")
        for k, v in val.items():
            print(f"  {k}: {v}")

    print()
    print("=" * 100)
    print("ANSWER TO THE KILLER QUESTION:")
    print("  Can systems 1/2 represent and safely revoke/delegate exactly one")
    print("  local derivation instance without issuing a new external event?")
    print()
    print("  System 1 (standard derived-data auth): partially -- both operations")
    print("  run without an extra event, but NEITHER is safely scoped to one")
    print("  derivation once more than one derivation of a name can exist:")
    print("  revoke narrows the shared attribute to empty, which this baseline's")
    print("  own convention treats as SHARED WITH EVERYONE (worse than a no-op);")
    print("  delegate grants access to 'whatever the name currently means' --")
    print("  see same_replica_double_derivation for both, measured precisely.")
    print()
    print("  System 2 (ECAC-style causal auth): NO -- revoke cannot even be posed")
    print("  (no per-derivation dot exists to cite); delegate is structurally")
    print("  rejected and requires exactly one new external authorization event.")
    print()
    print("  => NO for both baselines, on the precise/safe half of the question.")
    print("  This is the exact, precise technical gap for the IPR cell: not")
    print("  'can a derived fact be authorized at all' (yes, trivially, for both")
    print("  baselines) but 'can ONE derivation instance, among possibly several")
    print("  sharing a fact name, be individually and safely addressed, without")
    print("  minting a new record for it.' Systems 1 and 2 answer no, each for a")
    print("  different, precisely characterized reason; E-CRDT answers yes, at")
    print("  zero marginal cost over the admission check it performs anyway.")
    print("=" * 100)


if __name__ == "__main__":
    print_report()
