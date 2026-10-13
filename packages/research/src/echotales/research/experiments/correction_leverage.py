"""H-LEVER: with a fixed correction budget, which lines should a human fix?

Mutation of C26 (counterfactual value of a correction; parked because the
real correction log is 34 lines) and C04 (policy capped by the posterior):
PDNC gold serves as the oracle corrector, so the correction budget can be
simulated at any size. The question is the *allocation* objective:

- ``lowest_conf``: fix the lines the error score finds most suspicious --
  what every review queue (and FOLIO/MALLS-style relabelling) does;
- ``first_appearance``: fix each rendered voice's earliest lines;
- ``leverage``: P(error | score) x listener leverage, where leverage is how
  much the *planning* listener's comprehension of the passage depends on
  the line (its comprehension drop if the line's voice were swapped), so a
  tagged line early in a passage, which teaches the voice map, ranks above
  an implicit line late in it;
- ``random`` and ``oracle`` (true errors, greedy true gain) bracket them.

Circularity guard (pre-registered): leverage is planned with the default
listener but scored with a *mismatched* listener (other tau, anaphora
reliability, turn prior and self-training), so the policy is not graded by
its own objective. Raw errors fixed are reported too.

The error score is synthetic with a controlled AUROC: 0.60 (the product
ladder's measured value, H-CAL) and 0.80 (an LLM-grade posterior).
"""

from __future__ import annotations

import math
import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.stats import norm

from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.datasets import pdnc
from echotales.research.evaluators.voice_geometry import (
    BankGeometry,
    ears_geometry,
    synthetic_geometry,
)
from echotales.research.experiments.ideal_listener import (
    novel_cast,
    render_lines,
    voice_dist,
    window_context,
    windows,
)
from echotales.research.models.listener import ListenerParams, simulate
from echotales.research.schema import RunResult, Trial
from echotales.research.transforms.error_injection import inject

HYPOTHESIS_ID = "H-LEVER"
#: Error-type mix of the product ladder's real errors on PDNC (H-CAL: 52%
#: addressee capture; ~43% gender flips overall, H-GATE).
DEFAULT_PARAMS = {
    "window": 60, "windows_per_novel": 4, "error_rate": 0.25,
    "type_mix": {"addressee": 0.52, "cross_gender": 0.28, "same_gender": 0.20},
    "budgets": [0.05, 0.1, 0.2], "aurocs": [0.6, 0.8], "reps": 3,
    "plan_listener": {"tau": 0.06, "rho": 0.9, "lam_alt": 0.3, "w_self": 0.0},
    "eval_listener": {"tau": 0.12, "rho": 0.7, "lam_alt": 0.4, "w_self": 0.5},
    "resamples": 1000, "workers": 8,
    # "signed" is the pre-registered v1 implementation: sensitivity measured
    # against the current (partly wrong) rendering, which gives 52% of wrong
    # lines a negative leverage (diagnosed 2026-10-02), so the policy steered
    # away from errors. "abs" (v2, disclosed post-hoc deviation, same kill
    # criterion) uses the magnitude of a line's influence, the quantity the
    # hypothesis actually names.
    "leverage_mode": "abs",
}
POLICIES = ("random", "lowest_conf", "first_appearance", "leverage", "oracle")


def _inject_mix(qd, mf, rate, mix, seed):
    used: set[int] = set()
    out = []
    for et in sorted(mix):
        elig = set(range(len(qd))) - used
        inj = inject(qd, mf, rate=rate * mix[et], error_type=et,
                     seed=derive_seed(seed, et), eligible=elig)
        out.extend(inj)
        used |= {i.quote_index for i in inj}
    return out


def _posterior(score: float, mu: float, base: float) -> float:
    """P(error | score) under the score's own generative model (unit-variance
    Gaussians separated by mu), i.e. a perfectly calibrated posterior."""
    a = base * math.exp(-0.5 * (score - mu) ** 2)
    b = (1 - base) * math.exp(-0.5 * score ** 2)
    return a / (a + b)


def _window_task(args):
    (name, stub, base_seed, prm, geom_d) = args
    geom = BankGeometry(geom_d["ids"], geom_d["genders"], np.asarray(geom_d["emb"]))
    novel = pdnc.synthetic_novel(seed=base_seed) if stub else pdnc.load_novel(name)
    dist = voice_dist(geom)
    plan = ListenerParams(**prm["plan_listener"])
    evl = ListenerParams(**prm["eval_listener"])
    assign = novel_cast(novel, geom, "diverse", base_seed)
    rows = []
    for wi, win in enumerate(windows(novel, int(prm["window"]), int(prm["windows_per_novel"]),
                                     min_implicit=int(prm.get("min_implicit", 20)))):
        speakers, mf, qd = window_context(novel, win)
        gold = [q.speaker for q in win]
        n = len(win)
        unit = f"{novel.name}:w{wi}"

        def comp(rendered, lp, win=win, speakers=speakers):
            lines = render_lines(win, assign, rendered, "full", 2)
            return [o.comprehension for o in simulate(lines, speakers, dist, lp)]

        for rep in range(int(prm["reps"])):
            seed = derive_seed(base_seed, unit, rep)
            inj = _inject_mix(qd, mf, float(prm["error_rate"]), prm["type_mix"], seed)
            rendered = list(gold)
            for i in inj:
                rendered[i.quote_index] = i.rendered_as
            err = [rendered[i] != gold[i] for i in range(n)]
            if not any(err):
                continue
            base_rate = sum(err) / n
            base_eval = float(np.mean(comp(rendered, evl)))
            base_plan = sum(comp(rendered, plan))
            # Leverage under the planning listener: what the passage loses if
            # line i's voice is swapped to the nearest other voice in the
            # window. Computed from the rendering alone, never from gold.
            rspk = sorted(set(rendered))
            lev = []
            for i in range(n):
                cur = assign[rendered[i]]
                others = [s for s in rspk if assign[s] != cur]
                if not others:
                    lev.append(0.0)
                    continue
                alt = min(others, key=lambda s: (dist(cur, assign[s]), s))
                r2 = list(rendered)
                r2[i] = alt
                d_i = base_plan - sum(comp(r2, plan))
                lev.append(abs(d_i) if prm.get("leverage_mode", "signed") == "abs" else d_i)
            seen: dict[str, int] = {}
            order_first = []
            for i, s in enumerate(rendered):
                seen[s] = seen.get(s, 0) + 1
                order_first.append((seen[s], i))
            for auc in prm["aurocs"]:
                mu = math.sqrt(2) * float(norm.ppf(float(auc)))
                rng = random.Random(derive_seed(seed, "score", auc))
                score = [(mu if e else 0.0) + rng.gauss(0, 1) for e in err]
                post = [_posterior(s, mu, base_rate) for s in score]
                for b in prm["budgets"]:
                    k = max(1, round(float(b) * n))
                    rr = random.Random(derive_seed(seed, "rand", auc, b))
                    picks = {
                        "random": rr.sample(range(n), k),
                        "lowest_conf": sorted(range(n), key=lambda i: (-score[i], i))[:k],
                        "first_appearance": [i for _, i in sorted(order_first)][:k],
                        "leverage": sorted(range(n), key=lambda i: (-post[i] * max(lev[i], 1e-6), i))[:k],
                    }
                    # Oracle: greedy true marginal gain under the eval listener.
                    fixed = list(rendered)
                    chosen: list[int] = []
                    cur_sum = sum(comp(fixed, evl))
                    for _ in range(min(k, sum(err))):
                        best, best_gain = None, -1e9
                        for i in range(n):
                            if err[i] and i not in chosen:
                                t = list(fixed)
                                t[i] = gold[i]
                                g = sum(comp(t, evl)) - cur_sum
                                if g > best_gain:
                                    best, best_gain = i, g
                        chosen.append(best)
                        fixed[best] = gold[best]
                        cur_sum += best_gain
                    picks["oracle"] = chosen
                    fa = set(picks["first_appearance"])
                    for pol in POLICIES:
                        sel = set(picks[pol])
                        r3 = [gold[i] if i in sel else rendered[i] for i in range(n)]
                        rows.append({
                            "unit": unit, "rep": rep, "auc": auc, "budget": b, "policy": pol,
                            "gain_eval": float(np.mean(comp(r3, evl))) - base_eval,
                            "errors_fixed": sum(err[i] for i in sel),
                            "jacc_first": len(sel & fa) / len(sel | fa) if sel | fa else 0.0,
                        })
    return rows


def run(cfg: ExperimentConfig, *, stub: bool):
    prm = cfg.params
    if stub:
        names = ["synthetic"]
        geom = synthetic_geometry(seed=cfg.base_seed)
        prm = {**prm, "window": 40, "windows_per_novel": 2, "reps": 1, "budgets": [0.1],
               "min_implicit": 8, "resamples": 50}
        inputs = {}
    else:
        names = pdnc.available()
        geom = ears_geometry()
        inputs = {"pdnc_root": pdnc.PDNC_ROOT}
    geom_d = {"ids": geom.ids, "genders": geom.genders, "emb": geom.emb.tolist()}
    tasks = [(n, stub, cfg.base_seed, prm, geom_d) for n in names]
    if stub:
        results = [_window_task(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=int(prm["workers"])) as ex:
            results = list(ex.map(_window_task, tasks))  # ordered: deterministic
    rows = [r for rs in results for r in rs]

    cells = {}
    for auc in prm["aurocs"]:
        for b in prm["budgets"]:
            sel = [r for r in rows if r["auc"] == auc and r["budget"] == b]
            if not sel:
                continue
            cell: dict = {pol: {
                "gain_eval": round(float(np.mean([r["gain_eval"] for r in sel if r["policy"] == pol])), 5),
                "errors_fixed": round(float(np.mean([r["errors_fixed"] for r in sel if r["policy"] == pol])), 3)}
                for pol in POLICIES}
            units = sorted({r["unit"] for r in sel})
            vals = []
            for u in units:
                d = [r for r in sel if r["unit"] == u]
                vals.append(float(np.mean([r["gain_eval"] for r in d if r["policy"] == "leverage"])
                                  - np.mean([r["gain_eval"] for r in d if r["policy"] == "lowest_conf"])))
            rng = random.Random(derive_seed(cfg.base_seed, "boot", auc, b))
            boots = sorted(float(np.mean([rng.choice(vals) for _ in vals]))
                           for _ in range(int(prm["resamples"])))
            cell["leverage_minus_lowest_conf"] = {
                "mean": round(float(np.mean(vals)), 5),
                "ci": [round(boots[int(0.025 * len(boots))], 5),
                       round(boots[max(0, int(0.975 * len(boots)) - 1)], 5)]}
            cell["leverage_jaccard_with_first_appearance"] = round(float(np.mean(
                [r["jacc_first"] for r in sel if r["policy"] == "leverage"])), 4)
            cells[f"auc{auc}|budget{b}"] = cell
    key = f"auc{prm['aurocs'][0]}|budget0.1"
    primary = cells.get(key) or next(iter(cells.values()))
    ci = primary["leverage_minus_lowest_conf"]["ci"]
    killed = ci[0] <= 0 or primary["leverage_jaccard_with_first_appearance"] > 0.8
    hint = ("KILL" if killed else "SURVIVES") + (
        f" ({key}): leverage minus lowest_conf {primary['leverage_minus_lowest_conf']}, "
        f"Jaccard with first-appearance {primary['leverage_jaccard_with_first_appearance']}")
    summary = {"windows": len({r["unit"] for r in rows}), "primary_cell": key, "cells": cells,
               "plan_listener": prm["plan_listener"], "eval_listener": prm["eval_listener"]}
    trials = [Trial(unit_id=r["unit"], condition=f"{r['policy']}|auc{r['auc']}|b{r['budget']}|r{r['rep']}",
                    seed=0, metrics={"gain_eval": round(r["gain_eval"], 5),
                                     "errors_fixed": r["errors_fixed"]}) for r in rows]
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="correction_leverage",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len({t.unit_id for t in trials}), n_trials=len(trials),
                      summary=summary, verdict_hint=hint,
                      notes=["outcome is a listener *model's* comprehension: conditional on H-IOL "
                             "being right about people", "error score is synthetic with a set AUROC"]),
            trials, inputs)
