"""H-GATE-XDIS: does ladder-vs-LLM disagreement buy a better *selective
intervention* frontier than the ladder's own confidence?

H-XDIS established ranking quality (AUROC 0.889 vs 0.612). This asks the
operational question: with a review budget of k lines, how many ladder
errors does each signal catch? CPU only, from H-XDIS's saved trials -- no
new LLM calls.

Fields H-XDIS did not save (gold speaker, quote type, error flags,
candidate shortlist) are re-derived by re-running the same deterministic
ladder probe, behind a hard gate: every recomputed confidence, owner list
and correctness flag must equal the saved trial, or the run aborts.

Ties (confidence has 3 values, disagreement 2) are scored by the exact
expected value under random tie-breaking -- each line's inclusion
probability at budget k -- so a coarse signal is neither flattered nor
penalised by an arbitrary order.

Leakage control: H-XDIS gave the LLM a shortlist built from PDNC *gold*
(speakers/addressees within 20 quotes, always containing the true
speaker, plus the ladder's owners). `C_shortlist_random` is the
disagreement of an attributor that picks uniformly from that same
shortlist; if it reproduces most of the gain, the gain is the shortlist,
not the LLM.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import numpy as np

from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.schema import RunResult, Trial

HYPOTHESIS_ID = "H-GATE-XDIS"
DEFAULT_PARAMS = {
    "source_run": "data/eval/research/H-XDIS/real-6f97e4d14f536dfe",
    "candidates_window": 20,  # must equal the source run's parameter
    "rates": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
    "primary_rates": [0.10, 0.20],
    "resamples": 2000,
    # Empty = write no doc files. The canonical run's CONFIG/RESULTS/CURVES
    # stay in docs/research/experiments/H-GATE-XDIS/; its narrative moved to
    # DECISION_LOG.md, so a rerun no longer regenerates markdown there.
    "docs_dir": "",
    # Robustness (disclosed, added after the pre-registered run): 58/1000
    # gold labels are name variants absent from PDNC's character keys
    # ("Kemp", "Lucy"), so the ladder is scored wrong on all of them and the
    # LLM cannot pick the gold either (39 come back unparsed = "disagree").
    # True drops those rows to test whether the gain is that artifact.
    "exclude_unscorable_gold": False,
}
ROOT = Path(__file__).resolve().parents[6]  # experiments/ -> repo root
GATED = ("P1_conf", "P2a_disagree", "P3_disagree_then_conf", "C_shortlist_random")


# --------------------------------------------------------------------------
# data


def _load_saved(source: Path) -> list[dict]:
    rows = [json.loads(line) for line in (source / "trials.jsonl").read_text().splitlines() if line.strip()]
    return [{"unit": r["unit_id"], "novel": r["unit_id"].split(":")[0], "qid": r["unit_id"].split(":", 1)[1],
             "conf": float(r["metrics"]["conf"]), "disagree": bool(r["metrics"]["disagree"]),
             "err": bool(r["metrics"]["ladder_error"]), "owners": list(r["outputs"]["ladder_owners"]),
             "llm": r["outputs"]["llm"]} for r in rows]


def _rederive(rows: list[dict], window: int) -> dict:
    """Join every saved row with the deterministic ladder probe and PDNC gold;
    report any mismatch with what H-XDIS saved (the caller aborts)."""
    from echotales.research.datasets import pdnc
    from echotales.research.transforms.attribution_probe import probe

    by_novel: dict[str, list[dict]] = {}
    for r in rows:
        by_novel.setdefault(r["novel"], []).append(r)
    mismatches = []
    for name in sorted(by_novel):
        nv = pdnc.load_novel(name)
        res = {p.quote_id: p for p in probe(nv)}
        qidx = {q.id: q for q in nv.quotes}
        for r in by_novel[name]:
            p, q = res.get(r["qid"]), qidx.get(r["qid"])
            if p is None or q is None:
                mismatches.append((r["unit"], "missing"))
                continue
            if (round(p.confidence, 6) != round(r["conf"], 6) or list(p.owners) != r["owners"]
                    or (not p.correct_lenient) != r["err"]):
                mismatches.append((r["unit"], "fields"))
                continue
            # The shortlist exactly as disagreement_posterior.run built it.
            near = [x for x in nv.quotes if abs(x.index - q.index) <= window]
            cands = sorted({x.speaker for x in near} | {a for x in near for a in x.addressees} | set(p.owners))
            cands = [c for c in cands if c in nv.characters]
            if r["llm"] is not None and r["llm"] not in cands:
                mismatches.append((r["unit"], "llm_not_in_shortlist"))
                continue
            r.update({
                "gold": p.gold, "pred": p.predicted or p.owners[0], "method": p.method,
                "quote_type": p.quote_type.lower(), "addressee_capture": bool(p.addressee_capture),
                "vocative": bool(p.predicted_in_quote), "gender_gold": p.gender_gold,
                "gender_pred": p.gender_pred, "n_cands": len(cands),
                "owners_in_cands": len(set(p.owners) & set(cands)),
                "gold_in_shortlist": p.gold in cands, "llm_correct": r["llm"] == p.gold,
            })
    return {"checked": len(rows), "mismatches": mismatches}


def _synthetic(seed: int, n: int = 400) -> list[dict]:
    """Stub: rows shaped like the re-derived data; no corpus needed."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        err = rng.random() < 0.16
        conf = 0.75 if rng.random() < (0.3 if err else 0.1) else 0.95
        none = rng.random() < 0.15
        dis = none or (rng.random() < (0.7 if err else 0.12))
        rows.append({"unit": f"syn{i % 7}:Q{i}", "novel": f"syn{i % 7}", "qid": f"Q{i}", "conf": conf,
                     "disagree": dis, "err": err, "owners": ["A"], "llm": None if none else ("B" if dis else "A"),
                     "gold": "B" if err else "A", "pred": "A", "method": rng.choice(["explicit", "proximal"]),
                     "quote_type": rng.choice(["explicit", "anaphoric", "implicit"]),
                     "addressee_capture": err and rng.random() < 0.5, "vocative": err and rng.random() < 0.2,
                     "gender_gold": rng.choice("MF"), "gender_pred": rng.choice("MF"),
                     "n_cands": rng.randint(2, 8), "owners_in_cands": 1, "gold_in_shortlist": True,
                     "llm_correct": not dis})
    return rows


# --------------------------------------------------------------------------
# policies and expected-value curves


def scores(rows: list[dict]) -> dict[str, np.ndarray]:
    """Higher = review first. P0 is all zeros = never review."""
    conf = np.array([r["conf"] for r in rows])
    dis = np.array([r["disagree"] for r in rows], dtype=float)
    none = np.array([r["llm"] is None for r in rows], dtype=float)
    real_dis = dis * (1 - none)
    return {
        "P0_none": np.zeros(len(rows)),
        "P1_conf": 1 - conf,
        "P2a_disagree": dis,
        "P2b_disagree_none_as_agree": real_dis,
        "P2c_disagree_none_mid": 2 * real_dis + none,
        # lexicographic: disagreement first, then low confidence
        "P3_disagree_then_conf": 10 * dis + (1 - conf),
        "C_shortlist_random": np.array([1 - r["owners_in_cands"] / r["n_cands"] for r in rows]),
        "oracle": np.array([r["err"] for r in rows], dtype=float),
    }


def inclusion(score: np.ndarray, k: int) -> np.ndarray:
    """P(line is reviewed) when the top-k by score are reviewed and ties are
    broken uniformly at random."""
    p = np.zeros(len(score))
    if k <= 0 or not np.any(score):
        return p
    left = k
    for lv in np.unique(score)[::-1]:
        idx = np.nonzero(score == lv)[0]
        if left >= len(idx):
            p[idx] = 1.0
            left -= len(idx)
        else:
            p[idx] = left / len(idx)
            break
    return p


def caught_curve(score: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Expected weight (errors, or salient-error mass) in the reviewed set for
    every budget k = 0..n, exact under random tie-breaking."""
    n = len(score)
    out = np.zeros(n + 1)
    if not np.any(score):
        return out
    k0, c0 = 0, 0.0
    for lv in np.unique(score)[::-1]:
        m = score == lv
        size, e = int(m.sum()), float(weight[m].sum())
        out[k0 + 1:k0 + size + 1] = c0 + e * np.arange(1, size + 1) / size
        k0 += size
        c0 += e
    return out


def metrics_at(k: int, caught: float, n: int, e_total: float) -> dict:
    acc = n - k
    return {
        "k": k, "intervention_rate": k / n, "coverage": acc / n, "accepted": acc, "gated": k,
        "errors_caught": caught, "errors_remaining": e_total - caught,
        "frac_errors_caught": caught / e_total if e_total else 0.0,
        "intervention_precision": caught / k if k else 0.0,
        "unnecessary_interventions": k - caught,
        "selective_risk": (e_total - caught) / acc if acc else 0.0,
        "residual_error_rate": (e_total - caught) / n,
        "risk_reduction_vs_p0": caught / e_total if e_total else 0.0,
        "capture_efficiency": caught / min(k, e_total) if k and e_total else 0.0,
    }


def auroc(score: np.ndarray, err: np.ndarray) -> float | None:
    pos, neg = score[err.astype(bool)], score[~err.astype(bool)]
    if len(pos) == 0 or len(neg) == 0:
        return None
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


# --------------------------------------------------------------------------
# bootstrap


def _caught_frac(idx, score, err, rate):
    s, e = score[idx], err[idx]
    tot = e.sum()
    return float(caught_curve(s, e)[int(round(rate * len(idx)))] / tot) if tot else 0.0


def paired_bootstrap(rows, sc, err, pairs, rates, resamples, seed, cluster):
    """Paired bootstrap of errors-caught differences (A minus B) at each rate.
    `cluster` resamples whole novels (errors cluster by novel); otherwise
    quotes."""
    rng = random.Random(seed)
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r["novel"], []).append(i)
    keys = sorted(groups)
    draws: dict[tuple, list[float]] = {(a, b, rate): [] for a, b in pairs for rate in rates}
    for _ in range(resamples):
        if cluster:
            idx = np.array([i for g in (rng.choice(keys) for _ in keys) for i in groups[g]])
        else:
            idx = np.array([rng.randrange(len(rows)) for _ in rows])
        for a, b in pairs:
            for rate in rates:
                draws[(a, b, rate)].append(_caught_frac(idx, sc[a], err, rate)
                                           - _caught_frac(idx, sc[b], err, rate))
    return {f"{a}-{b}@{rate}": {"ci": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))],
                                "p_le_0": float(np.mean(np.array(v) <= 0))}
            for (a, b, rate), v in draws.items()}


# --------------------------------------------------------------------------
# stratification and narrator fallback


def strata(rows) -> dict:
    def gendered_flip(r):
        return r["gender_gold"] in ("M", "F") and r["gender_pred"] in ("M", "F") \
            and r["gender_gold"] != r["gender_pred"]
    defs = {
        "addressee_capture": lambda r: r["err"] and r["addressee_capture"],
        "not_addressee_capture": lambda r: r["err"] and not r["addressee_capture"],
        "vocative_in_quote": lambda r: r["err"] and r["vocative"],
        "cross_gender": lambda r: r["err"] and gendered_flip(r),
        "same_or_unknown_gender": lambda r: r["err"] and not gendered_flip(r),
    }
    for m in sorted({r["method"] for r in rows}):
        defs[f"method={m}"] = (lambda mm: lambda r: r["err"] and r["method"] == mm)(m)
    for t in sorted({r["quote_type"] for r in rows}):
        defs[f"quote_type={t}"] = (lambda tt: lambda r: r["err"] and r["quote_type"] == tt)(t)
    return defs


def narrator_fallback(rows, sc, seed, stub) -> dict:
    """H-GATE's measure: a line gated to the narrator carries no salient
    error; a committed wrong line carries the speaker-embedding distance
    between the gold and the rendered voice. AURC of committed salient mass
    over coverage, against random and oracle orderings."""
    from echotales.research.controllers.casting import cast
    from echotales.research.evaluators.voice_geometry import ears_geometry

    n = len(rows)
    out = {}
    if stub:
        modes, dists = ["diverse"], {"diverse": np.array([0.15 if r["err"] else 0.0 for r in rows])}
    else:
        from echotales.research.datasets import pdnc

        geom = ears_geometry()
        modes, dists = ["diverse", "homogeneous"], {}
        novels = {name: pdnc.load_novel(name) for name in sorted({r["novel"] for r in rows})}
        for mode in modes:
            assign = {}
            for name, nv in novels.items():
                counts: dict[str, int] = {}
                for q in nv.quotes:
                    counts[q.speaker] = counts.get(q.speaker, 0) + 1
                chars = sorted(nv.characters.values(), key=lambda c: -counts.get(c.name, 0))
                # same call and seed as H-GATE's commitment_gating._lines
                assign[name] = cast([(c.name, c.gender) for c in chars], geom, mode=mode,
                                    seed=derive_seed(seed, nv.name, mode))
            d = np.zeros(n)
            for i, r in enumerate(rows):
                vg, vp = assign[r["novel"]].get(r["gold"]), assign[r["novel"]].get(r["pred"])
                if r["err"] and vg and vp:
                    d[i] = geom.distance(vg, vp)
            dists[mode] = d
    for mode in modes:
        d = dists[mode]
        total = d.sum()
        res = {}
        for name in (*GATED, "oracle"):
            gated_mass = caught_curve(sc[name], d)  # mass removed by gating the top-k
            committed = (total - gated_mass[::-1]) / n  # index = coverage c = n - k
            res[name] = float(np.mean(committed[1:]))
        res["random"] = float(np.mean([total * c / n / n for c in range(1, n + 1)]))
        gap = res["random"] - res["oracle"]
        res["gap_closed"] = {k: ((res["random"] - res[k]) / gap if gap else None) for k in GATED}
        out[mode] = res
    return out


# --------------------------------------------------------------------------


def _r(x, nd=4):
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, dict):
        return {k: _r(v, nd) for k, v in x.items()}
    if isinstance(x, list):
        return [_r(v, nd) for v in x]
    return x


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    if stub:
        rows = _synthetic(cfg.base_seed)
        gate = {"checked": len(rows), "mismatches": []}
        inputs = {}
    else:
        source = ROOT / p["source_run"]
        rows = _load_saved(source)
        gate = _rederive(rows, int(p["candidates_window"]))
        if gate["mismatches"]:
            raise RuntimeError(f"exact-match gate failed on {len(gate['mismatches'])} rows: "
                               f"{gate['mismatches'][:5]}")
        inputs = {"source_trials": source / "trials.jsonl", "source_results": source / "results.json"}
    n_before = len(rows)
    if p.get("exclude_unscorable_gold"):
        rows = [r for r in rows if r["gold_in_shortlist"]]
    summary, curves, hint, trials = analyse(rows, p, cfg.base_seed, stub, n_before=n_before, gate=gate)
    if not stub and p.get("docs_dir") and not p.get("exclude_unscorable_gold"):
        _write_docs(ROOT / p["docs_dir"], cfg, summary, curves, len(rows),
                    float(sum(r["err"] for r in rows)), hint)
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="gate_xdis", mode="stub" if stub else "real",
                      config_hash=cfg.hash, n_units=len(rows), n_trials=len(trials), summary=summary,
                      verdict_hint=hint,
                      notes=["expected-value tie handling (exact, no RNG)",
                             "the LLM's shortlist is gold-derived; see C_shortlist_random",
                             "re-derived fields gated by exact match against the saved trials"]),
            trials, inputs)


def analyse(rows: list[dict], p: dict, base_seed: int, stub: bool, *, n_before: int | None = None,
            gate: dict | None = None):
    """The pre-registered H-GATE-XDIS analysis over already-labelled rows.

    Split out of `run` (behaviour unchanged) so the convergence pass can apply
    the *identical* analysis to re-labelled rows -- alias-corrected gold
    (H-XDIS-ALIAS) and a product-built shortlist (H-XDIS-PS) -- instead of a
    near-copy that could drift from what H-GATE-XDIS actually measured.
    """
    n_before = len(rows) if n_before is None else n_before
    gate = gate or {"checked": len(rows), "mismatches": []}
    n = len(rows)
    err = np.array([r["err"] for r in rows], dtype=float)
    e_total = float(err.sum())
    sc = scores(rows)
    curves = {k: caught_curve(v, err) for k, v in sc.items()}

    ops: dict[str, dict] = {}
    for name, cur in curves.items():
        o: dict = {f"{rate:.2f}": metrics_at(int(round(rate * n)), float(cur[int(round(rate * n))]), n, e_total)
                   for rate in p["rates"]}
        o["auc_capture"] = float(np.mean(cur[1:] / e_total)) if e_total else 0.0
        o["distinct_score_levels"] = int(len(np.unique(sc[name])))
        o["auroc"] = auroc(sc[name], err) if name != "P0_none" else None
        ops[name] = o

    prim = [float(x) for x in p["primary_rates"]]
    pairs = [("P2a_disagree", "P1_conf"), ("P3_disagree_then_conf", "P1_conf"),
             ("C_shortlist_random", "P1_conf"), ("P2a_disagree", "C_shortlist_random")]
    resamples = int(p["resamples"]) if not stub else 50
    boot_cluster = paired_bootstrap(rows, sc, err, pairs, prim, resamples,
                                    derive_seed(base_seed, "boot-novel"), cluster=True)
    boot_quote = paired_bootstrap(rows, sc, err, pairs, prim, resamples,
                                  derive_seed(base_seed, "boot-quote"), cluster=False)

    strat = {}
    for name_s, pred in strata(rows).items():
        idx = [i for i, r in enumerate(rows) if pred(r)]
        if not idx:
            continue
        cell: dict = {"n_errors": len(idx)}
        for rate in prim:
            k = int(round(rate * n))
            for pol in GATED:
                cell[f"{pol}@{rate}"] = float(inclusion(sc[pol], k)[idx].sum() / len(idx))
        strat[name_s] = cell

    fallback = narrator_fallback(rows, sc, base_seed, stub)

    # ---- decision against the pre-registered criteria (hypotheses.toml)
    def frac(pol, rate):
        return ops[pol][f"{rate:.2f}"]["frac_errors_caught"]

    gains = {pol: {rate: frac(pol, rate) - frac("P1_conf", rate) for rate in prim}
             for pol in ("P2a_disagree", "P3_disagree_then_conf", "C_shortlist_random")}
    best = max(("P2a_disagree", "P3_disagree_then_conf"), key=lambda pol: sum(gains[pol].values()))
    prim_ok = [r for r in prim
               if gains[best][r] >= 0.15 and boot_cluster[f"{best}-P1_conf@{r}"]["ci"][0] > 0]
    low_rate = frac(best, prim[0])
    control_ratio = {r: (gains["C_shortlist_random"][r] / gains["P2a_disagree"][r]
                         if gains["P2a_disagree"][r] > 0 else None) for r in prim}
    artifact = all(v is not None and v >= 0.8 for v in control_ratio.values())
    strat_ok = [s for s, c in strat.items()
                if c["n_errors"] >= 20 and not s.startswith(("method=", "quote_type=", "not_"))
                and c[f"{best}@{prim[-1]}"] > c[f"P1_conf@{prim[-1]}"]]
    if not prim_ok:
        status = "KILL"
    elif len(prim_ok) < len(prim):
        status = "CONDITIONAL"
    elif artifact or len(strat_ok) < 2 or low_rate < 0.40:
        status = "PRODUCT-INFRA"
    else:
        status = "GREENLIGHT"

    summary = _r({
        "n_quotes": n, "n_excluded_unscorable_gold": n_before - n,
        "n_errors": int(e_total), "ladder_error_rate": e_total / n,
        "exact_match_gate": {"checked": gate["checked"], "mismatches": len(gate["mismatches"])},
        "llm_unparsed": sum(r["llm"] is None for r in rows),
        "llm_accuracy_parsed": float(np.mean([r["llm_correct"] for r in rows if r["llm"] is not None])),
        "shortlist": {"mean_size": float(np.mean([r["n_cands"] for r in rows])),
                      "gold_always_in_shortlist": all(r["gold_in_shortlist"] for r in rows)},
        "operating_points": ops,
        "gains_vs_P1": {pol: {str(r): v for r, v in g.items()} for pol, g in gains.items()},
        "bootstrap_novel_cluster": boot_cluster, "bootstrap_quote_paired": boot_quote,
        "control_ratio_of_P2a_gain": {str(k): v for k, v in control_ratio.items()},
        "control_artifact": artifact, "best_xdis_policy": best,
        "primary_rates_passed": prim_ok, "low_rate_capture_best": low_rate,
        "strata": strat, "strata_supporting": strat_ok,
        "narrator_fallback_aurc": fallback, "status": status,
        "not_evaluable": ["P4/P5: qwen confidence was not saved (no logprobs)",
                          "nearby-name substitution: no PDNC field; method= strata are the closest proxy"],
    })
    hint = (f"{status}: best={best}; errors caught @10%/20%: "
            f"P1 {frac('P1_conf', 0.1):.3f}/{frac('P1_conf', 0.2):.3f}, "
            f"{best} {frac(best, 0.1):.3f}/{frac(best, 0.2):.3f}, "
            f"shortlist control {frac('C_shortlist_random', 0.1):.3f}/{frac('C_shortlist_random', 0.2):.3f}")
    trials = [Trial(unit_id=r["unit"], condition="gate", seed=0,
                    outputs={"method": r["method"], "quote_type": r["quote_type"],
                             "addressee_capture": r["addressee_capture"], "vocative": r["vocative"]},
                    metrics={"err": float(r["err"]), **{k: float(round(v[i], 5)) for k, v in sc.items()}})
              for i, r in enumerate(rows)]
    return summary, curves, hint, trials


def _write_docs(d: Path, cfg, summary, curves, n, e_total, hint) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "CONFIG.json").write_text(json.dumps(
        {"experiment_id": HYPOTHESIS_ID, "experiment": "gate_xdis", "config_hash": cfg.hash,
         "base_seed": cfg.base_seed, "params": cfg.params,
         "run_dir": f"data/eval/research/{HYPOTHESIS_ID}/real-{cfg.hash}"}, indent=2, sort_keys=True) + "\n")
    (d / "RESULTS.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    with (d / "CURVES.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["policy", "k", "intervention_rate", "errors_caught", "frac_errors_caught",
                    "selective_risk", "residual_error_rate", "intervention_precision"])
        for pol, cur in curves.items():
            for k in range(n + 1):
                m = metrics_at(k, float(cur[k]), n, e_total)
                w.writerow([pol, k, round(m["intervention_rate"], 4), round(m["errors_caught"], 4),
                            round(m["frac_errors_caught"], 4), round(m["selective_risk"], 4),
                            round(m["residual_error_rate"], 4), round(m["intervention_precision"], 4)])
    ops = summary["operating_points"]
    rate_keys = [k for k in ops["P1_conf"] if k[0] == "0"]
    lines = ["# H-GATE-XDIS results (generated by gate_xdis.py)", "", f"Verdict: {hint}", "",
             f"n = {summary['n_quotes']} quotes, {summary['n_errors']} ladder errors "
             f"(rate {summary['ladder_error_rate']}). Exact-match gate: "
             f"{summary['exact_match_gate']['checked']} checked, "
             f"{summary['exact_match_gate']['mismatches']} mismatches.", "",
             "## Operating points: fraction of ladder errors caught / residual error rate", "",
             "| Policy | AUROC | " + " | ".join(f"{float(r):.0%}" for r in rate_keys) + " |",
             "|---|---|" + "---|" * len(rate_keys)]
    for pol, o in ops.items():
        cells = [f"{o[r]['frac_errors_caught']:.3f} / {o[r]['residual_error_rate']:.3f}" for r in rate_keys]
        lines.append(f"| {pol} | {o['auroc'] if o['auroc'] is not None else '-'} | " + " | ".join(cells) + " |")
    lines += ["", "## Gains in errors caught, with paired novel-cluster bootstrap 95% CI", "",
              "| Comparison | Gain | CI |", "|---|---|---|"]
    for key, v in summary["bootstrap_novel_cluster"].items():
        a_b, rate = key.split("@")
        a, b = a_b.split("-")
        g = ops[a][f"{float(rate):.2f}"]["frac_errors_caught"] - ops[b][f"{float(rate):.2f}"]["frac_errors_caught"]
        lines.append(f"| {a} - {b} @ {float(rate):.0%} | {g:+.3f} | [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}] |")
    lines += ["", "## Strata: share of the category's errors caught at the global budget", "",
              "| Stratum | errors | P1 10% | P2a 10% | P3 10% | ctrl 10% | P1 20% | P2a 20% | P3 20% | ctrl 20% |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for s, c in summary["strata"].items():
        vals = [c.get(f"{pol}@{r}", 0.0) for r in (0.1, 0.2) for pol in GATED]
        lines.append(f"| {s} | {c['n_errors']} | " + " | ".join(f"{v:.2f}" for v in vals) + " |")
    lines += ["", "## Narrator fallback: share of the random-to-oracle salient-error gap closed", ""]
    for mode, res in summary["narrator_fallback_aurc"].items():
        lines.append(f"- {mode}: " + ", ".join(f"{k} {v}" for k, v in res["gap_closed"].items()))
    (d / "RESULTS.md").write_text("\n".join(lines) + "\n")
