"""H-IOL: does a listener who learns the voice->character map predict error
costs that a per-line (uniform) cost model cannot?

Runs `models/listener.py` over PDNC passages (60-quote windows, human gold
speakers and quote types) cast onto EARS voices, with attribution errors
injected by the measured types (`transforms/error_injection.py`). Four
pre-registered predictions (hypotheses.toml H-IOL):

- P1 spillover: comprehension lost on *uncorrupted* lines, per error, as a
  share of the comprehension lost on the corrupted lines themselves. A
  uniform-cost model has spillover 0 by construction.
- P2 tag poisoning: the same number of errors placed only on tagged lines vs
  only on implicit lines -- lower direct cost but higher spillover predicted
  for tagged.
- P3 crossover: the error rate a* at which full cast stops beating a
  single narrator, for diverse vs homogeneous casts.
- P4 late casting: narrator voice for a character until its 2nd tagged line.

Sign stability across the 24-setting listener grid is the robustness test:
a prediction that flips with tau or the turn-taking prior is an artefact of
the parameter choice, not a property of learned mappings.
"""

from __future__ import annotations

import random
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.controllers.casting import cast
from echotales.research.datasets import pdnc
from echotales.research.evaluators.voice_geometry import (
    BankGeometry,
    ears_geometry,
    synthetic_geometry,
)
from echotales.research.models.listener import (
    NARRATOR,
    Line,
    ListenerParams,
    param_grid,
    simulate,
)
from echotales.research.schema import RunResult, Trial
from echotales.research.transforms.error_injection import ERROR_TYPES, inject

HYPOTHESIS_ID = "H-IOL"
DEFAULT_PARAMS = {
    "window": 60, "windows_per_novel": 4, "reps": 2,
    "rates": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    "fixed_errors": 4, "late_k": 2, "casts": ["diverse", "homogeneous"],
    "grid": True, "resamples": 1000, "workers": 8,
}


# --------------------------------------------------------------------------
# passages


def tag_of(q) -> str:
    t = q.quote_type.lower()
    return t if t in ("explicit", "anaphoric") else "implicit"


def windows(novel: pdnc.Novel, size: int, per_novel: int, *, min_tagged: int = 6,
            min_implicit: int = 20) -> list[list[pdnc.Quote]]:
    """Non-overlapping windows with enough structure for the predictions to be
    measurable: >= 3 speakers, >= 6 tagged and >= 20 implicit lines. Evenly
    spaced through the novel so no single part of a book dominates."""
    qs = [q for q in novel.quotes if q.speaker in novel.characters]
    cands = []
    for s in range(0, len(qs) - size + 1, size):
        w = qs[s:s + size]
        tags = [tag_of(q) for q in w]
        if (len({q.speaker for q in w}) >= 3 and sum(t != "implicit" for t in tags) >= min_tagged
                and sum(t == "implicit" for t in tags) >= min_implicit):
            cands.append(w)
    if len(cands) <= per_novel:
        return cands
    step = len(cands) / per_novel
    return [cands[int(i * step)] for i in range(per_novel)]


def render_lines(win, assign, rendered_speaker: list[str], policy: str, late_k: int) -> list[Line]:
    """Voice per line under a rendering policy. `rendered_speaker` is the
    attributor's (possibly wrong) speaker for each line."""
    out = []
    tagged_seen: dict[str, int] = {}
    for q, rs in zip(win, rendered_speaker):
        t = tag_of(q)
        if policy == "narrator":
            v = NARRATOR
        elif policy == "late":
            # The renderer only knows its own attribution: a character keeps
            # the narrator voice until the attributor has put it on
            # `late_k` tagged lines.
            v = assign[rs] if tagged_seen.get(rs, 0) >= late_k else NARRATOR
        else:
            v = assign[rs]
        if t != "implicit":
            tagged_seen[rs] = tagged_seen.get(rs, 0) + 1
        out.append(Line(speaker=q.speaker, voice=v, tag=t))
    return out


def voice_dist(geom: BankGeometry):
    def dist(u, v):
        if u == v:
            return 0.0
        if NARRATOR in (u, v):
            return 1.0  # the narrator is never confused with a character voice
        return geom.distance(u, v)
    return dist


def novel_cast(novel: pdnc.Novel, geom: BankGeometry, mode: str, base_seed: int) -> dict[str, str]:
    counts: dict[str, int] = {}
    for q in novel.quotes:
        counts[q.speaker] = counts.get(q.speaker, 0) + 1
    chars = sorted(novel.characters.values(), key=lambda c: (-counts.get(c.name, 0), c.name))
    return cast([(c.name, c.gender) for c in chars], geom, mode=mode,
                seed=derive_seed(base_seed, novel.name, mode))


def window_context(novel: pdnc.Novel, win):
    speakers = sorted({q.speaker for q in win})
    wcast = sorted(set(speakers) | {a for q in win for a in q.addressees if a in novel.characters})
    mf = {c: novel.gender_of(c) for c in wcast if novel.gender_of(c) in ("M", "F")}
    qd = [{"speaker": q.speaker, "addressees": list(q.addressees)} for q in win]
    return speakers, mf, qd


# --------------------------------------------------------------------------
# one novel (worker)


def _novel_task(args):
    (name, stub, base_seed, prm, geom_d, params_list) = args
    geom = BankGeometry(geom_d["ids"], geom_d["genders"], np.asarray(geom_d["emb"]))
    novel = pdnc.synthetic_novel(seed=base_seed) if stub else pdnc.load_novel(name)
    dist = voice_dist(geom)
    rows = []
    for wi, win in enumerate(windows(novel, int(prm["window"]), int(prm["windows_per_novel"]),
                                     min_implicit=int(prm.get("min_implicit", 20)))):
        speakers, mf, qd = window_context(novel, win)
        n = len(win)
        tagged_idx = {i for i, q in enumerate(win) if tag_of(q) != "implicit"}
        implicit_idx = set(range(n)) - tagged_idx
        third = n // 3
        unit = f"{novel.name}:w{wi}"
        gold = [q.speaker for q in win]
        for cmode in prm["casts"]:
            assign = novel_cast(novel, geom, cmode, base_seed)
            for pi, lp in params_list:
                def run(rendered, policy="full", lp=lp, assign=assign):
                    lines = render_lines(win, assign, rendered, policy, int(prm["late_k"]))
                    return [o.comprehension for o in simulate(lines, speakers, dist, lp)]

                clean = {pol: run(gold, pol) for pol in ("full", "narrator", "late")}
                for pol, comp in clean.items():
                    rows.append({"unit": unit, "novel": novel.name, "cast": cmode, "p": pi,
                                 "cond": f"clean|{pol}", "comp": float(np.mean(comp)),
                                 "n_err": 0, "direct": 0.0, "spill": 0.0})

                def score(cond, injections, policy="full", clean=clean, run=run, cmode=cmode, pi=pi):
                    rendered = list(gold)
                    for inj in injections:
                        rendered[inj.quote_index] = inj.rendered_as
                    comp = run(rendered, policy)
                    base = clean[policy]
                    bad = {inj.quote_index for inj in injections}
                    rows.append({"unit": unit, "novel": novel.name, "cast": cmode, "p": pi,
                                 "cond": cond, "comp": float(np.mean(comp)), "n_err": len(bad),
                                 "direct": sum(base[i] - comp[i] for i in bad),
                                 "spill": sum(base[i] - comp[i] for i in range(n) if i not in bad)})

                k = int(prm["fixed_errors"])
                for rep in range(int(prm["reps"])):
                    for et in ERROR_TYPES:
                        for rate in prm["rates"]:
                            sd = derive_seed(base_seed, unit, cmode, et, rate, rep)
                            inj = inject(qd, mf, rate=rate, error_type=et, seed=sd)
                            for pol in ("full", "late"):
                                score(f"rate|{pol}|{et}|{rate}", inj, pol)
                        for place, elig in (("tagged", tagged_idx), ("implicit", implicit_idx)):
                            sd = derive_seed(base_seed, unit, cmode, et, place, rep)
                            score(f"place|{place}|{et}",
                                  inject(qd, mf, rate=k / n, error_type=et, seed=sd, eligible=elig))
                        for pos, elig in (("early", set(range(third))),
                                          ("late", set(range(n - third, n)))):
                            sd = derive_seed(base_seed, unit, cmode, et, pos, rep)
                            score(f"pos|{pos}|{et}",
                                  inject(qd, mf, rate=k / n, error_type=et, seed=sd, eligible=elig))
    return rows


# --------------------------------------------------------------------------
# analysis


def _per_error(rows, prefix, key):
    """Pooled per-error cost (sum of cost / sum of errors) over conditions."""
    sel = [r for r in rows if r["cond"].startswith(prefix) and r["n_err"] > 0]
    ne = sum(r["n_err"] for r in sel)
    return sum(r[key] for r in sel) / ne if ne else float("nan")


def _crossover(rows, cmode, policy="full"):
    """Smallest injected rate at which mean comprehension under `policy` falls
    to the narrator's, linearly interpolated; None if it never does within
    the tested rates (censored)."""
    mine = [r for r in rows if r["cast"] == cmode]
    narr = np.mean([r["comp"] for r in mine if r["cond"] == "clean|narrator"])
    pts = [(0.0, np.mean([r["comp"] for r in mine if r["cond"] == f"clean|{policy}"]))]
    rates = sorted({float(r["cond"].split("|")[3]) for r in mine
                    if r["cond"].startswith(f"rate|{policy}|")})
    for rate in rates:
        pts.append((rate, np.mean([r["comp"] for r in mine
                                   if r["cond"].startswith(f"rate|{policy}|")
                                   and float(r["cond"].split("|")[3]) == rate])))
    for (r0, c0), (r1, c1) in zip(pts, pts[1:]):
        if c0 > narr >= c1:
            return float(r0 + (c0 - narr) * (r1 - r0) / (c0 - c1))
    return None


def predictions(rows, max_rate):
    direct = _per_error(rows, "rate|full|", "direct")
    spill = _per_error(rows, "rate|full|", "spill")
    late_spill = _per_error(rows, "rate|late|", "spill")
    pt = {k: {"direct": _per_error(rows, f"place|{k}|", "direct"),
              "spill": _per_error(rows, f"place|{k}|", "spill")} for k in ("tagged", "implicit")}
    pos = {k: _per_error(rows, f"pos|{k}|", "spill") + _per_error(rows, f"pos|{k}|", "direct")
           for k in ("early", "late")}
    a = {c: _crossover(rows, c) for c in sorted({r["cast"] for r in rows})}
    # A censored a* (full cast never falls to the narrator within the tested
    # rates) counts as max_rate: conservative toward "no difference".
    a_eff = {c: (v if v is not None else max_rate) for c, v in a.items()}
    a_diff = a_eff.get("diverse", 0.0) - a_eff.get("homogeneous", 0.0)
    by_type = {et: _per_error(rows, f"rate|full|{et}", "direct")
               + _per_error(rows, f"rate|full|{et}", "spill") for et in ERROR_TYPES}
    return {
        "direct_per_error": direct, "spill_per_error": spill,
        "spill_over_direct": spill / direct if direct else float("nan"),
        "P1_spillover": bool(direct and spill / direct >= 0.25),
        "placement": pt,
        "P2_tag_poisoning": bool(pt["tagged"]["direct"] < pt["implicit"]["direct"]
                                 and pt["tagged"]["spill"] > pt["implicit"]["spill"]),
        "crossover_a_star": a, "a_star_diverse_minus_homogeneous": a_diff,
        "P3_crossover_differs": bool(abs(a_diff) >= 0.05), "P3_sign": int(np.sign(a_diff)),
        "late_cast_spill_per_error": late_spill,
        "P4_late_reduces_spill": bool(late_spill < spill),
        "position_total_per_error": pos,
        "early_over_late": pos["early"] / pos["late"] if pos["late"] else float("nan"),
        "total_cost_per_error_by_type": by_type,
        "clean_comprehension": {f"{c}|{pol}": float(np.mean([r["comp"] for r in rows if r["cast"] == c
                                                              and r["cond"] == f"clean|{pol}"]))
                                for c in sorted({r["cast"] for r in rows})
                                for pol in ("full", "late", "narrator")},
    }


def rnd(x):
    if isinstance(x, float):
        return round(x, 5)
    if isinstance(x, dict):
        return {k: rnd(v) for k, v in x.items()}
    return x


def vars_of(lp: ListenerParams) -> dict:
    return {"tau": lp.tau, "rho": lp.rho, "lam_alt": lp.lam_alt, "w_self": lp.w_self,
            "alpha": lp.alpha}


def run(cfg: ExperimentConfig, *, stub: bool):
    prm = cfg.params
    if stub:
        names = ["synthetic"]
        geom = synthetic_geometry(seed=cfg.base_seed)
        grid = [ListenerParams(), ListenerParams(tau=0.12, lam_alt=0.0)]
        prm = {**prm, "rates": [0.2, 0.4], "reps": 1, "window": 40, "windows_per_novel": 2,
               "resamples": 50, "min_implicit": 8}
        inputs = {}
    else:
        names = pdnc.available()
        geom = ears_geometry()
        grid = [ListenerParams(), *(param_grid() if prm["grid"] else [])]
        inputs = {"pdnc_root": pdnc.PDNC_ROOT}
    params_list = list(enumerate(grid))  # index 0 = the default (pre-registered "median")
    geom_d = {"ids": geom.ids, "genders": geom.genders, "emb": geom.emb.tolist()}
    tasks = [(n, stub, cfg.base_seed, prm, geom_d, params_list) for n in names]
    if stub or int(prm["workers"]) <= 1:
        results = [_novel_task(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=int(prm["workers"])) as ex:
            results = list(ex.map(_novel_task, tasks))  # map keeps task order: deterministic
    rows = [r for rs in results for r in rs]
    max_rate = max(prm["rates"])
    by_p = {pi: [r for r in rows if r["p"] == pi] for pi, _ in params_list}
    default = predictions(by_p[0], max_rate)

    # Cluster bootstrap over novels at the default setting (P1, P2).
    units = sorted({r["novel"] if not stub else r["unit"] for r in by_p[0]})
    key = "unit" if stub else "novel"
    by_cluster = {u: [r for r in by_p[0] if r[key] == u] for u in units}
    rng = random.Random(derive_seed(cfg.base_seed, "boot"))
    boot: dict[str, list[float]] = {"spill_over_direct": [], "tag_minus_implicit_spill": [],
                                    "tag_minus_implicit_direct": []}
    for _ in range(int(prm["resamples"])):
        samp = [r for u in (rng.choice(units) for _ in units) for r in by_cluster[u]]
        pr = predictions(samp, max_rate)
        boot["spill_over_direct"].append(pr["spill_over_direct"])
        boot["tag_minus_implicit_spill"].append(pr["placement"]["tagged"]["spill"]
                                                - pr["placement"]["implicit"]["spill"])
        boot["tag_minus_implicit_direct"].append(pr["placement"]["tagged"]["direct"]
                                                 - pr["placement"]["implicit"]["direct"])
    ci = {k: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))]
          for k, v in boot.items() if v}

    grid_preds = {pi: predictions(by_p[pi], max_rate) for pi, _ in params_list[1:]}
    stable: dict[str, dict] = {}
    for k in ("P1_spillover", "P2_tag_poisoning", "P4_late_reduces_spill"):
        vals = [g[k] for g in grid_preds.values()]
        stable[k] = {"true_in": sum(vals), "of": len(vals)}
    signs = [g["P3_sign"] for g in grid_preds.values() if g["P3_crossover_differs"]]
    stable["P3_sign"] = {"positive": signs.count(1), "negative": signs.count(-1),
                         "no_difference": len(grid_preds) - len(signs)}

    flips = [k for k in ("P1_spillover", "P2_tag_poisoning")
             if stable[k]["true_in"] not in (0, stable[k]["of"])]
    if stable["P3_sign"]["positive"] and stable["P3_sign"]["negative"]:
        flips.append("P3_sign")
    killed = (not default["P1_spillover"]) or bool(flips)
    hint = ("KILL" if killed else "SURVIVES at model level") + (
        f": spill/direct={default['spill_over_direct']:.3f}, P2={default['P2_tag_poisoning']}, "
        f"a*={default['crossover_a_star']}, sign flips across grid: {flips or 'none'}")

    summary = {
        "novels": len({r['novel'] for r in by_p[0]}), "windows": len({r['unit'] for r in by_p[0]}),
        "listener_settings": len(params_list), "default_params": vars_of(grid[0]),
        "default": rnd(default), "default_ci_cluster_bootstrap": rnd(ci),
        "grid_stability": stable, "sign_flips": flips,
        "grid": {str(pi): {"params": vars_of(lp), **rnd({k: grid_preds[pi][k] for k in (
            "spill_over_direct", "P2_tag_poisoning", "crossover_a_star",
            "late_cast_spill_per_error", "spill_per_error")})}
            for pi, lp in params_list[1:]},
    }
    trials = [Trial(unit_id=r["unit"], condition=f"{r['cast']}|{r['cond']}", seed=0,
                    metrics={"comp": round(r["comp"], 5), "direct": round(r["direct"], 5),
                             "spill": round(r["spill"], 5), "n_err": r["n_err"]})
              for r in by_p[0]]
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="ideal_listener",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len({t.unit_id for t in trials}), n_trials=len(trials),
                      summary=summary, verdict_hint=hint,
                      notes=["model-level predictions only; they become a result about people "
                             "only when the H-COST v2 listening study tests them",
                             "voice distance = Chatterbox speaker-embedding cosine; tau maps it to "
                             "confusability and is swept, not fitted"]),
            trials, inputs)
