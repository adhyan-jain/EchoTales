"""Synthetic multi-agent benchmark harness.

Builds a world of N replicas exchanging M facts through observation,
communication, inference, concurrent updates, retraction, and network
partitions, then measures three systems side by side:

  - ecrdt      : this package's Replica (world convergence + epistemic
                 non-interference via causal-disclosure materialization)
  - naive      : plain CRDT union, K_i := W_i (no epistemic layer)
  - acl        : CRDT + static per-fact visible_to scope, checked at read
                 time (the "CRDT + ACL" combination the brief requires be
                 ruled out as non-novel)

Metrics: bandwidth, metadata growth, merge latency, update cost,
convergence rounds, stale-state fraction, and unauthorized knowledge
propagation (via audit.audit_non_interference against ground-truth
disclosure).
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from .audit import audit_non_interference, total_violation_count
from .baselines import ACLReplica, NaiveUnionReplica
from .compaction import causally_stable, compact_for_target
from .replica import Replica


@dataclass
class Metrics:
    bandwidth_bytes: int = 0
    metadata_bytes: int = 0
    merge_calls: int = 0
    merge_time_s: float = 0.0
    update_calls: int = 0
    update_time_s: float = 0.0
    convergence_rounds: int = -1
    unauthorized_knowledge: int = 0
    unauthorized_detail: Dict[str, Set[str]] = field(default_factory=dict)

    @property
    def avg_merge_latency_us(self) -> float:
        return (self.merge_time_s / self.merge_calls * 1e6) if self.merge_calls else 0.0

    @property
    def avg_update_cost_us(self) -> float:
        return (self.update_time_s / self.update_calls * 1e6) if self.update_calls else 0.0


def _gossip_pairs(replica_ids: List[str], rng: random.Random, groups: List[List[str]]) -> List[Tuple[str, str]]:
    pairs = []
    for group in groups:
        if len(group) < 2:
            continue
        shuffled = group[:]
        rng.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            pairs.append((shuffled[i], shuffled[i + 1]))
    return pairs


def run_scenario(
    n_replicas: int = 8,
    n_facts: int = 60,
    rounds: int = 12,
    partition_rounds: int = 4,
    seed: int = 7,
    retroactive_widen: bool = False,
) -> Dict[str, Metrics]:
    rng = random.Random(seed)
    ids = [f"agent_{i}" for i in range(n_replicas)]

    ecrdt = {r: Replica(replica_id=r) for r in ids}
    naive = {r: NaiveUnionReplica(replica_id=r) for r in ids}
    acl = {r: ACLReplica(replica_id=r) for r in ids}

    ground_truth: Dict[str, Set[str]] = {r: set() for r in ids}
    fact_pool = [f"fact_{i}" for i in range(n_facts)]
    metrics = {"ecrdt": Metrics(), "naive": Metrics(), "acl": Metrics()}
    world_history: List[Set[str]] = []

    # split into two partitions for the first `partition_rounds` rounds
    half = n_replicas // 2
    groups_partitioned = [ids[:half], ids[half:]]
    groups_full = [ids]

    for rnd in range(rounds):
        groups = groups_partitioned if rnd < partition_rounds else groups_full

        # --- local ops this round: originate facts, observe, communicate, infer, retract
        for origin_group in groups:
            for r in origin_group:
                if rng.random() < 0.35 and fact_pool:
                    f = rng.choice(fact_pool)
                    t0 = time.perf_counter()
                    if f not in ecrdt[r].W.facts():
                        ecrdt[r].assert_world(f)
                        naive[r].assert_world(f)
                        acl[r].assert_world(f, visible_to=frozenset({r}))
                    metrics["ecrdt"].update_time_s += time.perf_counter() - t0
                    metrics["ecrdt"].update_calls += 1

                if rng.random() < 0.5:
                    live_here = list(ecrdt[r].W.facts())
                    if live_here:
                        f = rng.choice(live_here)
                        try:
                            t0 = time.perf_counter()
                            ecrdt[r].observe(f)
                            metrics["ecrdt"].update_time_s += time.perf_counter() - t0
                            metrics["ecrdt"].update_calls += 1
                            ground_truth[r].add(f)
                            acl[r].widen_scope(f, frozenset({r}))
                        except ValueError:
                            pass

                known, _ = ecrdt[r].materialize()
                if len(known) >= 2 and rng.random() < 0.15:
                    premises = rng.sample(sorted(known), 2)
                    derived = f"derived_{'_'.join(premises)}"
                    try:
                        t0 = time.perf_counter()
                        ecrdt[r].infer(derived, premises)
                        metrics["ecrdt"].update_time_s += time.perf_counter() - t0
                        metrics["ecrdt"].update_calls += 1
                        ground_truth[r].add(derived)
                    except ValueError:
                        pass

                if known and rng.random() < 0.1:
                    peers = [p for p in origin_group if p != r]
                    if peers:
                        target = rng.choice(peers)
                        f = rng.choice(sorted(known))
                        t0 = time.perf_counter()
                        ecrdt[r].communicate(target, f)
                        metrics["ecrdt"].update_time_s += time.perf_counter() - t0
                        metrics["ecrdt"].update_calls += 1
                        ground_truth[target].add(f)
                        acl[r].widen_scope(f, frozenset({target}))

                if rng.random() < 0.05 and ecrdt[r].W.facts():
                    f = rng.choice(sorted(ecrdt[r].W.facts()))
                    try:
                        ecrdt[r].retract_world(f)
                        naive[r].retract_world(f)
                        acl[r].retract_world(f)
                    except ValueError:
                        pass

        # --- gossip merges within current topology
        for a, b in _gossip_pairs(ids, rng, groups):
            for system, table in (("ecrdt", ecrdt), ("naive", naive), ("acl", acl)):
                t0 = time.perf_counter()
                table[a].merge(table[b])
                table[b].merge(table[a])
                dt = time.perf_counter() - t0
                metrics[system].merge_time_s += dt
                metrics[system].merge_calls += 2

        world_history.append(set(ecrdt[ids[0]].W.facts()))
        if metrics["ecrdt"].convergence_rounds == -1 and rnd >= partition_rounds:
            if all(ecrdt[r].W.facts() == ecrdt[ids[0]].W.facts() for r in ids):
                metrics["ecrdt"].convergence_rounds = rnd

    # final all-to-all merge round to settle convergence for accounting
    for a in ids:
        for b in ids:
            if a == b:
                continue
            for system, table in (("ecrdt", ecrdt), ("naive", naive), ("acl", acl)):
                table[a].merge(table[b])

    if retroactive_widen:
        # the concrete gap: widen scope for a batch of facts system-wide
        # *without* any COMMUNICATE/OBSERVE event ever happening for the
        # newly-included replicas.
        widen_targets = fact_pool[: max(1, n_facts // 5)]
        for r in ids:
            for f in widen_targets:
                acl[r].widen_scope(f, frozenset(ids))

    # --- bandwidth / metadata accounting (post-hoc, sum of serialized sizes)
    for r in ids:
        metrics["ecrdt"].bandwidth_bytes += ecrdt[r].W.size_bytes() + ecrdt[r].event_log_size_bytes()
        metrics["ecrdt"].metadata_bytes += ecrdt[r].event_log_size_bytes()
        metrics["naive"].bandwidth_bytes += naive[r].W.size_bytes()
        metrics["acl"].bandwidth_bytes += acl[r].W.size_bytes() + len(acl[r].scope) * 20
        metrics["acl"].metadata_bytes += len(acl[r].scope) * 20

    # --- unauthorized knowledge propagation, measured against ground truth
    ecrdt_apparent = {r: ecrdt[r].materialize()[0] for r in ids}
    naive_apparent = {r: naive[r].materialized_facts() for r in ids}
    acl_apparent = {r: acl[r].materialized_facts() for r in ids}

    for system, apparent in (("ecrdt", ecrdt_apparent), ("naive", naive_apparent), ("acl", acl_apparent)):
        # derived facts (from INFER) are legitimately known only by their
        # inferring replica; ground_truth already includes them for that
        # replica via the infer branch above.
        violations = audit_non_interference(apparent, ground_truth)
        metrics[system].unauthorized_detail = violations
        metrics[system].unauthorized_knowledge = total_violation_count(violations)

    return metrics


def run_compaction_demo(n_replicas: int = 6, n_facts: int = 40, rounds: int = 10, seed: int = 3) -> Dict[str, int]:
    """Run a chain-heavy scenario, then compact stable events for one
    target replica, reporting event-log bytes before/after."""
    rng = random.Random(seed)
    ids = [f"agent_{i}" for i in range(n_replicas)]
    reps = {r: Replica(replica_id=r) for r in ids}

    for rnd in range(rounds):
        for r in ids:
            if rng.random() < 0.4:
                f = f"fact_{rng.randrange(n_facts)}"
                if f not in reps[r].W.facts():
                    reps[r].assert_world(f)
        # chain communication: 0 -> 1 -> 2 -> ... for facts each knows
        for i in range(len(ids) - 1):
            a, b = ids[i], ids[i + 1]
            reps[a].merge(reps[b])
            reps[b].merge(reps[a])
            for f in list(reps[a].W.facts())[:3]:
                known, _ = reps[a].materialize()
                if f not in known:
                    try:
                        reps[a].observe(f)
                    except ValueError:
                        pass
            known, _ = reps[a].materialize()
            for f in list(known)[:2]:
                try:
                    reps[a].communicate(b, f)
                except ValueError:
                    pass

    for a in ids:
        for b in ids:
            if a != b:
                reps[a].merge(reps[b])

    target = ids[-1]
    merged_E = reps[target].E
    seen = {r: reps[r].event_context() for r in ids}
    stable = causally_stable(merged_E, ids, seen)
    result = compact_for_target(merged_E, target, stable)
    return {
        "events_before": result.events_before,
        "events_after": result.events_after,
        "bytes_before": result.bytes_before,
        "bytes_after": result.bytes_after,
    }


def measure_convergence(n_replicas: int = 8, n_facts: int = 40, seed: int = 11, max_rounds: int = 50) -> int:
    """Full-mesh random-pair gossip (no partition) until all replicas' W
    agree. This isolates convergence behavior from the epistemic layer:
    W's CRDT join is identical across ecrdt/naive/acl, so this number is
    the same underlying causal OR-Set convergence rate for all three."""
    rng = random.Random(seed)
    ids = [f"agent_{i}" for i in range(n_replicas)]
    reps = {r: Replica(replica_id=r) for r in ids}
    fact_pool = [f"fact_{i}" for i in range(n_facts)]
    for r in ids:
        for _ in range(3):
            f = rng.choice(fact_pool)
            if f not in reps[r].W.facts():
                reps[r].assert_world(f)

    for rnd in range(1, max_rounds + 1):
        shuffled = ids[:]
        rng.shuffle(shuffled)
        for i in range(0, len(shuffled) - 1, 2):
            a, b = shuffled[i], shuffled[i + 1]
            reps[a].merge(reps[b])
            reps[b].merge(reps[a])
        ref = reps[ids[0]].W.facts()
        if all(reps[r].W.facts() == ref for r in ids):
            return rnd
    return -1


def print_report(metrics: Dict[str, Metrics], title: str) -> None:
    print(f"\n=== {title} ===")
    header = f"{'system':<8}{'bandwidth_B':>14}{'metadata_B':>12}{'merge_us':>12}{'update_us':>12}{'converge_rd':>13}{'unauth_leak':>13}"
    print(header)
    for name in ("ecrdt", "naive", "acl"):
        m = metrics[name]
        print(
            f"{name:<8}{m.bandwidth_bytes:>14}{m.metadata_bytes:>12}"
            f"{m.avg_merge_latency_us:>12.2f}{m.avg_update_cost_us:>12.2f}"
            f"{m.convergence_rounds:>13}{m.unauthorized_knowledge:>13}"
        )


if __name__ == "__main__":
    base = run_scenario(retroactive_widen=False)
    print_report(base, "baseline scenario (no scope widening)")

    widened = run_scenario(retroactive_widen=True)
    print_report(widened, "with retroactive ACL scope widening")

    comp = run_compaction_demo()
    print("\n=== compaction demo (single target replica, event log) ===")
    print(comp)

    rounds_needed = measure_convergence()
    print(f"\n=== convergence (full-mesh gossip, no partition) ===\nrounds to converge: {rounds_needed}")
