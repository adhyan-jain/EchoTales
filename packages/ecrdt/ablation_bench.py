"""Phase 4 ablation harness. Run: PYTHONPATH=src python3 ablation_bench.py

Runs the same synthetic workload through all six variants (A-F) and reports
unauthorized-knowledge-propagation counts under two conditions:
  (1) a clean, honest workload (only well-formed ops via each class's own API)
  (2) the same workload PLUS one injected forged/invalid event, to isolate
      which mechanism (causal gating vs. provenance-closure checking)
      is actually responsible for catching it.
"""
from __future__ import annotations

import random
from typing import Dict, Set

from ecrdt.replica import Replica
from ecrdt.baselines import NaiveUnionReplica, ACLReplica
from ecrdt.ablations import NoProvenanceReplica, FlatPerAgentCRDTReplica, ClosureOnlyReplica
from ecrdt.model import Event
from ecrdt.audit import audit_non_interference, total_violation_count


def run_clean_workload(n_replicas=6, n_facts=40, rounds=10, seed=17):
    rng = random.Random(seed)
    ids = [f"r{i}" for i in range(n_replicas)]
    results = {}

    # ---- A / F share the Replica-family shape (ecrdt, no_provenance) ----
    for label, cls in (("F_full_ecrdt", Replica), ("C_no_provenance", NoProvenanceReplica)):
        rng2 = random.Random(seed)
        reps = {r: cls(replica_id=r) for r in ids}
        ground_truth = {r: set() for r in ids}
        for rnd in range(rounds):
            for r in ids:
                if rng2.random() < 0.4:
                    f = f"f{rng2.randrange(n_facts)}"
                    if f not in reps[r].W.facts():
                        reps[r].assert_world(f)
                if rng2.random() < 0.5:
                    live = list(reps[r].W.facts())
                    if live:
                        f = rng2.choice(live)
                        try:
                            reps[r].observe(f)
                            ground_truth[r].add(f)
                        except ValueError:
                            pass
                known, _ = reps[r].materialize()
                if len(known) >= 2 and rng2.random() < 0.15:
                    premises = rng2.sample(sorted(known), 2)
                    derived = f"d_{'_'.join(premises)}"
                    try:
                        reps[r].infer(derived, premises)
                        ground_truth[r].add(derived)
                    except ValueError:
                        pass
                if known and rng2.random() < 0.15:
                    target = rng2.choice([x for x in ids if x != r])
                    f = rng2.choice(sorted(known))
                    reps[r].communicate(target, f)
                    ground_truth[target].add(f)
            for a in ids:
                for b in ids:
                    if a != b:
                        reps[a].merge(reps[b])
        apparent = {r: reps[r].materialize()[0] for r in ids}
        violations = audit_non_interference(apparent, ground_truth)
        results[label] = total_violation_count(violations)

    # ---- A: naive union ----
    rng2 = random.Random(seed)
    reps = {r: NaiveUnionReplica(replica_id=r) for r in ids}
    ground_truth = {r: set() for r in ids}
    for rnd in range(rounds):
        for r in ids:
            if rng2.random() < 0.4:
                f = f"f{rng2.randrange(n_facts)}"
                if f not in reps[r].W.facts():
                    reps[r].assert_world(f)
                    ground_truth[r].add(f)
        for a in ids:
            for b in ids:
                if a != b:
                    reps[a].merge(reps[b])
    apparent = {r: reps[r].materialized_facts() for r in ids}
    results["A_naive_union"] = total_violation_count(audit_non_interference(apparent, ground_truth))

    # ---- B: static ACL ----
    rng2 = random.Random(seed)
    reps = {r: ACLReplica(replica_id=r) for r in ids}
    ground_truth = {r: set() for r in ids}
    for rnd in range(rounds):
        for r in ids:
            if rng2.random() < 0.4:
                f = f"f{rng2.randrange(n_facts)}"
                if f not in reps[r].W.facts():
                    reps[r].assert_world(f, visible_to=frozenset({r}))
                    ground_truth[r].add(f)
        for a in ids:
            for b in ids:
                if a != b:
                    reps[a].merge(reps[b])
    apparent = {r: reps[r].materialized_facts() for r in ids}
    results["B_static_acl"] = total_violation_count(audit_non_interference(apparent, ground_truth))

    # ---- D: provenance closure only (no identity gating) ----
    rng2 = random.Random(seed)
    reps = {r: ClosureOnlyReplica(replica_id=r) for r in ids}
    ground_truth = {r: set() for r in ids}
    for rnd in range(rounds):
        for r in ids:
            if rng2.random() < 0.4:
                f = f"f{rng2.randrange(n_facts)}"
                if f not in reps[r].W.facts():
                    reps[r].assert_world(f)
            if rng2.random() < 0.5:
                live = list(reps[r].W.facts())
                if live:
                    f = rng2.choice(live)
                    try:
                        reps[r].observe(f)
                        ground_truth[r].add(f)
                    except ValueError:
                        pass
        for a in ids:
            for b in ids:
                if a != b:
                    reps[a].merge(reps[b])
    apparent = {r: reps[r].materialized_facts() for r in ids}
    results["D_closure_only_no_identity"] = total_violation_count(audit_non_interference(apparent, ground_truth))

    # ---- E: flat per-agent CRDT knowledge ----
    rng2 = random.Random(seed)
    reps = {r: FlatPerAgentCRDTReplica(replica_id=r) for r in ids}
    ground_truth = {r: set() for r in ids}
    for rnd in range(rounds):
        for r in ids:
            if rng2.random() < 0.4:
                f = f"f{rng2.randrange(n_facts)}"
                if f not in reps[r].W.facts():
                    reps[r].assert_world(f)
            if rng2.random() < 0.5:
                live = list(reps[r].W.facts())
                if live:
                    f = rng2.choice(live)
                    reps[r].learn_locally(f)
                    ground_truth[r].add(f)
        for a in ids:
            for b in ids:
                if a != b:
                    reps[a].merge(reps[b])
    apparent = {r: reps[r].materialized_facts() for r in ids}
    results["E_flat_per_agent_crdt"] = total_violation_count(audit_non_interference(apparent, ground_truth))

    return results


def run_with_forged_event_injection():
    """Isolate whether provenance-closure checking (present in F, absent
    in C) is what actually stops a forged/invalid INFER event."""
    out = {}
    for label, cls in (("F_full_ecrdt", Replica), ("C_no_provenance", NoProvenanceReplica)):
        mallory = cls(replica_id="mallory")
        fake_dot = mallory._new_dot()
        forged = Event(dot=fake_dot, kind="infer", fact="fabricated_claim", actor="mallory",
                        deps=frozenset({("nobody", 999)}))
        mallory.E[fake_dot] = forged
        if hasattr(mallory, "_dirty"):
            mallory._dirty = True
        out[label] = mallory.knows("fabricated_claim")
    return out


if __name__ == "__main__":
    print("=== Ablation results: unauthorized-knowledge-propagation count, clean workload ===")
    clean = run_clean_workload()
    for label in ("F_full_ecrdt", "C_no_provenance", "D_closure_only_no_identity", "A_naive_union", "B_static_acl", "E_flat_per_agent_crdt"):
        print(f"{label:24s} leaks={clean[label]}")

    print("\n=== Isolating the provenance-closure mechanism: forged INFER event with fabricated deps ===")
    forged = run_with_forged_event_injection()
    for label, admitted in forged.items():
        print(f"{label:24s} forged fact admitted into K? {admitted}")
