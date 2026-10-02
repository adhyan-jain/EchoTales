"""H-CAL: are the attribution ladder's confidence constants usable as a
posterior, on independent human gold?

Every confidence-conditioned decision the arena studies (commitment-calibrated
rendering, salience-aware review queues) needs an upstream confidence that
*ranks* errors. The product's tiers emit constants (0.95 explicit, 0.75
proximal, ...) that were never measured against labels. This experiment is
the precondition test: if accuracy is not ordered by confidence, any policy
built on it is building on noise.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from echotales.research import stats
from echotales.research.config import ExperimentConfig
from echotales.research.datasets import pdnc
from echotales.research.schema import RunResult, Trial
from echotales.research.transforms.attribution_probe import probe

HYPOTHESIS_ID = "H-CAL"
DEFAULT_PARAMS = {"novels": "all", "max_quotes_per_novel": 0}


def _auroc(scores: list[float], labels: list[bool]) -> float:
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def run(cfg: ExperimentConfig, *, stub: bool):
    if stub:
        novels = [pdnc.synthetic_novel(seed=cfg.base_seed)]
        inputs = {}
    else:
        names = pdnc.available()
        if cfg.params.get("novels") not in (None, "all"):
            names = [n for n in names if n in set(cfg.params["novels"])]
        if not names:
            raise SystemExit("PDNC not found under data/cache/research/pdnc -- see pdnc.py")
        novels = [pdnc.load_novel(n) for n in names]
        inputs = {"pdnc_root": pdnc.PDNC_ROOT}
    cap = int(cfg.params.get("max_quotes_per_novel", 0))

    results = []
    per_novel = {}
    for nv in novels:
        qs = nv.quotes[:cap] if cap else nv.quotes
        r = probe(nv, qs)
        results.extend((nv.name, x) for x in r)
        res = [x for x in r if x.resolved]
        per_novel[nv.name] = {"quotes": len(r), "resolved": len(res),
                              "correct": sum(x.correct for x in res)}

    trials = [Trial(unit_id=f"{n}:{x.quote_id}", condition=x.method, seed=0,
                    outputs={"gold": x.gold, "pred": x.predicted, "raw": x.predicted_raw,
                             "owners": list(x.owners), "lenient": x.correct_lenient,
                             "type": x.quote_type, "addressee_capture": x.addressee_capture},
                    metrics={"confidence": x.confidence, "correct": float(x.correct)})
              for n, x in results]

    allr = [x for _, x in results]
    resolved = [x for x in allr if x.resolved]
    by_tier: dict[str, list] = defaultdict(list)
    for x in resolved:
        by_tier[x.method].append(x)
    tiers = {}
    for m, xs in sorted(by_tier.items()):
        k = sum(x.correct for x in xs)
        p, lo, hi = stats.wilson(k, len(xs))
        kl = sum(x.correct_lenient for x in xs)
        tiers[m] = {"n": len(xs), "confidence": xs[0].confidence, "accuracy": round(p, 4),
                    "accuracy_lenient": round(kl / len(xs), 4),
                    "wilson_lo": round(lo, 4), "wilson_hi": round(hi, 4)}
    by_type = {}
    for t, xs in sorted(Counter(x.quote_type for x in allr).items()):
        sub = [x for x in allr if x.quote_type == t]
        rs = [x for x in sub if x.resolved]
        by_type[t] = {"n": len(sub), "coverage": round(len(rs) / len(sub), 4),
                      "accuracy_resolved": round(sum(x.correct for x in rs) / len(rs), 4) if rs else None}
    ece, table = stats.expected_calibration_error(
        [x.confidence for x in resolved], [x.correct for x in resolved])
    wrong = [x for x in resolved if not x.correct_lenient]
    gender_known = [x for x in wrong if x.gender_gold in ("M", "F") and x.gender_pred in ("M", "F")]
    auroc = _auroc([x.confidence for x in resolved], [x.correct for x in resolved])
    ordered = [tiers[m]["accuracy"] for m in sorted(tiers, key=lambda m: -tiers[m]["confidence"])
               if tiers[m]["n"] >= 30]
    monotone = all(a >= b - 1e-9 for a, b in zip(ordered, ordered[1:]))

    summary = {
        "novels": len(novels), "quotes": len(allr),
        "coverage": round(len(resolved) / len(allr), 4) if allr else 0.0,
        "accuracy_resolved": round(sum(x.correct for x in resolved) / len(resolved), 4) if resolved else 0.0,
        "ece": round(ece, 4), "auroc_confidence_vs_correct": round(auroc, 4),
        "tiers": tiers, "by_quote_type": by_type, "reliability": table,
        "accuracy_resolved_lenient": round(sum(x.correct_lenient for x in resolved) / len(resolved), 4) if resolved else 0.0,
        "auroc_lenient": round(_auroc([x.confidence for x in resolved], [x.correct_lenient for x in resolved]), 4),
        "unmapped_surface_share": round(sum(not x.owners for x in resolved) / len(resolved), 4) if resolved else 0.0,
        "errors_lenient": len(wrong),
        "vocative": {
            flag: {"n": len(xs), "accuracy_lenient": round(sum(x.correct_lenient for x in xs) / len(xs), 4)}
            for flag, xs in (("predicted_in_quote", [x for x in resolved if x.predicted_in_quote]),
                             ("not_in_quote", [x for x in resolved if not x.predicted_in_quote]))
            if xs
        },
        "addressee_capture_share_of_errors": round(sum(x.addressee_capture for x in wrong) / len(wrong), 4) if wrong else 0.0,
        "gender_mismatch_share_of_errors": round(sum(x.gender_gold != x.gender_pred for x in gender_known) / len(gender_known), 4) if gender_known else None,
        "tier_accuracy_monotone_in_confidence": monotone,
        "per_novel": per_novel,
    }
    if auroc != auroc:  # nan
        hint = "UNDECIDED: no errors or no correct resolutions"
    elif monotone and auroc >= 0.6:
        hint = "SURVIVES: confidence ranks errors (monotone tiers, AUROC>=0.6)"
    else:
        hint = "KILL-SIGNAL: confidence does not rank errors -- a policy needs a new posterior"
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="attribution_calibration",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len(allr), n_trials=len(trials), summary=summary,
                      verdict_hint=hint,
                      notes=["tier 4 (LLM) excluded by design; see module docstring"]),
            trials, inputs)
