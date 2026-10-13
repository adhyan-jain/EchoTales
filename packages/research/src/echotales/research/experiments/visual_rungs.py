"""H-VRUNG: can the product's image engine render a figure *without
committing* to its attributes?

The visual twin of H-HEDGE. Visual abstention (C22/H-VABST: a silhouette
instead of a committed figure when the attributes are uncertain) presupposes
the engine can withhold. Two variants per rung, at fixed seeds on NoobAI-XL
with prompts from the product's own `build_image_prompt`:

- ``in``: the attribute stays in the prompt and the rung's framing is meant
  to hide it. Pre-registered kill: a withholding rung lets automatic probes
  recover the intended gender AND hair at > 70% (chance 50%), or the
  committed rung recovers either below 80%.
- ``free``: the attribute is dropped -- the case the product actually has
  when it is unsure. Reported, not a kill condition: whether the engine then
  commits to a *default* anyway (IMPLICIT-Bench's "constrained neutrality"),
  measured as probe decisiveness and majority-class share.
"""

from __future__ import annotations

import numpy as np

from echotales.research.config import ExperimentConfig
from echotales.research.datasets import visual_beats as vb
from echotales.research.schema import RunResult, Trial

HYPOTHESIS_ID = "H-VRUNG"
DEFAULT_PARAMS = {"probe_version": 2, "n_specs": 20, "seed": 1234, "engine": "noobai-gpu", "steps": 35, "llava": True}
WITHHOLD = ("back_view", "silhouette", "distant", "crop")


def _fake_probe(st: vb.Stimulus) -> dict:
    """Stub: deterministic probe outputs shaped like the real ones."""
    hide = st.rung != "committed"
    flip = hide and int(st.key[:2], 16) % 2
    g = ("M" if st.spec.gender == "F" else "F") if flip else st.spec.gender
    other_h = "black" if st.spec.hair == "blonde" else "blonde"
    return {"clip": {"gender": {g: 0.7, ("M" if g == "F" else "F"): 0.3},
                     "hair": {st.spec.hair: 0.6, other_h: 0.4}},
            "llava": {"gender": None if hide else st.spec.gender, "hair": st.spec.hair, "person": True}}


def probe_all(stims, *, stub: bool, llava: bool) -> dict[str, dict]:
    if stub:
        return {s.key: _fake_probe(s) for s in stims}
    from echotales.research.evaluators import attribute_probe as ap

    out: dict[str, dict] = {}
    for s in stims:
        out.setdefault(s.key, {})["clip"] = ap.clip_attributes(s.path, vb.SETTINGS)
    ap.clip_release()
    if llava:
        for s in stims:
            out[s.key]["llava"] = ap.llava_attributes(s.path, vb.SETTINGS)
        ap.llava_unload()
    return out


def _round(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    return x


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    specs = vb.specs(int(p["n_specs"]) if not stub else 4)
    stims = [vb.build(sp, r, v, seed=int(p["seed"])) for sp in specs for r in vb.RUNGS
             for v in ("in", "free")]
    rendered = 0 if stub else vb.render_all(stims, engine_name=p["engine"], steps=int(p["steps"]))
    probes = probe_all(stims, stub=stub, llava=bool(p["llava"]))
    use_llava = bool(p["llava"])

    trials, table = [], {}
    for v in ("in", "free"):
        for r in vb.RUNGS:
            sel = [s for s in stims if s.rung == r and s.variant == v]
            row: dict = {"n": len(sel)}
            for attr in ("gender", "hair"):
                truth = [getattr(s.spec, attr) for s in sel]
                cl = [max(probes[s.key]["clip"][attr], key=probes[s.key]["clip"][attr].get) for s in sel]
                conf = [max(probes[s.key]["clip"][attr].values()) for s in sel]
                lv = [probes[s.key].get("llava", {}).get(attr) for s in sel]
                rec = {"clip_recovery": float(np.mean([a == t for a, t in zip(cl, truth)]))}
                if use_llava:
                    rec["llava_recovery"] = float(np.mean([a == t for a, t in zip(lv, truth)]))
                    rec["llava_unknown_rate"] = float(np.mean([a is None for a in lv]))
                rec["mean_recovery"] = float(np.mean([rec["clip_recovery"]]
                                                     + ([rec["llava_recovery"]] if use_llava else [])))
                rec["clip_decisiveness"] = float(np.mean(conf))
                maj = max(sorted(set(cl)), key=cl.count)
                rec["clip_majority_value"] = maj
                rec["clip_majority_share"] = cl.count(maj) / len(cl)
                row[attr] = rec
            if use_llava:
                row["person_visible_llava"] = float(np.mean([bool(probes[s.key]["llava"].get("person"))
                                                             for s in sel]))
            row["setting_kept_in_prompt"] = float(np.mean([s.kept["setting"] for s in sel]))
            table[f"{v}|{r}"] = row
            for s in sel:
                trials.append(Trial(unit_id=s.spec.beat_id, condition=f"{v}|{r}", seed=s.seed,
                                    outputs={"key": s.key, "prompt": s.prompt,
                                             "llava": probes[s.key].get("llava")},
                                    metrics={f"clip_{a}_{k}": round(val, 4) for a in ("gender", "hair")
                                             for k, val in probes[s.key]["clip"][a].items()}))
    committed = table["in|committed"]
    fail_commit = any(committed[a]["mean_recovery"] < 0.8 for a in ("gender", "hair"))
    leaks = [r for r in WITHHOLD
             if all(table[f"in|{r}"][a]["mean_recovery"] > 0.7 for a in ("gender", "hair"))]
    hiding = [r for r in WITHHOLD if r not in leaks]
    killed = fail_commit or not hiding
    hint = ("KILL" if killed else "SURVIVES") + (
        f": committed recovery gender {committed['gender']['mean_recovery']:.2f} hair "
        f"{committed['hair']['mean_recovery']:.2f}; leaking rungs {leaks}; hiding rungs {hiding}")
    summary = {"specs": len(specs), "images": len({s.key for s in stims}), "newly_rendered": rendered,
               "engine": p["engine"], "table": _round(table),
               "leaking_rungs": leaks, "hiding_rungs": hiding, "committed_fails": fail_commit}
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="visual_rungs",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len(specs), n_trials=len(trials), summary=summary, verdict_hint=hint,
                      notes=["recovery = automatic probes (CLIP-L zero-shot, llava:7b), not readers",
                             "as registered, a rung leaks only if BOTH gender and hair leak"]),
            trials, {})
