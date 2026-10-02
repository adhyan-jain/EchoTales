"""Analyse listening-study responses, and simulate power before running one.

The decisive quantity is an *interaction*: does committing to character
voices (full cast vs narrator) help less -- or hurt -- as attribution
accuracy falls, and more so with a distinctive cast? It is estimated as a
difference-in-differences on probe accuracy (objective) and on enjoyment
(subjective), with a **cluster bootstrap over listeners**: each listener
contributes many correlated trials, and resampling trials as if independent
would overstate certainty (the same choice `pipeline/eval/stats.py` makes
explicit for mentions within chapters).
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np


def load_responses(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        rows.extend(json.loads(Path(p).read_text()))
    return rows


def _probe_acc(r: dict) -> float:
    ps = r.get("probes", [])
    return float(np.mean([p["chosen"] == p["answer"] for p in ps])) if ps else float("nan")


def cell_means(rows: list[dict], outcome: str) -> dict[tuple, float]:
    acc: dict[tuple, list[float]] = defaultdict(list)
    for r in rows:
        y = _probe_acc(r) if outcome == "probe" else float(r["enjoyment"])
        if y == y:
            acc[(r["policy"], float(r["rate"]) > 0)].append(y)
    return {k: float(np.mean(v)) for k, v in acc.items()}


def did(rows: list[dict], outcome: str) -> float:
    """[full - narrator | errors] - [full - narrator | no errors].
    Negative = errors erode the full-cast advantage (the hypothesis)."""
    m = cell_means(rows, outcome)
    try:
        return (m[("full_cast", True)] - m[("narrator_only", True)]) - (
            m[("full_cast", False)] - m[("narrator_only", False)])
    except KeyError:
        return float("nan")


def cluster_bootstrap(rows: list[dict], fn, *, resamples: int = 2000, seed: int = 20261002):
    by = defaultdict(list)
    for r in rows:
        by[r["participant"]].append(r)
    ids = sorted(by)
    rng = random.Random(seed)
    point = fn(rows)
    draws = []
    for _ in range(resamples):
        sample = [r for _ in ids for r in by[ids[rng.randrange(len(ids))]]]
        v = fn(sample)
        if v == v:
            draws.append(v)
    draws.sort()
    lo = draws[int(0.025 * len(draws))] if draws else float("nan")
    hi = draws[int(0.975 * len(draws)) - 1] if draws else float("nan")
    return point, lo, hi


def simulate_power(*, n_listeners: int, passages: int = 12, effect: float = -0.15,
                   base: float = 0.75, full_cast_gain: float = 0.08, listener_sd: float = 0.08,
                   probes_per_passage: int = 2, sims: int = 300, seed: int = 0) -> float:
    """Share of simulated studies whose cluster-bootstrap CI on the
    probe-accuracy DiD excludes 0, under an assumed true interaction `effect`.
    Assumptions are arguments, not constants: the pilot replaces them."""
    rng = np.random.default_rng(seed)
    hits = 0
    for s in range(sims):
        rows = []
        for li in range(n_listeners):
            u = rng.normal(0, listener_sd)
            for p in range(passages):
                policy = "full_cast" if (p + li) % 2 else "narrator_only"
                err = ((p + li) // 2) % 2 == 1
                pr = base + u + (full_cast_gain if policy == "full_cast" else 0) + (
                    effect if (policy == "full_cast" and err) else 0)
                pr = min(max(pr, 0.01), 0.99)
                k = rng.binomial(probes_per_passage, pr)
                rows.append({"participant": f"L{li}", "policy": policy, "rate": 0.35 if err else 0.0,
                             "probes": [{"chosen": "a" if i < k else "b", "answer": "a"}
                                        for i in range(probes_per_passage)], "enjoyment": 4})
        _, lo, hi = cluster_bootstrap(rows, lambda rs: did(rs, "probe"), resamples=200, seed=s)
        hits += (hi < 0) or (lo > 0)
    return hits / sims


def analyse(paths: list[Path]) -> dict:
    rows = load_responses(paths)
    out = {"responses": len(rows), "listeners": len({r["participant"] for r in rows})}
    for outcome in ("probe", "enjoyment"):
        pt, lo, hi = cluster_bootstrap(rows, lambda rs, o=outcome: did(rs, o))
        out[outcome] = {"cells": {f"{k[0]}|errors={k[1]}": round(v, 4)
                                  for k, v in cell_means(rows, outcome).items()},
                        "did": round(pt, 4), "ci": [round(lo, 4), round(hi, 4)]}
    for cast in ("homogeneous", "diverse"):
        sub = [r for r in rows if r["cast"] == cast]
        if sub:
            pt, lo, hi = cluster_bootstrap(sub, lambda rs: did(rs, "probe"))
            out[f"probe_did_{cast}"] = {"did": round(pt, 4), "ci": [round(lo, 4), round(hi, 4)]}
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(analyse([Path(p) for p in sys.argv[1:]]), indent=2))
