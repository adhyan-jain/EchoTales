"""H-GATE: can the confidence the pipeline actually has drive a commitment
policy, and how much does voice distinctiveness change what an error costs?

Two questions the perceptual study (H-COST) presupposes, answerable without
listeners:

1. **Masking (objective precondition).** Under a homogeneous vs a diverse
   cast, what share of real attribution errors land on an acoustically
   different voice, and how far away? If errors are already masked under the
   diverse bank (wrong voice ~ right voice in embedding space), the
   distinctiveness x accuracy crossover has no room to exist.
2. **Gating (policy precondition).** Abstaining to the narrator below a
   confidence threshold trades correct character voicing for fewer salient
   errors. Is that trade better with the pipeline's confidence than with a
   random threshold? Reported as risk-coverage curves and AURC with a paired
   bootstrap over lines, against random and oracle orderings.

Errors are the product ladder's real errors on PDNC human gold (the
`attribution_probe`), not injected ones -- injection is H-COST's job.
"""

from __future__ import annotations

import random

import numpy as np

from echotales.research import stats
from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.controllers.casting import cast, mean_pairwise_distance
from echotales.research.datasets import pdnc
from echotales.research.evaluators.voice_geometry import ears_geometry, synthetic_geometry
from echotales.research.schema import RunResult, Trial
from echotales.research.transforms.attribution_probe import probe

HYPOTHESIS_ID = "H-GATE"
DEFAULT_PARAMS = {"modes": ["homogeneous", "diverse"], "vocative_penalty": 0.5,
                  "resamples": 1000}


def _lines(novels, geom, mode, seed):
    rows = []
    for nv in novels:
        res = [r for r in probe(nv) if r.resolved and r.owners]
        counts: dict[str, int] = {}
        for q in nv.quotes:
            counts[q.speaker] = counts.get(q.speaker, 0) + 1
        chars = sorted(nv.characters.values(), key=lambda c: -counts.get(c.name, 0))
        assign = cast([(c.name, c.gender) for c in chars], geom, mode=mode,
                      seed=derive_seed(seed, nv.name, mode))
        for r in res:
            pred = r.predicted or r.owners[0]
            vg, vp = assign.get(r.gold), assign.get(pred)
            if vg is None or vp is None:
                continue
            d = geom.distance(vg, vp)
            rows.append({
                "unit": f"{nv.name}:{r.quote_id}", "conf": r.confidence,
                "vocative": r.predicted_in_quote, "correct_id": r.correct_lenient,
                # A wrong attribution onto the same voice is acoustically
                # invisible -- the masking the hypothesis is about.
                "same_voice": vg == vp, "dist": d,
                "gender_flip": geom.gender(vg) != geom.gender(vp),
            })
        rows_mpd = mean_pairwise_distance(assign, geom)
        for row in rows[-len(res):]:
            row.setdefault("cast_spread", rows_mpd)
    return rows


def _curve(rows, score):
    """Commit (character voice) to the top-k lines by score, narrator for the rest.
    Returns coverage grid with salient-error mass and correct-voicing rate."""
    order = sorted(range(len(rows)), key=lambda i: -score[i])
    n = len(rows)
    err = np.array([0.0 if rows[i]["correct_id"] else rows[i]["dist"] for i in order])
    good = np.array([1.0 if rows[i]["correct_id"] else 0.0 for i in order])
    cum_err, cum_good = np.cumsum(err) / n, np.cumsum(good) / n
    return cum_err, cum_good


def _aurc(rows, score):
    cum_err, _ = _curve(rows, score)
    return float(np.mean(cum_err))


def run(cfg: ExperimentConfig, *, stub: bool):
    if stub:
        novels = [pdnc.synthetic_novel(seed=cfg.base_seed)]
        geom = synthetic_geometry(seed=cfg.base_seed)
        inputs = {}
    else:
        novels = [pdnc.load_novel(n) for n in pdnc.available()]
        geom = ears_geometry()
        inputs = {"pdnc_root": pdnc.PDNC_ROOT}
    pen = float(cfg.params["vocative_penalty"])
    summary: dict = {"bank_voices": len(geom.ids)}
    trials: list[Trial] = []
    hints = []
    for mode in cfg.params["modes"]:
        rows = _lines(novels, geom, mode, cfg.base_seed)
        if not rows:
            continue
        wrong = [r for r in rows if not r["correct_id"]]
        rng = random.Random(derive_seed(cfg.base_seed, "random-order", mode))
        scores = {
            "tier_confidence": [r["conf"] for r in rows],
            "tier_plus_vocative": [r["conf"] - (pen if r["vocative"] else 0.0) for r in rows],
            "oracle": [1.0 if r["correct_id"] else 0.0 for r in rows],
            "random": [rng.random() for _ in rows],
        }
        aurc = {k: round(_aurc(rows, s), 5) for k, s in scores.items()}
        idx = list(range(len(rows)))

        def stat_for(key):
            return lambda sample: _aurc([rows[i] for i in sample], [scores[key][i] for i in sample])

        cmp = stats.paired_bootstrap(idx, stat_for("tier_confidence"), stat_for("random"),
                                     resamples=int(cfg.params["resamples"]), seed=cfg.base_seed)
        summary[mode] = {
            "lines": len(rows), "errors": len(wrong),
            "error_rate": round(len(wrong) / len(rows), 4),
            "masked_errors_same_voice": round(sum(r["same_voice"] for r in wrong) / len(wrong), 4) if wrong else None,
            "mean_error_distance": round(float(np.mean([r["dist"] for r in wrong])), 4) if wrong else None,
            "gender_flip_errors": round(sum(r["gender_flip"] for r in wrong) / len(wrong), 4) if wrong else None,
            "aurc_salient_error": aurc,
            # positive delta = random is worse (higher area) than tier confidence
            "tier_vs_random": {"delta_random_minus_tier": round(cmp.delta, 5),
                               "ci": [round(cmp.low, 5), round(cmp.high, 5)],
                               "p_random_not_worse": round(cmp.p_value, 4)},
            "gap_closed_vs_oracle": round((aurc["random"] - aurc["tier_confidence"]) /
                                          (aurc["random"] - aurc["oracle"]), 4)
            if aurc["random"] != aurc["oracle"] else None,
        }
        sig = cmp.low > 0
        hints.append(f"{mode}: tier {'beats' if sig else 'does not beat'} random "
                     f"(closes {summary[mode]['gap_closed_vs_oracle']} of the random-oracle gap)")
        for r in rows:
            trials.append(Trial(unit_id=r["unit"], condition=mode, seed=0,
                                outputs={"correct_id": r["correct_id"], "same_voice": r["same_voice"],
                                         "gender_flip": r["gender_flip"], "vocative": r["vocative"]},
                                metrics={"conf": r["conf"], "dist": round(r["dist"], 5)}))
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="commitment_gating",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len({t.unit_id for t in trials}), n_trials=len(trials),
                      summary=summary, verdict_hint="; ".join(hints),
                      notes=["salience proxy = speaker-embedding cosine distance (Chatterbox VE); "
                             "not a perceptual measure -- see voice_geometry.py"]),
            trials, inputs)
