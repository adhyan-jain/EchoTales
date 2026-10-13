"""H-CCAST: does knowing *which* characters the attributor confuses make for
a better cast than simply making the whole cast less distinct?

Mutation of the killed hedge (C13/H-HEDGE): voice identity is perceived
categorically, so a graded voice cannot hedge one line. The cast as a whole
can still be shaped: two characters the attributor often swaps could get
similar voices (their swaps are masked) while pairs it never swaps stay far
apart (correct lines stay identifiable). H-GATE measured that a homogeneous
cast masks 22% of errors but also blurs every correct line; the question is
whether *confusion-aware* shaping beats that blunt trade.

Per novel (PDNC, product ladder errors from `attribution_probe`):

- **need** for distinctness of a pair = how often the two speak within 3
  quotes of each other (gold) -- the lines a listener must tell apart;
- **confusion** of a pair = ladder errors swapping them. On held-out novels
  it is *predicted* from pair features (addressee co-occurrence, same
  gender, line counts) fitted by Poisson regression on the other fold, never
  read from the test novel's own errors;
- a cast maximises ``sum need*d - lam * sum w*d`` by deterministic local
  search over each gender's EARS voices, where ``w`` is the predicted
  confusion (confusion-aware) or the same total spread uniformly over all
  pairs (confusion-blind control). Sweeping ``lam`` traces each method's
  frontier of identifiability (sum need*d on gold) vs salient-error mass
  (sum d over the test novel's *real* errors).

Kill (pre-registered): the novel-level bootstrap of the relative
hypervolume gain (aware over blind) has a CI including 0.
"""

from __future__ import annotations

import math
import random
from itertools import combinations

import numpy as np
from scipy import optimize

from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.controllers.casting import cast
from echotales.research.datasets import pdnc
from echotales.research.evaluators.voice_geometry import (
    BankGeometry,
    ears_geometry,
    synthetic_geometry,
)
from echotales.research.schema import RunResult, Trial
from echotales.research.transforms.attribution_probe import probe

HYPOTHESIS_ID = "H-CCAST"
DEFAULT_PARAMS = {"min_lines": 10, "near": 3, "lams": [0.0, 0.25, 0.5, 1, 2, 4, 8, 16, 32],
                  "resamples": 1000}


def _novel_data(nv: pdnc.Novel, min_lines: int, near: int):
    counts: dict[str, int] = {}
    for q in nv.quotes:
        counts[q.speaker] = counts.get(q.speaker, 0) + 1
    chars = sorted((c for c in nv.characters.values()
                    if counts.get(c.name, 0) >= min_lines and c.gender in ("M", "F")),
                   key=lambda c: (-counts[c.name], c.name))
    names = [c.name for c in chars]
    in_cast = set(names)
    pairs = list(combinations(sorted(names), 2))
    need = {p: 0.0 for p in pairs}
    adr = {p: 0.0 for p in pairs}
    qs = [q for q in nv.quotes if q.speaker in in_cast]
    for i, q in enumerate(qs):
        for q2 in qs[i + 1:i + 1 + near]:
            if q2.speaker != q.speaker:
                need[tuple(sorted((q.speaker, q2.speaker)))] += 1
        for a in q.addressees:
            if a in in_cast and a != q.speaker:
                adr[tuple(sorted((q.speaker, a)))] += 1
    errors = []
    for r in probe(nv):
        if not (r.resolved and r.owners):
            continue
        pred = r.predicted or r.owners[0]
        if not r.correct_lenient and r.gold in in_cast and pred in in_cast and pred != r.gold:
            errors.append((r.gold, pred))
    conf = {p: 0.0 for p in pairs}
    for g, pr in errors:
        conf[tuple(sorted((g, pr)))] += 1
    gender = {c.name: c.gender for c in chars}
    feats = {p: [1.0, math.log1p(adr[p]), 1.0 if gender[p[0]] == gender[p[1]] else 0.0,
                 math.log(counts[p[0]] * counts[p[1]])] for p in pairs}
    return {"name": nv.name, "chars": chars, "pairs": pairs, "need": need, "conf": conf,
            "feats": feats, "errors": errors}


def _fit_poisson(train) -> np.ndarray:
    X = np.array([d["feats"][p] for d in train for p in d["pairs"]])
    y = np.array([d["conf"][p] for d in train for p in d["pairs"]])

    def nll(b):
        eta = np.clip(X @ b, -30, 30)
        return float(np.sum(np.exp(eta) - y * eta)) + 1e-3 * float(b @ b)

    return optimize.minimize(nll, np.zeros(X.shape[1]), method="L-BFGS-B").x


def _search(d, geom: BankGeometry, w: dict, lam: float, seed: int) -> dict[str, str]:
    """Deterministic coordinate ascent starting from the diverse cast."""
    assign = cast([(c.name, c.gender) for c in d["chars"]], geom, mode="diverse", seed=seed)
    pool = {g: [v for v, gg in zip(geom.ids, geom.genders) if gg == g] for g in ("M", "F")}
    nbr: dict[str, list[tuple[str, float]]] = {c.name: [] for c in d["chars"]}
    for p in d["pairs"]:
        coef = d["need"][p] - lam * w[p]
        nbr[p[0]].append((p[1], coef))
        nbr[p[1]].append((p[0], coef))
    for _ in range(10):
        changed = False
        for c in d["chars"]:
            cur = assign[c.name]

            def val(v, c=c):
                return sum(coef * geom.distance(v, assign[o]) for o, coef in nbr[c.name])

            best = max(pool[c.gender], key=lambda v: (round(val(v), 9), v == cur, v))
            if best != cur and val(best) > val(cur) + 1e-9:
                assign[c.name] = best
                changed = True
        if not changed:
            break
    return assign


def _evaluate(d, geom, assign):
    ident = sum(d["need"][p] * geom.distance(assign[p[0]], assign[p[1]]) for p in d["pairs"])
    err = sum(geom.distance(assign[g], assign[pr]) for g, pr in d["errors"])
    return ident, err


def _hypervolume(points, ref_err, ref_id=0.0) -> float:
    """Area dominated by (low error mass, high identifiability) points, up to
    the reference error mass."""
    frontier, best_i = [], ref_id
    for e, i in sorted(set(points)):
        if i > best_i:
            frontier.append((e, i))
            best_i = i
    area = 0.0
    for k, (e, i) in enumerate(frontier):
        e_next = frontier[k + 1][0] if k + 1 < len(frontier) else ref_err
        area += max(0.0, e_next - e) * (i - ref_id)
    return area


def _corr(x, y):
    if len(x) > 2 and np.std(x) > 0 and np.std(y) > 0:
        return float(np.corrcoef(x, y)[0, 1])
    return None


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    if stub:
        novels = []
        for k in range(4):
            nv = pdnc.synthetic_novel(seed=cfg.base_seed + k, n_quotes=200)
            nv.name = f"synthetic{k}"
            novels.append(nv)
        geom = synthetic_geometry(seed=cfg.base_seed)
        inputs = {}
    else:
        novels = [pdnc.load_novel(n) for n in pdnc.available()]
        geom = ears_geometry()
        inputs = {"pdnc_root": pdnc.PDNC_ROOT}
    data = [_novel_data(nv, int(p["min_lines"]), int(p["near"])) for nv in novels]
    if stub:
        # The synthetic ladder is nearly error-free; plant addressee captures
        # (the dominant real error class) so the stub exercises every path.
        for d, nv in zip(data, novels):
            for q in nv.quotes[::5]:
                if q.addressees and q.addressees[0] != q.speaker:
                    d["errors"].append((q.speaker, q.addressees[0]))
                    d["conf"][tuple(sorted((q.speaker, q.addressees[0])))] += 1
    data = [d for d in data if len(d["chars"]) >= 3 and d["errors"]]
    folds = [data[0::2], data[1::2]]
    per_novel, trials = [], []
    for fi, test in enumerate(folds):
        if not folds[1 - fi]:
            continue
        beta = _fit_poisson(folds[1 - fi])
        for d in test:
            pred = {pp: float(np.exp(np.clip(np.array(d["feats"][pp]) @ beta, -30, 30)))
                    for pp in d["pairs"]}
            tot = sum(pred.values())
            blind = {pp: tot / len(d["pairs"]) for pp in d["pairs"]}
            # Scale both penalties to the need scale so one lam grid serves both.
            s = sum(d["need"].values()) / max(tot, 1e-9)
            pts: dict[str, list] = {"aware": [], "blind": []}
            for lam in p["lams"]:
                for meth, w in (("aware", pred), ("blind", blind)):
                    a = _search(d, geom, {k: v * s for k, v in w.items()}, float(lam),
                                derive_seed(cfg.base_seed, d["name"]))
                    ident, err = _evaluate(d, geom, a)
                    pts[meth].append((err, ident))
                    trials.append(Trial(unit_id=d["name"], condition=f"{meth}|{lam}", seed=0,
                                        metrics={"ident": round(ident, 5), "err_mass": round(err, 5)}))
            ref = max(e for v in pts.values() for e, _ in v) * 1.05 + 1e-9
            hv = {m: _hypervolume(v, ref) for m, v in pts.items()}
            per_novel.append({
                "novel": d["name"], "hv_aware": hv["aware"], "hv_blind": hv["blind"],
                "rel_gain": (hv["aware"] - hv["blind"]) / hv["blind"] if hv["blind"] else 0.0,
                "corr_pred_conf_vs_need": _corr([pred[pp] for pp in d["pairs"]],
                                                [d["need"][pp] for pp in d["pairs"]]),
                "corr_pred_vs_real_conf": _corr([pred[pp] for pp in d["pairs"]],
                                                [d["conf"][pp] for pp in d["pairs"]]),
                "errors": len(d["errors"]), "chars": len(d["chars"])})
    gains = [r["rel_gain"] for r in per_novel]
    rng = random.Random(derive_seed(cfg.base_seed, "boot"))
    boots = sorted(float(np.mean([rng.choice(gains) for _ in gains]))
                   for _ in range(int(p["resamples"]))) if gains else [0.0]
    lo, hi = boots[int(0.025 * len(boots))], boots[max(0, int(0.975 * len(boots)) - 1)]
    killed = lo <= 0
    cn = [r["corr_pred_conf_vs_need"] for r in per_novel if r["corr_pred_conf_vs_need"] is not None]
    cr = [r["corr_pred_vs_real_conf"] for r in per_novel if r["corr_pred_vs_real_conf"] is not None]
    summary = {
        "novels": len(per_novel), "errors_in_cast": sum(r["errors"] for r in per_novel),
        "mean_rel_hypervolume_gain_aware_vs_blind": round(float(np.mean(gains)), 5) if gains else None,
        "ci_novel_bootstrap": [round(lo, 5), round(hi, 5)],
        "novels_aware_better": sum(g > 1e-9 for g in gains),
        "novels_blind_better": sum(g < -1e-9 for g in gains),
        "mean_corr_predicted_confusion_vs_need": round(float(np.mean(cn)), 4) if cn else None,
        "mean_corr_predicted_vs_real_confusion": round(float(np.mean(cr)), 4) if cr else None,
        "per_novel": [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()}
                      for r in per_novel],
    }
    hint = ("KILL" if killed else "SURVIVES") + (
        f": aware-vs-blind hypervolume gain {summary['mean_rel_hypervolume_gain_aware_vs_blind']} "
        f"CI {summary['ci_novel_bootstrap']}; corr(predicted confusion, need) "
        f"{summary['mean_corr_predicted_confusion_vs_need']}")
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="confusion_casting",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len(per_novel), n_trials=len(trials), summary=summary,
                      verdict_hint=hint,
                      notes=["need and addressee features use PDNC gold speakers; a product "
                             "version would estimate them from predicted speakers",
                             "salience proxy = speaker-embedding cosine distance (not perception)"]),
            trials, inputs)
