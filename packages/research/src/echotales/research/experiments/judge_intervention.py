"""H-JUDGE-V: where is an upstream error lost, and do judges see the rest?

One attribute error (gender, hair colour, or setting) is injected *upstream*
of the product's prompt assembly (`build_image_prompt` via
`datasets/visual_beats.py`), rendered at the same seed as the correct panel
(common random numbers), and traced through three stages:

1. **survives** -- the wrong clause is still in the prompt after the CLIP
   budget (`fit_tiers_to_budget`);
2. **rendered** -- both attribute probes (CLIP zero-shot and llava, which do
   not share weights) see the wrong value in the image;
3. **detected** -- a holistic judge (CLIPScore, llava 1-10 match) scores the
   intervened panel below the correct one against the intended description.

Pre-registered kill: conditional on (1) and (2), every judge reaches
detection AUROC > 0.9 (no validity gap); or P(rendered | survives) > 0.9 for
every error type (all loss is truncation -- which would re-kill T3).
"""

from __future__ import annotations

import numpy as np

from echotales.research.config import ExperimentConfig
from echotales.research.datasets import visual_beats as vb
from echotales.research.schema import RunResult, Trial

HYPOTHESIS_ID = "H-JUDGE-V"
DEFAULT_PARAMS = {"probe_version": 2, "n_specs": 20, "seed": 1234, "engine": "noobai-gpu", "steps": 35}
ERRORS = ("gender", "hair", "setting")
JUDGES = ("clipscore", "llava_match")


def _wrong(spec: vb.Spec, etype: str) -> dict:
    if etype == "gender":
        return {"gender": "M" if spec.gender == "F" else "F"}
    if etype == "hair":
        return {"hair": "black" if spec.hair == "blonde" else "blonde"}
    i = vb.SETTINGS.index(spec.setting)
    return {"setting": vb.SETTINGS[(i + 5) % len(vb.SETTINGS)]}


def _clause_kept(st: vb.Stimulus, etype: str) -> bool:
    return st.kept[{"gender": "cast", "hair": "character", "setting": "setting"}[etype]]


def _auc(pairs) -> float | None:
    """Paired AUROC: P(judge scores the correct panel above the intervened
    one), ties count 1/2."""
    if not pairs:
        return None
    return float(np.mean([1.0 if a > b else 0.5 if a == b else 0.0 for a, b in pairs]))


def _round(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    return x


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    specs = vb.specs(int(p["n_specs"]) if not stub else 4)
    seed = int(p["seed"])
    base = {sp.beat_id: vb.build(sp, "committed", "in", seed=seed) for sp in specs}
    wrong = {(sp.beat_id, e): vb.build(sp, "committed", f"error:{e}", seed=seed, **_wrong(sp, e))
             for sp in specs for e in ERRORS}
    stims = list(base.values()) + list(wrong.values())
    newly = 0 if stub else vb.render_all(stims, engine_name=p["engine"], steps=int(p["steps"]))

    if stub:
        attrs = {s.key: {pr: {"gender": s.spec.gender, "hair": s.spec.hair, "setting": s.spec.setting}
                         for pr in ("clip", "llava")} for s in stims}
        judge = {s.key: {"clipscore": (int(s.key[:4], 16) % 100) / 100,
                         "llava_match": float(int(s.key[4:6], 16) % 10)} for s in stims}
    else:
        from echotales.research.evaluators import attribute_probe as ap

        attrs, judge = {}, {}
        for s in stims:
            c = ap.clip_attributes(s.path, vb.SETTINGS)
            attrs[s.key] = {"clip": {a: max(c[a], key=c[a].get) for a in ("gender", "hair", "setting")}}
            judge[s.key] = {"clipscore": ap.clip_score(s.path, vb.description(s.spec))}
        ap.clip_release()
        for s in stims:
            attrs[s.key]["llava"] = ap.llava_attributes(s.path, vb.SETTINGS)
            judge[s.key]["llava_match"] = ap.llava_match(s.path, vb.description(s.spec))
        ap.llava_unload()

    rows, trials = [], []
    for sp in specs:
        b = base[sp.beat_id]
        for e in ERRORS:
            w = wrong[(sp.beat_id, e)]
            target = _wrong(sp, e)[e]
            survived = _clause_kept(w, e)
            seen = [attrs[w.key][pr].get(e) == target for pr in ("clip", "llava")]
            base_ok = all(attrs[b.key][pr].get(e) == getattr(sp, e) for pr in ("clip", "llava"))
            row = {"beat": sp.beat_id, "error": e, "survived": survived,
                   "rendered": survived and all(seen), "rendered_any_probe": survived and any(seen),
                   "base_compliant": base_ok,
                   **{f"{j}_pair": (judge[b.key][j], judge[w.key][j]) for j in JUDGES}}
            rows.append(row)
            trials.append(Trial(unit_id=sp.beat_id, condition=e, seed=seed,
                                outputs={"survived": survived, "rendered": row["rendered"],
                                         "base_compliant": base_ok, "wrong_prompt": w.prompt},
                                metrics={f"{j}_{k}": round(float(v), 4) for j in JUDGES
                                         for k, v in zip(("base", "wrong"), row[f"{j}_pair"])}))

    by_type = {}
    for e in ERRORS:
        r = [x for x in rows if x["error"] == e]
        surv = [x for x in r if x["survived"]]
        rend = [x for x in surv if x["rendered"]]
        by_type[e] = {
            "n": len(r), "p_survives": len(surv) / len(r),
            "p_rendered_given_survives": len(rend) / len(surv) if surv else None,
            "p_rendered_any_probe_given_survives": (sum(x["rendered_any_probe"] for x in surv) / len(surv)
                                                    if surv else None),
            "base_compliance": float(np.mean([x["base_compliant"] for x in r])),
            "judge_auc_all": {j: _auc([x[f"{j}_pair"] for x in r]) for j in JUDGES},
            "judge_auc_given_rendered": {j: _auc([x[f"{j}_pair"] for x in rend]) for j in JUDGES},
            "n_rendered": len(rend),
        }
    rend_all = [x for x in rows if x["rendered"]]
    pooled = {j: _auc([x[f"{j}_pair"] for x in rend_all]) for j in JUDGES}
    no_gap = all(v is not None and v > 0.9 for v in pooled.values())
    all_trunc = all(v["p_rendered_given_survives"] is not None and v["p_rendered_given_survives"] > 0.9
                    for v in by_type.values())
    killed = no_gap or all_trunc
    hint = ("KILL" if killed else "SURVIVES") + (
        f": pooled judge AUROC given rendered {_round(pooled)}; P(rendered|survives) "
        f"{ {e: _round(v['p_rendered_given_survives']) for e, v in by_type.items()} }")
    summary = {"specs": len(specs), "images": len({s.key for s in stims}), "newly_rendered": newly,
               "by_type": _round(by_type), "pooled_judge_auc_given_rendered": _round(pooled),
               "n_rendered_errors": len(rend_all), "no_validity_gap": no_gap,
               "all_loss_is_truncation": all_trunc}
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="judge_intervention",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len(specs), n_trials=len(trials), summary=summary, verdict_hint=hint,
                      notes=["'rendered' needs both probes to agree; 'rendered_any_probe' is the "
                             "lenient alternative", "judges score against the intended description"]),
            trials, {})
