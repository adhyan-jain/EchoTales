"""H-COST: build the stimulus set for the perceptual error-cost study.

The study the lead stands or falls on (DECISION_LOG.md, the decisive
experiment): does the cost listeners pay for a misattributed line depend on
how the line is rendered -- on voice distinctiveness and on whether the
renderer committed to a character voice at all -- such that full-cast
rendering stops beating a single narrator below some attribution accuracy?

This module produces everything except the listeners:

- passages from PDNC (public-domain text, human speaker/addressee gold),
  chosen to be dialogue-dense with a mixed-gender cast;
- a factorial of conditions (error rate x error type x cast distinctiveness x
  rendering policy), each a deterministic *script* (segment -> voice);
- comprehension probes ("who said ...?") on implicit quotes, where the voice
  is the only cue, so the probe measures what a wrong voice costs;
- optionally the audio (`synthesize=true`, local Chatterbox).

Scripts are regenerated from code, not shipped (PDNC licence: see pdnc.py).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from echotales.pipeline.paths import RESEARCH_SCRATCH_DIR
from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.controllers.casting import cast
from echotales.research.datasets import pdnc
from echotales.research.evaluators.voice_geometry import ears_geometry, synthetic_geometry
from echotales.research.schema import RunResult, Trial
from echotales.research.transforms.error_injection import inject

HYPOTHESIS_ID = "H-COST"
DEFAULT_PARAMS = {
    "n_passages": 12,
    "quotes_per_passage": [6, 10],
    "max_chars": 2200,
    "rates": [0.0, 0.15, 0.35],
    "error_types": ["addressee", "cross_gender", "same_gender"],
    "casts": ["homogeneous", "diverse"],
    "policies": ["full_cast", "narrator_only"],
    "narrator_voice": "auto",
    "synthesize": False,
    "out_dir": "",
    # v2 (mutation lab, 2026-10-02). Defaults keep v1 behaviour.
    # min_per_gender=2 fixes same-gender errors realising at half the
    # requested rate (one speaker per gender in many v1 passages);
    # placements ["tagged", "implicit"] is the H-IOL P2 factor (an error on a
    # line the text names vs one the voice alone carries); iol_predict writes
    # the listener model's predicted probe accuracy for every exact script,
    # so the listening study tests numbers stated in advance.
    "min_per_gender": 1,
    "placements": ["any"],
    "iol_predict": False,
}


def _passages(novel: pdnc.Novel, lo: int, hi: int, max_chars: int, rng: random.Random,
              min_per_gender: int = 1):
    qs = [q for q in novel.quotes if q.start >= 0 and q.speaker.lower() not in ("unknowable", "")]
    cands = []
    for i in range(len(qs) - lo):
        for n in range(hi, lo - 1, -1):
            win = qs[i:i + n]
            if len(win) < lo or win[-1].end - win[0].start > max_chars:
                continue
            spk = {q.speaker for q in win}
            genders = {novel.gender_of(s) for s in spk}
            implicit = [q for q in win if q.quote_type.lower() == "implicit"]
            cast_g = [novel.gender_of(c) for c in spk | {a for q in win for a in q.addressees
                                                          if a in novel.characters}]
            enough = min(cast_g.count("M"), cast_g.count("F")) >= min_per_gender
            if len(spk) >= 2 and {"M", "F"} <= genders and len(implicit) >= 2 and enough:
                cands.append(win)
                break
    rng.shuffle(cands)
    chosen, used = [], set()
    for win in cands:
        if any(q.id in used for q in win):
            continue
        chosen.append(win)
        used |= {q.id for q in win}
    return chosen


def _segments(novel: pdnc.Novel, win) -> list[dict]:
    segs, pos = [], win[0].start
    lead = novel.text.rfind("\n\n", 0, win[0].start)
    pos = lead + 2 if lead != -1 and win[0].start - lead < 400 else win[0].start
    for k, q in enumerate(win):
        if q.start > pos:
            narr = novel.text[pos:q.start].strip().strip("“”\"").strip()
            if narr:
                segs.append({"kind": "narration", "text": narr})
        segs.append({"kind": "quote", "text": q.text, "quote_index": k, "speaker": q.speaker,
                     "addressees": q.addressees, "type": q.quote_type})
        pos = q.end
    tail_end = novel.text.find("\n\n", pos)
    tail = novel.text[pos:tail_end if tail_end != -1 and tail_end - pos < 300 else pos].strip()
    tail = tail.strip("“”\"").strip()
    if tail:
        segs.append({"kind": "narration", "text": tail})
    return segs


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    rng = random.Random(derive_seed(cfg.base_seed, "passages"))
    if stub:
        novels = [pdnc.synthetic_novel(seed=cfg.base_seed, n_quotes=200)]
        geom = synthetic_geometry(seed=cfg.base_seed)
        inputs = {}
    else:
        novels = [pdnc.load_novel(n) for n in pdnc.available()]
        geom = ears_geometry()
        inputs = {"pdnc_root": pdnc.PDNC_ROOT}
    lo, hi = p["quotes_per_passage"]
    pool = []
    for nv in novels:
        for win in _passages(nv, lo, hi, int(p["max_chars"]), rng, int(p.get("min_per_gender", 1))):
            pool.append((nv, win))
    rng.shuffle(pool)
    chosen = pool[: int(p["n_passages"])]

    # Narrator: the bank voice nearest the overall centroid -- the least
    # distinctive voice, so "narrator_only" is the maximal-masking rung.
    centre = geom.emb.mean(axis=0)
    narrator = (p["narrator_voice"] if p["narrator_voice"] != "auto"
                else geom.ids[int((geom.emb @ centre).argmax())])

    out_dir = Path(p["out_dir"]) if p["out_dir"] else RESEARCH_SCRATCH_DIR / "error_cost_stimuli" / cfg.hash
    stimuli, trials, probes = [], [], []
    segs_by_passage = {}
    for pi, (nv, win) in enumerate(chosen):
        segs = _segments(nv, win)
        segs_by_passage[pi] = segs
        quotes = [s for s in segs if s["kind"] == "quote"]
        speakers = sorted({q["speaker"] for q in quotes} | {a for q in quotes for a in q["addressees"]
                                                          if a in nv.characters})
        genders = {s: nv.gender_of(s) for s in speakers}
        implicit = [q["quote_index"] for q in quotes if q["type"].lower() == "implicit"]
        pr = random.Random(derive_seed(cfg.base_seed, "probe", pi))
        probe_idx = sorted(pr.sample(implicit, min(2, len(implicit))))
        for qi in probe_idx:
            q = quotes[qi]
            probes.append({"passage": pi, "quote_index": qi, "excerpt": q["text"][:120],
                           "answer": q["speaker"], "options": speakers})
        for cast_mode in p["casts"]:
            assign = cast([(s, genders[s]) for s in speakers], geom, mode=cast_mode,
                          seed=derive_seed(cfg.base_seed, pi, cast_mode))
            tagged = {q["quote_index"] for q in quotes if q["type"].lower() != "implicit"}
            for rate in p["rates"]:
                for etype, place in ([(e, pl) for e in p["error_types"] for pl in p.get("placements", ["any"])]
                                     if rate > 0 else [("none", "any")]):
                    # Probed lines are never corrupted: a probe must ask
                    # about a line whose *neighbours* carry the errors, or
                    # it measures the injected label instead of tracking.
                    elig = {q["quote_index"] for q in quotes} - set(probe_idx)
                    if place == "tagged":
                        elig &= tagged
                    elif place == "implicit":
                        elig -= tagged
                    seed_keys = (pi, rate, etype) if place == "any" else (pi, rate, etype, place)
                    inj = [] if rate == 0 else inject(
                        quotes, genders, rate=rate, error_type=etype,
                        seed=derive_seed(cfg.base_seed, *seed_keys), eligible=elig)
                    swapped = {x.quote_index: x for x in inj}
                    for policy in p["policies"]:
                        sid = f"p{pi:02d}-{cast_mode}-r{int(rate * 100):02d}-{etype}-{policy}"
                        if place != "any":
                            sid += f"-{place}"
                        script = []
                        for s in segs:
                            if s["kind"] == "narration" or policy == "narrator_only":
                                v = narrator
                                rendered = None if s["kind"] == "narration" else "narrator"
                            else:
                                who = swapped[s["quote_index"]].rendered_as if s["quote_index"] in swapped else s["speaker"]
                                v, rendered = assign[who], who
                            script.append({**{k: s[k] for k in ("kind", "text")}, "voice": v,
                                           "rendered_as": rendered,
                                           "gold": s.get("speaker"),
                                           "injected": s.get("quote_index") in swapped and policy != "narrator_only"})
                        realised = sum(x["injected"] for x in script) / max(1, len(quotes))
                        st = {"id": sid, "passage": pi, "novel": nv.name, "cast": cast_mode,
                              "rate_requested": rate, "rate_realised": round(realised, 3),
                              "error_type": etype, "policy": policy, "script": script,
                              # Duration covariate (v1 design issue: narrator
                              # renders ran ~30% longer); measured audio
                              # length replaces it once synthesised.
                              "spoken_chars": sum(len(x["text"]) for x in script)}
                        if place != "any":
                            st["placement"] = place
                        stimuli.append(st)
                        trials.append(Trial(unit_id=f"p{pi:02d}", condition=sid, seed=0,
                                            outputs={"cast": cast_mode, "policy": policy, "error_type": etype},
                                            metrics={"rate_requested": rate, "rate_realised": realised}))
    iol = _iol_predictions(stimuli, probes, segs_by_passage, geom) if p.get("iol_predict") else None
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stimuli.json").write_text(json.dumps(
        {"narrator": narrator, "stimuli": stimuli, "probes": probes}, indent=1))
    synth_note = "scripts only"
    if p["synthesize"] and not stub:
        from echotales.research.human_studies.synthesize import synthesize_stimuli
        synth_note = synthesize_stimuli(out_dir / "stimuli.json", out_dir / "audio")
    by_cond = {}
    for st in stimuli:
        key = f"{st['cast']}|{st['policy']}|{st['error_type']}|{st['rate_requested']}"
        if "placement" in st:
            key += f"|{st['placement']}"
        by_cond.setdefault(key, []).append(st["rate_realised"])
    summary = {
        "passages": len(chosen), "stimuli": len(stimuli), "probes": len(probes),
        "narrator_voice": narrator, "out_dir": str(out_dir), "audio": synth_note,
        "realised_rate_by_condition": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_cond.items())},
    }
    if iol is not None:
        summary["iol_predicted_probe_accuracy"] = iol
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="error_cost_stimuli",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len(chosen), n_trials=len(trials), summary=summary,
                      verdict_hint="NOT A TEST: stimulus generation only; the decision needs listeners "
                                   "(human_studies/listening_study.html + analyze_listening.py)"),
            trials, inputs)


def _iol_predictions(stimuli, probes, segs_by_passage, geom) -> dict:
    """The H-IOL listener's predicted probe accuracy per condition, from the
    exact scripts listeners will hear (default listener parameters)."""
    import numpy as np

    from echotales.research.models.listener import Line, ListenerParams, simulate

    def dist(u, v):
        return 0.0 if u == v else geom.distance(u, v)

    probe_at = {}
    for pr in probes:
        probe_at.setdefault(pr["passage"], set()).add(pr["quote_index"])
    by_cond: dict[str, list[float]] = {}
    for st in stimuli:
        segs = segs_by_passage[st["passage"]]
        quotes = [s for s in segs if s["kind"] == "quote"]
        qscript = [x for x in st["script"] if x["kind"] == "quote"]
        cast = sorted({q["speaker"] for q in quotes})
        lines = [Line(speaker=q["speaker"], voice=x["voice"],
                      tag=q["type"].lower() if q["type"].lower() in ("explicit", "anaphoric") else "implicit")
                 for q, x in zip(quotes, qscript)]
        out = simulate(lines, cast, dist, ListenerParams())
        acc = [out[i].comprehension for i in sorted(probe_at.get(st["passage"], ()))]
        key = f"{st['cast']}|{st['policy']}|{st['error_type']}|{st['rate_requested']}|{st.get('placement', 'any')}"
        by_cond.setdefault(key, []).extend(acc)
    return {k: round(float(np.mean(v)), 4) for k, v in sorted(by_cond.items()) if v}
