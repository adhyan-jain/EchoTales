"""H-ACT image arm (convergence pass C3): re-read H-VRUNG as an action
counterfactual. CPU only, from saved probe outputs; no new renders.

H-VRUNG rendered every beat at a fixed seed under five framings ("rungs")
with the attribute in the prompt. The renderer cannot tell a correct
upstream attribute from a wrong one, so the rate at which a probe recovers
the *prompted* attribute under rung a is exactly the rate at which an
upstream attribute error would manifest under a. The question is the audio
arm's: does the action, with the upstream value fixed, change how often the
value (right or wrong) shows -- and does it mask the attributes differently?

Limits carried from H-VRUNG: 20 beats; attribute probes (llava forced choice,
CLIP zero-shot), not identity; hiding rungs often draw no visible person,
so "masked" partly means "nobody drawn".
"""

from __future__ import annotations

import json
import random

from echotales.research.config import ExperimentConfig
from echotales.research.experiments.gate_xdis import ROOT
from echotales.research.schema import RunResult, Trial
from echotales.research.stats import wilson

HYPOTHESIS_ID = "H-ACT"
DEFAULT_PARAMS = {"source_run": "data/eval/research/H-VRUNG/real-a89a29764cb7eea2"}
RUNGS = ("committed", "back_view", "silhouette", "distant", "crop")


def _rows(p, stub, seed):
    if not stub:
        src = ROOT / p["source_run"] / "trials.jsonl"
        return [json.loads(x) for x in src.read_text().splitlines() if x.strip()], {"source_trials": src}
    rng = random.Random(seed)
    rows = []
    for i in range(20):
        g, h = "FM"[i % 2], ("black", "blonde")[(i // 2) % 2]
        for var in ("in", "free"):
            for rung in RUNGS:
                ok = rng.random() < (0.9 if rung == "committed" else 0.6)
                gg = g if ok else ("M" if g == "F" else "F")
                hh = h if ok else ("blonde" if h == "black" else "black")
                rows.append({"unit_id": f"b{i:02d}", "condition": f"{var}|{rung}",
                             "metrics": {f"clip_gender_{gg}": 0.8, f"clip_gender_{'M' if gg == 'F' else 'F'}": 0.2,
                                         f"clip_hair_{hh}": 0.7,
                                         f"clip_hair_{'blonde' if hh == 'black' else 'black'}": 0.3},
                             "outputs": {"llava": {"gender": gg, "hair": hh, "person": ok}}})
    return rows, {}


def run(cfg: ExperimentConfig, *, stub: bool):
    from echotales.research.datasets import visual_beats as vb

    rows, inputs = _rows(cfg.params, stub, cfg.base_seed)
    spec = {s.beat_id: s for s in vb.specs(20)}
    cells, trials = {}, []
    for var in ("in", "free"):
        for rung in RUNGS:
            rs = [r for r in rows if r["condition"] == f"{var}|{rung}"]
            if not rs:
                continue
            cell = {"n": len(rs)}
            for attr, labels in (("gender", ("F", "M")), ("hair", ("black", "blonde"))):
                want = [getattr(spec[r["unit_id"]], attr) for r in rs]
                clip = [max(labels, key=lambda lb: r["metrics"].get(f"clip_{attr}_{lb}", 0.0)) for r in rs]
                lv = [r["outputs"]["llava"].get(attr) for r in rs]
                k_clip = sum(c == w for c, w in zip(clip, want))
                k_llava = sum(x == w for x, w in zip(lv, want))
                # Decisive = the probe committed to *some* value at >= 0.8:
                # what the "free" variant's default commitment is measured by.
                dec = sum(max(r["metrics"].get(f"clip_{attr}_{lb}", 0.0) for lb in labels) >= 0.8 for r in rs)
                maj = max(labels, key=lambda lb: sum(c == lb for c in clip))
                cell[attr] = {
                    "clip_recovery": [round(x, 4) for x in wilson(k_clip, len(rs))],
                    "llava_recovery": [round(x, 4) for x in wilson(k_llava, len(rs))],
                    "llava_answered": round(sum(x is not None for x in lv) / len(rs), 4),
                    "clip_decisive": round(dec / len(rs), 4),
                    "clip_majority": [maj, round(sum(c == maj for c in clip) / len(rs), 4)],
                }
            cell["person_visible_llava"] = round(sum(bool(r["outputs"]["llava"].get("person")) for r in rs)
                                                 / len(rs), 4)
            cells[f"{var}|{rung}"] = cell
            trials.append(Trial(unit_id=f"{var}|{rung}", condition=var, seed=0, outputs={},
                                metrics={"gender_clip": cell["gender"]["clip_recovery"][0],
                                         "hair_clip": cell["hair"]["clip_recovery"][0]}))
    # Manifestation of a (possibly wrong) prompted attribute, committed vs each
    # hiding rung: positive = the rung shows the upstream value less often.
    masking = {}
    base = cells.get("in|committed")
    for rung in RUNGS[1:]:
        c = cells.get(f"in|{rung}")
        if base and c:
            masking[rung] = {a: round(base[a]["clip_recovery"][0] - c[a]["clip_recovery"][0], 4)
                             for a in ("gender", "hair")}
    diverge = [r for r, m in masking.items() if (m["gender"] > 0.15) != (m["hair"] > 0.15)]
    summary = {"cells": cells, "masking_vs_committed_clip": masking,
               "rungs_masking_one_attribute_not_other": diverge}
    hint = (f"image arm: committed shows the prompted gender/hair at "
            f"{base['gender']['clip_recovery'][0] if base else None}/{base['hair']['clip_recovery'][0] if base else None}"
            f" (CLIP); attribute-selective rungs: {diverge}")
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="vrung_manifestation",
                      mode="stub" if stub else "real", config_hash=cfg.hash, n_units=len(rows),
                      n_trials=len(trials), summary=summary, verdict_hint=hint,
                      notes=["reanalysis of H-VRUNG saved probes; no new renders",
                             "prompted attribute stands in for a possibly-wrong upstream value",
                             "attribute probes, not identity; person visibility confounds hiding rungs"]),
            trials, inputs)
