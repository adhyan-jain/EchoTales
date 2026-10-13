"""H-ACT policy layer (convergence pass C3, CPU): does a risk signal select a
safer rendering action, once each action's measured manifestation is known?

Joins two measured things and nothing assumed:
- the C2 rows (real ladder errors on PDNC, with each line's P1/P2a/P3 score
  and the gold/predicted genders), and
- the C3 table: mean manifestation Delta_a of an error under action a, by
  gender relation (cross vs same), and the identity price a masking action
  pays on a *correct* line (Q3).

For a budget k, the top-k lines by a signal are rendered with a masking
action (generic or narrator); the rest stay character-specific. Reported:
manifested error mass left in the output vs identity price paid -- a
frontier per signal. This is H-GATE's narrator_fallback with measured,
action-specific costs instead of a distance proxy, and a third action.
"""

from __future__ import annotations

import json
import random

import numpy as np

from echotales.research.config import ExperimentConfig
from echotales.research.experiments.gate_xdis import ROOT, inclusion
from echotales.research.schema import RunResult

HYPOTHESIS_ID = "H-ACT"
DEFAULT_PARAMS = {"c2_run": "", "c3_run": "", "rates": [0.05, 0.10, 0.20, 0.30],
                  "signals": ["P1_conf", "P2a_disagree", "P3_disagree_then_conf", "oracle"]}


def _load(p, stub, seed):
    if stub:
        rng = random.Random(seed)
        rows = []
        for _ in range(400):
            err = rng.random() < 0.12
            r = {"err": err, "cross": err and rng.random() < 0.3,
                 "P1_conf": rng.choice([0.05, 0.25]) + (0.1 if err and rng.random() < 0.3 else 0),
                 "P2a_disagree": float(rng.random() < (0.7 if err else 0.15)), "oracle": float(err)}
            r["P3_disagree_then_conf"] = 10 * r["P2a_disagree"] + r["P1_conf"]
            rows.append(r)
        table = {"cross": {"spec": 0.6, "gen": 0.2, "narr": 0.0}, "same": {"spec": 0.5, "gen": 0.05, "narr": 0.0},
                 "price": {"gen": 0.45, "narr": 0.5}}
        return rows, table
    c2 = [json.loads(x) for x in (ROOT / p["c2_run"] / "trials.jsonl").read_text().splitlines() if x.strip()]
    rows = []
    for t in c2:
        o, m = t["outputs"], t["metrics"]
        gg, gp = o.get("gender_gold"), o.get("gender_pred")
        rows.append({"err": bool(m["err"]),
                     "cross": gg in ("M", "F") and gp in ("M", "F") and gg != gp,
                     **{s: m[s] for s in p["signals"]}})
    s3 = json.loads((ROOT / p["c3_run"] / "results.json").read_text())["summary"]["by_error_type"]

    def mean(et, k):
        return s3[et][k]["mean"]

    # Gender relation -> C3 cell. Real addressee errors are scored by their
    # actual gender relation, so only the cross/same cells are needed.
    table = {"cross": {"spec": mean("cross_gender", "D_spec"), "gen": mean("cross_gender", "D_gen"), "narr": 0.0},
             "same": {"spec": mean("same_gender", "D_spec"), "gen": mean("same_gender", "D_gen"), "narr": 0.0},
             "price": {a: float(np.mean([s3[et][f"price_{a}"]["mean"] for et in s3])) for a in ("gen", "narr")}}
    return rows, table


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    rows, table = _load(p, stub, cfg.base_seed)
    n = len(rows)
    err = np.array([r["err"] for r in rows])
    rel = ["cross" if r["cross"] else "same" for r in rows]
    d_spec = np.array([table[c]["spec"] if e else 0.0 for c, e in zip(rel, err)])
    base_mass = float(d_spec.sum())
    out = {}
    for action in ("gen", "narr"):
        d_act = np.array([table[c][action] if e else 0.0 for c, e in zip(rel, err)])
        price = np.where(err, 0.0, table["price"][action])
        res = {}
        for sig in [*p["signals"], "random"]:
            # gate_xdis trial metrics are already "higher = intervene first"
            score = np.zeros(n) if sig == "random" else np.array([r[sig] for r in rows], dtype=float)
            cells = {}
            for rate in p["rates"]:
                k = int(round(rate * n))
                inc = np.full(n, k / n) if sig == "random" else inclusion(score, k)
                mass = float(((1 - inc) * d_spec + inc * d_act).sum())
                cells[f"{rate:.2f}"] = {"manifested_mass_left": round(mass / base_mass, 4) if base_mass else None,
                                        "identity_price_per_line": round(float((inc * price).sum()) / n, 5)}
            res[sig] = cells
        out[action] = res
    hint = "; ".join(f"{a}@20%: P1 {out[a]['P1_conf']['0.20']['manifested_mass_left']} vs "
                     f"P3 {out[a]['P3_disagree_then_conf']['0.20']['manifested_mass_left']}" for a in out)
    summary = {"n_lines": n, "n_errors": int(err.sum()), "cost_table": table, "frontiers": out}
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="action_policy", mode="stub" if stub else "real",
                      config_hash=cfg.hash, n_units=n, n_trials=0, summary=summary,
                      verdict_hint="manifested error mass left (fraction of all-specific): " + hint,
                      notes=["costs are C3 machine manifestation means, not perceptual cost",
                             "identity price = C3 Q3 margin loss on correct lines"]),
            [], {})
