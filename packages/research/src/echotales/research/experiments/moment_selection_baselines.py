"""H-SELECT (precondition): do existing notions of "a moment worth drawing"
agree with each other?

The lead (visual G1) is that which k of N beats to illustrate should be
learned from reader preference. That is only worth a human study if the
cheap notions disagree -- if a drama heuristic, a visualness proxy and a
zero-shot LLM already pick the same beats, the selection problem is easy.
This measures pairwise top-k overlap (Jaccard) and rank correlation
(Kendall tau) between scorers per chapter, against the random-vs-random
floor. It cannot say which scorer is *right*: that needs the pairwise
annotation study (human_studies/moment_annotation.html).
"""

from __future__ import annotations

import itertools

import numpy as np
from scipy.stats import kendalltau

from echotales.research import stats
from echotales.research.baselines import moment_scorers as ms
from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.datasets import public_chapters
from echotales.research.schema import RunResult, Trial

HYPOTHESIS_ID = "H-SELECT"
DEFAULT_PARAMS = {"n_novels": 8, "chapters_per_novel": 2, "budget": 0.2, "llm": False}


def _topk(scores, k):
    return set(sorted(range(len(scores)), key=lambda i: -scores[i])[:k])


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    if stub:
        from echotales.research.datasets.pdnc import synthetic_novel
        txt = synthetic_novel(seed=cfg.base_seed, n_quotes=300).text
        chs = [public_chapters.beats(txt[:30000], "synthetic", 0)]
        inputs = {}
    else:
        chs = public_chapters.sample(int(p["n_novels"]), int(p["chapters_per_novel"]))
        from echotales.research.datasets.pdnc import PDNC_ROOT
        inputs = {"pdnc_root": PDNC_ROOT}
    names = ["product_drama", "dialogue_density", "visual_lexicon", "random_a", "random_b"]
    if p["llm"] and not stub:
        names.insert(3, "llm_zero_shot")
    per_pair: dict[str, list[float]] = {}
    per_tau: dict[str, list[float]] = {}
    trials = []
    for ch in chs:
        texts = [b.text for b in ch]
        sc = {
            "product_drama": [ms.product_drama(t) for t in texts],
            "dialogue_density": [ms.dialogue_density(t) for t in texts],
            "visual_lexicon": [ms.visual_lexicon(t) for t in texts],
            "random_a": ms.random_scores(len(texts), derive_seed(cfg.base_seed, ch[0].id, "a")),
            "random_b": ms.random_scores(len(texts), derive_seed(cfg.base_seed, ch[0].id, "b")),
        }
        if "llm_zero_shot" in names:
            sc["llm_zero_shot"] = ms.llm_zero_shot(texts)
        k = max(1, round(float(p["budget"]) * len(texts)))
        tops = {n: _topk(sc[n], k) for n in names}
        for a, b in itertools.combinations(names, 2):
            key = f"{a}~{b}"
            per_pair.setdefault(key, []).append(len(tops[a] & tops[b]) / len(tops[a] | tops[b]))
            tau = kendalltau(sc[a], sc[b]).statistic
            per_tau.setdefault(key, []).append(0.0 if tau != tau else float(tau))
        for b, i in zip(ch, range(len(ch))):
            trials.append(Trial(unit_id=b.id, condition="scores", seed=0,
                                metrics={n: round(float(sc[n][i]), 5) for n in names}))
    summary = {"chapters": len(chs), "beats": len(trials), "budget": p["budget"], "pairs": {}}
    for key, vals in sorted(per_pair.items()):
        iv = stats.bootstrap_ci(vals, lambda xs: float(np.mean(xs)), seed=cfg.base_seed)
        summary["pairs"][key] = {"jaccard_topk": round(iv.point, 4),
                                 "ci": [round(iv.low, 4), round(iv.high, 4)],
                                 "kendall_tau": round(float(np.mean(per_tau[key])), 4)}
    floor = summary["pairs"].get("random_a~random_b", {}).get("jaccard_topk", 0.0)
    real = {k: v["jaccard_topk"] for k, v in summary["pairs"].items() if "random" not in k}
    summary["random_floor_jaccard"] = floor
    summary["max_non_random_jaccard"] = max(real.values()) if real else None
    hint = ("scorers DISAGREE (all non-random pairs within 0.15 of the random floor): selection is "
            "not settled by cheap notions -- the preference study is warranted"
            if real and max(real.values()) < floor + 0.15 else
            "some scorers AGREE substantially: check whether a human ceiling is already reached")
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="moment_selection_baselines",
                      mode="stub" if stub else "real", config_hash=cfg.hash, n_units=len(trials),
                      n_trials=len(trials), summary=summary, verdict_hint="PRECONDITION: " + hint),
            trials, inputs)
