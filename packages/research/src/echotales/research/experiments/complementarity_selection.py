"""H-COMPL: is "illustrate where the audio is hard to follow" a distinct
notion of which moment to draw?

Cross-modal mutation of H-SELECT (C20): in an audiobook-plus-panels product
the picture's job may be to carry what the soundtrack cannot -- who is
talking when nothing says so, who has just walked in. `listener_ambiguity`
scores beats by untagged quotes and first-time names. The L1 question is
only whether that notion is *distinct* from the cheap ones H-SELECT already
compared (drama, dialogue density, visual lexicon) -- whether readers or
listeners value it is the later human study.

Pre-registered kill: top-k Jaccard with any existing non-random scorer
>= the random-vs-random floor + 0.15.
"""

from __future__ import annotations

import numpy as np

from echotales.research import stats
from echotales.research.baselines import moment_scorers as ms
from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.datasets import public_chapters
from echotales.research.schema import RunResult, Trial

HYPOTHESIS_ID = "H-COMPL"
DEFAULT_PARAMS = {"n_novels": 8, "chapters_per_novel": 2, "budget": 0.2}
OTHERS = ("product_drama", "dialogue_density", "visual_lexicon")


def _topk(scores, k):
    return set(sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k])


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    if stub:
        from echotales.research.datasets.pdnc import synthetic_novel

        txt = synthetic_novel(seed=cfg.base_seed, n_quotes=300).text
        chs = [public_chapters.beats(txt[:30000], "synthetic", 0)]
        inputs = {}
    else:
        from echotales.research.datasets.pdnc import PDNC_ROOT

        chs = public_chapters.sample(int(p["n_novels"]), int(p["chapters_per_novel"]))
        inputs = {"pdnc_root": PDNC_ROOT}
    jac: dict[str, list[float]] = {}
    trials = []
    for ch in chs:
        texts = [b.text for b in ch]
        seen: set[str] = set()
        sc = {"listener_ambiguity": [ms.listener_ambiguity(t, seen) for t in texts],
              "product_drama": [ms.product_drama(t) for t in texts],
              "dialogue_density": [ms.dialogue_density(t) for t in texts],
              "visual_lexicon": [ms.visual_lexicon(t) for t in texts],
              "random_a": ms.random_scores(len(texts), derive_seed(cfg.base_seed, ch[0].id, "a")),
              "random_b": ms.random_scores(len(texts), derive_seed(cfg.base_seed, ch[0].id, "b"))}
        k = max(1, round(float(p["budget"]) * len(texts)))
        tops = {n: _topk(v, k) for n, v in sc.items()}
        for o in (*OTHERS, "random_a"):
            jac.setdefault(o, []).append(len(tops["listener_ambiguity"] & tops[o])
                                         / len(tops["listener_ambiguity"] | tops[o]))
        jac.setdefault("random_floor", []).append(len(tops["random_a"] & tops["random_b"])
                                                  / len(tops["random_a"] | tops["random_b"]))
        for i, b in enumerate(ch):
            trials.append(Trial(unit_id=b.id, condition="scores", seed=0,
                                metrics={n: round(float(v[i]), 5) for n, v in sc.items()}))
    summary: dict = {"chapters": len(chs), "beats": len(trials), "budget": p["budget"], "jaccard": {}}
    for key, vals in sorted(jac.items()):
        iv = stats.bootstrap_ci(vals, lambda xs: float(np.mean(xs)), seed=cfg.base_seed)
        summary["jaccard"][key] = {"mean": round(iv.point, 4), "ci": [round(iv.low, 4), round(iv.high, 4)]}
    floor = summary["jaccard"]["random_floor"]["mean"]
    worst = max(OTHERS, key=lambda o: summary["jaccard"][o]["mean"])
    killed = summary["jaccard"][worst]["mean"] >= floor + 0.15
    hint = ("KILL" if killed else "SURVIVES") + (
        f": max Jaccard with an existing scorer {summary['jaccard'][worst]['mean']} ({worst}) "
        f"vs random floor {floor} (+0.15 threshold)")
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="complementarity_selection",
                      mode="stub" if stub else "real", config_hash=cfg.hash, n_units=len(trials),
                      n_trials=len(trials), summary=summary, verdict_hint=hint,
                      notes=["distinctness only; whether people value it needs the human study"]),
            trials, inputs)
