"""Phase 3 (round 2): scaling with the incremental materializer, plus the
parameter sweeps (communication density, inference depth, retraction rate,
delayed delivery, partition/rejoin, compaction cost, memory) the brief asks
for. Uses IncrementalReplica (ecrdt.incremental) as "C" throughout, since
that's now the technically-serious candidate -- the non-incremental
reference (replica.Replica) is kept only for the direct speedup comparison
table, at small N (it cannot reach 1M -- see IPR_REVIEW.md).

Run: PYTHONPATH=src python3 bench_scaling_v2.py
"""
from __future__ import annotations

import csv
import os
import random
import resource
import time
from typing import List, Tuple

from ecrdt.baselines import ACLReplica, NaiveUnionReplica
from ecrdt.incremental import IncrementalReplica
from ecrdt.replica import Replica
from ecrdt.compaction import causally_stable, compact_for_target

OUT_DIR = os.path.join(os.path.dirname(__file__), "scaling_results")
os.makedirs(OUT_DIR, exist_ok=True)


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # KB->MB on Linux


def _write_csv(name, header, rows):
    with open(os.path.join(OUT_DIR, name), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


# ---------------------------------------------------------------------------
# 1. Direct reference-vs-incremental speedup, matched N (small, so the
#    non-incremental reference actually finishes)
# ---------------------------------------------------------------------------

def direct_speedup_comparison(sizes=(200, 500, 1000, 2000)):
    rows = []
    for n in sizes:
        ref = Replica("a")
        t0 = time.perf_counter()
        for i in range(n):
            f = f"f{i}"
            ref.assert_world(f)
            ref.observe(f)
            if i % 3 == 0:
                ref.communicate("b", f)
        ref_time = time.perf_counter() - t0

        inc = IncrementalReplica("a")
        t0 = time.perf_counter()
        for i in range(n):
            f = f"f{i}"
            inc.assert_world(f)
            inc.observe(f)
            if i % 3 == 0:
                inc.communicate("b", f)
        inc_time = time.perf_counter() - t0

        speedup = ref_time / inc_time if inc_time > 0 else float("inf")
        rows.append((n, ref_time, inc_time, speedup))
        print(f"[speedup] n={n:>6d}  reference={ref_time:9.4f}s  incremental={inc_time:9.5f}s  speedup={speedup:8.1f}x")
    _write_csv("v2_direct_speedup.csv", ["n", "reference_s", "incremental_s", "speedup_x"], rows)
    return rows


# ---------------------------------------------------------------------------
# 2. Incremental-replica scaling to large N (already 1M measured
#    separately in shell for the headline number; here at moderate sizes
#    with full metric capture including memory)
# ---------------------------------------------------------------------------

def incremental_scaling(sizes=(1_000, 10_000, 100_000, 1_000_000)):
    rows = []
    for n in sizes:
        rep = IncrementalReplica("a")
        rss0 = _rss_mb()
        t0 = time.perf_counter()
        for i in range(n):
            f = f"f{i}"
            rep.assert_world(f)
            rep.observe(f)
            if i % 3 == 0:
                rep.communicate("b", f)
        total = time.perf_counter() - t0
        rss1 = _rss_mb()

        t0 = time.perf_counter()
        rep.materialize()  # O(1) query cost -- state already maintained
        query_s = time.perf_counter() - t0

        other = IncrementalReplica("c")
        t0 = time.perf_counter()
        other.merge(rep)
        merge_s = time.perf_counter() - t0

        rows.append((n, total, total / (3 * n) * 1e6, query_s, merge_s, rep.event_log_size_bytes(), rss1 - rss0))
        print(
            f"[inc-scale] n={n:>8d}  total={total:9.4f}s  avg_op_us={total/(3*n)*1e6:7.2f}  "
            f"query={query_s*1e6:8.1f}us  first_merge={merge_s:8.4f}s  E_bytes={rep.event_log_size_bytes()}  "
            f"rss_delta_mb={rss1-rss0:8.1f}"
        )
    _write_csv("v2_incremental_scaling.csv",
               ["n", "total_s", "avg_op_us", "query_s", "merge_s", "E_bytes", "rss_delta_mb"], rows)
    return rows


# ---------------------------------------------------------------------------
# 3. Agent-count scaling, large N, incremental
# ---------------------------------------------------------------------------

def agent_scaling(agent_counts=(2, 10, 50, 100, 200), ops_per_agent=2000):
    rows = []
    for n_agents in agent_counts:
        rng = random.Random(11)
        ids = [f"a{i}" for i in range(n_agents)]
        reps = {r: IncrementalReplica(r) for r in ids}
        t0 = time.perf_counter()
        for r in ids:
            for k in range(ops_per_agent):
                reps[r].assert_world(f"{r}_f{k}")
                reps[r].observe(f"{r}_f{k}")
        update_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        merges = 0
        for _ in range(5):
            shuffled = ids[:]
            rng.shuffle(shuffled)
            for i in range(0, len(shuffled) - 1, 2):
                a, b = shuffled[i], shuffled[i + 1]
                reps[a].merge(reps[b])
                reps[b].merge(reps[a])
                merges += 2
        gossip_time = time.perf_counter() - t0

        total_events = sum(len(reps[r].E) for r in ids)
        rows.append((n_agents, update_time, gossip_time, merges, total_events / n_agents))
        print(
            f"[agents] n={n_agents:>4d}  update={update_time:8.4f}s  gossip5={gossip_time:8.4f}s "
            f"({merges} merges)  avg_E={total_events/n_agents:9.1f}"
        )
    _write_csv("v2_agent_scaling.csv", ["n_agents", "update_s", "gossip5_s", "merges", "avg_E_per_replica"], rows)
    return rows


# ---------------------------------------------------------------------------
# 4. Parameter sweeps: communication density, inference depth, retraction rate
# ---------------------------------------------------------------------------

def density_sweep(n=20_000, densities=(0.0, 0.1, 0.3, 0.5, 0.8)):
    rows = []
    for density in densities:
        rng = random.Random(5)
        a, b = IncrementalReplica("a"), IncrementalReplica("b")
        b.merge(a)
        t0 = time.perf_counter()
        for i in range(n):
            f = f"f{i}"
            a.assert_world(f)
            a.observe(f)
            if rng.random() < density:
                a.communicate("b", f)
        total = time.perf_counter() - t0
        t0 = time.perf_counter()
        b.merge(a)
        merge_s = time.perf_counter() - t0
        known_b, _ = b.materialize()
        rows.append((density, total, merge_s, len(known_b), a.event_log_size_bytes()))
        print(f"[density] p={density:.1f}  update={total:8.4f}s  final_merge={merge_s:8.4f}s  b_knows={len(known_b)}")
    _write_csv("v2_density_sweep.csv", ["density", "update_s", "merge_s", "b_knows_count", "E_bytes"], rows)
    return rows


def inference_depth_sweep(depths=(1, 5, 10, 20, 50, 100)):
    rows = []
    for depth in depths:
        rep = IncrementalReplica("a")
        rep.assert_world("base")
        rep.observe("base")
        t0 = time.perf_counter()
        prev = "base"
        for i in range(depth):
            d = f"d{i}"
            rep.infer(d, [prev])
            prev = d
        total = time.perf_counter() - t0
        known, _ = rep.materialize()
        rows.append((depth, total, total / depth * 1e6 if depth else 0, prev in known))
        print(f"[infer-depth] depth={depth:>4d}  total={total*1e6:9.1f}us  per_hop={total/max(depth,1)*1e6:7.2f}us  final_admitted={prev in known}")
    _write_csv("v2_inference_depth.csv", ["depth", "total_s", "per_hop_us", "final_admitted"], rows)
    return rows


def retraction_rate_sweep(n=20_000, rates=(0.0, 0.05, 0.2, 0.5)):
    rows = []
    for rate in rates:
        rng = random.Random(13)
        rep = IncrementalReplica("a")
        t0 = time.perf_counter()
        for i in range(n):
            f = f"f{i}"
            rep.assert_world(f)
            if rng.random() < rate and i > 0:
                prior = f"f{i-1}"
                if rep.W.contains(prior):
                    try:
                        rep.retract_world(prior)
                    except ValueError:
                        pass
        total = time.perf_counter() - t0
        rows.append((rate, total, len(rep.W.facts()), rep.event_log_size_bytes()))
        print(f"[retract] rate={rate:.2f}  total={total:8.4f}s  live_facts={len(rep.W.facts())}  E_bytes={rep.event_log_size_bytes()}")
    _write_csv("v2_retraction_sweep.csv", ["rate", "total_s", "live_facts", "E_bytes"], rows)
    return rows


# ---------------------------------------------------------------------------
# 5. Compaction cost at scale
# ---------------------------------------------------------------------------

def compaction_cost_at_scale(n=20_000):
    rng = random.Random(21)
    ids = ["a", "b", "c"]
    reps = {r: IncrementalReplica(r) for r in ids}
    for i in range(n):
        r = rng.choice(ids)
        f = f"f{i}"
        reps[r].assert_world(f)
        reps[r].observe(f)
        other = rng.choice([x for x in ids if x != r])
        reps[r].communicate(other, f)
    for x in ids:
        for y in ids:
            if x != y:
                reps[x].merge(reps[y])

    target = "c"
    merged_E = reps[target].E
    seen = {r: {origin: max((c for (o, c) in reps[r].E if o == origin), default=0) for origin in ids} for r in ids}
    t0 = time.perf_counter()
    stable = causally_stable(merged_E, ids, seen)
    result = compact_for_target(merged_E, target, stable)
    compaction_time = time.perf_counter() - t0
    print(
        f"[compaction] n={n}  events_before={result.events_before}  events_after={result.events_after}  "
        f"bytes_before={result.bytes_before}  bytes_after={result.bytes_after}  time={compaction_time:.4f}s"
    )
    return result, compaction_time


if __name__ == "__main__":
    print("=== 1. Direct reference-vs-incremental speedup ===")
    direct_speedup_comparison()

    print("\n=== 2. Incremental scaling (up to 1M) ===")
    incremental_scaling()

    print("\n=== 3. Agent-count scaling (incremental) ===")
    agent_scaling()

    print("\n=== 4a. Communication-density sweep ===")
    density_sweep()

    print("\n=== 4b. Inference-depth sweep ===")
    inference_depth_sweep()

    print("\n=== 4c. Retraction-rate sweep ===")
    retraction_rate_sweep()

    print("\n=== 5. Compaction cost at scale ===")
    compaction_cost_at_scale()
