"""Phase 3: technical-effect / scalability benchmark.

Run from packages/ecrdt/ with:  PYTHONPATH=src python3 bench_scaling.py

Three separate experiments, kept separate on purpose:

  A. world-only workload (ASSERT_WORLD/RETRACT_WORLD only) at large N --
     isolates the causal OR-Set (W) layer's cost, identical machinery in
     all three systems.
  B. epistemic workload (OBSERVE/COMMUNICATE/INFER heavy) at moderate N --
     isolates materialize() cost, where this prototype has a known,
     honestly-reported scaling weakness (see AUDIT.md): materialize()
     recomputes over the full local event log whenever it is dirty, and
     communicate()/infer() call materialize() internally to check their
     precondition, so a workload dominated by those ops pays a
     non-incremental, roughly-quadratic-in-N cumulative cost. This
     experiment exists to *measure*, not hide, that.
  C. agent-count scaling at fixed op count, random-pair gossip (not full
     mesh, to avoid conflating harness fan-out with algorithm cost).

Outputs CSV files plus dependency-free inline SVG line charts (no
matplotlib in this venv) under packages/ecrdt/scaling_results/.
"""
from __future__ import annotations

import csv
import os
import random
import time
from typing import List, Tuple

from ecrdt.replica import Replica
from ecrdt.baselines import NaiveUnionReplica, ACLReplica

OUT_DIR = os.path.join(os.path.dirname(__file__), "scaling_results")
os.makedirs(OUT_DIR, exist_ok=True)


def _write_csv(path: str, header: List[str], rows: List[Tuple]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _svg_line_chart(path: str, title: str, series: dict, xlabel: str, ylabel: str) -> None:
    """series: {label: [(x, y), ...]}. Pure-Python inline SVG, log-scaled y."""
    import math

    W, H, pad = 640, 380, 56
    colors = ["#2563eb", "#dc2626", "#16a34a", "#a855f7", "#ea580c"]
    all_x = [x for pts in series.values() for x, _ in pts]
    all_y = [y for pts in series.values() for _, y in pts if y > 0]
    if not all_x or not all_y:
        return
    xmin, xmax = min(all_x), max(all_x)
    ymin, ymax = min(all_y), max(all_y)
    logy = lambda v: math.log10(max(v, 1e-9))
    ylo, yhi = logy(ymin), logy(ymax if ymax > ymin else ymin + 1)

    def sx(x):
        return pad + (x - xmin) / max(1, (xmax - xmin)) * (W - 2 * pad)

    def sy(y):
        return H - pad - (logy(y) - ylo) / max(1e-9, (yhi - ylo)) * (H - 2 * pad)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="monospace" font-size="11">']
    parts.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    parts.append(f'<text x="{W/2}" y="20" text-anchor="middle" font-size="13">{title}</text>')
    parts.append(f'<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="black"/>')
    parts.append(f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H-pad}" stroke="black"/>')
    parts.append(f'<text x="{W/2}" y="{H-15}" text-anchor="middle">{xlabel}</text>')
    parts.append(f'<text x="14" y="{H/2}" text-anchor="middle" transform="rotate(-90 14 {H/2})">{ylabel} (log10)</text>')

    for i, (label, pts) in enumerate(series.items()):
        pts = sorted(pts)
        color = colors[i % len(colors)]
        path_d = " ".join(f"{'M' if j==0 else 'L'} {sx(x):.1f} {sy(y):.1f}" for j, (x, y) in enumerate(pts))
        parts.append(f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.5" fill="{color}"/>')
        lx, ly = pad + 10, pad + 14 * i + 10
        parts.append(f'<rect x="{lx}" y="{ly-8}" width="10" height="10" fill="{color}"/>')
        parts.append(f'<text x="{lx+14}" y="{ly+1}">{label}</text>')

    parts.append("</svg>")
    with open(path, "w") as fh:
        fh.write("\n".join(parts))


# ---------------------------------------------------------------------------
# Experiment A: world-only scaling
# ---------------------------------------------------------------------------

def experiment_a_world_only(sizes=(1_000, 10_000, 50_000, 100_000)) -> List[Tuple]:
    rows = []
    for n in sizes:
        for name, cls, kw in (("ecrdt", Replica, {}), ("naive", NaiveUnionReplica, {}), ("acl", ACLReplica, {})):
            rng = random.Random(1)
            rep = cls(replica_id="r0")
            t0 = time.perf_counter()
            for i in range(n):
                f = f"f{i}"
                if name == "acl":
                    rep.assert_world(f, visible_to=frozenset())
                else:
                    rep.assert_world(f)
                if rng.random() < 0.1 and i > 0:
                    rep.retract_world(f"f{rng.randrange(i)}") if False else None
            update_time = time.perf_counter() - t0

            other = cls(replica_id="r1")
            t0 = time.perf_counter()
            other.merge(rep)
            merge_time = time.perf_counter() - t0

            size_bytes = rep.W.size_bytes()
            rows.append((name, n, update_time, merge_time, size_bytes))
            print(f"[A] {name:6s} n={n:>7d}  update_total={update_time:8.4f}s  merge={merge_time:8.5f}s  W_bytes={size_bytes}")
    return rows


# ---------------------------------------------------------------------------
# Experiment B: epistemic (materialize-heavy) scaling
# ---------------------------------------------------------------------------

def experiment_b_epistemic(sizes=(200, 500, 1_000, 2_000)) -> List[Tuple]:
    rows = []
    for n in sizes:
        rep = Replica(replica_id="a")
        t0 = time.perf_counter()
        for i in range(n):
            f = f"f{i}"
            rep.assert_world(f)
            rep.observe(f)
            if i % 3 == 0:
                rep.communicate("b", f)
        total_time = time.perf_counter() - t0
        avg_op_us = total_time / (3 * n) * 1e6

        # single materialize call cost at this log size (cache cold)
        rep._dirty = True
        t0 = time.perf_counter()
        rep.materialize()
        single_materialize_s = time.perf_counter() - t0

        rows.append((n, total_time, avg_op_us, single_materialize_s, rep.event_log_size_bytes(), rep.materialize_full_recomputes))
        print(
            f"[B] n={n:>6d}  total={total_time:8.4f}s  avg_op={avg_op_us:9.2f}us  "
            f"single_materialize={single_materialize_s*1e6:9.1f}us  E_bytes={rep.event_log_size_bytes()}  "
            f"full_recomputes={rep.materialize_full_recomputes}"
        )
    return rows


# ---------------------------------------------------------------------------
# Experiment C: agent-count scaling, fixed op budget, random-pair gossip
# ---------------------------------------------------------------------------

def experiment_c_agents(agent_counts=(2, 10, 50, 100), ops_per_agent=200) -> List[Tuple]:
    rows = []
    for n_agents in agent_counts:
        rng = random.Random(3)
        ids = [f"a{i}" for i in range(n_agents)]
        reps = {r: Replica(r) for r in ids}
        t0 = time.perf_counter()
        for r in ids:
            for k in range(ops_per_agent):
                reps[r].assert_world(f"{r}_f{k}")
                reps[r].observe(f"{r}_f{k}")
        update_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        merges = 0
        for _ in range(5):  # 5 rounds of random-pair gossip
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
            f"[C] agents={n_agents:>4d}  update_total={update_time:8.4f}s  "
            f"gossip5rounds={gossip_time:8.4f}s ({merges} merges)  avg_E_per_replica={total_events/n_agents:8.1f}"
        )
    return rows


if __name__ == "__main__":
    print("=== Experiment A: world-only (W layer) scaling ===")
    a_rows = experiment_a_world_only()
    _write_csv(os.path.join(OUT_DIR, "experiment_a_world_only.csv"),
               ["system", "n", "update_total_s", "merge_s", "W_bytes"], a_rows)

    print("\n=== Experiment B: epistemic (materialize-heavy) scaling ===")
    b_rows = experiment_b_epistemic()
    _write_csv(os.path.join(OUT_DIR, "experiment_b_epistemic.csv"),
               ["n", "total_s", "avg_op_us", "single_materialize_s", "E_bytes", "full_recomputes"], b_rows)

    print("\n=== Experiment C: agent-count scaling ===")
    c_rows = experiment_c_agents()
    _write_csv(os.path.join(OUT_DIR, "experiment_c_agents.csv"),
               ["n_agents", "update_total_s", "gossip5rounds_s", "merges", "avg_E_per_replica"], c_rows)

    # charts
    by_system = {}
    for name, n, upd, mrg, sz in a_rows:
        by_system.setdefault(name, []).append((n, upd))
    _svg_line_chart(os.path.join(OUT_DIR, "a_update_time.svg"), "Experiment A: total update time vs N (world-only)",
                     by_system, "N ops", "seconds")

    b_series = {"materialize (single call, cold cache)": [(n, t) for n, _, _, t, _, _ in b_rows]}
    _svg_line_chart(os.path.join(OUT_DIR, "b_materialize_latency.svg"),
                     "Experiment B: single materialize() latency vs event-log size N",
                     b_series, "N events in log", "seconds")

    c_series = {"gossip (5 rounds)": [(n, t) for n, _, t, _, _ in c_rows]}
    _svg_line_chart(os.path.join(OUT_DIR, "c_gossip_time.svg"), "Experiment C: gossip time vs agent count",
                     c_series, "agents", "seconds")

    print(f"\nCSV + SVG charts written to {OUT_DIR}/")
