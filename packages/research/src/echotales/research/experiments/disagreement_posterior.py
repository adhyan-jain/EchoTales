"""H-XDIS (product infrastructure): does disagreement between the product's
rule ladder and a local LLM attributor flag the ladder's errors?

H-CAL measured the ladder's tier constants at AUROC 0.59, and H-GATE showed
that caps any confidence-gated rendering policy at 16-18% of the oracle
gain. C28 (cross-modal disagreement) was parked for lack of labels; this is
its product-only mutation: two *independently derived* attributions of the
same line, scored on PDNC human gold. Pre-declared not to be a research
claim (committee disagreement is known: query-by-committee, ensembles).

Pre-registered kill: AUROC(disagreement, ladder error) < 0.7.
"""

from __future__ import annotations

import json
import random
import re
import urllib.request

import numpy as np

from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.datasets import pdnc
from echotales.research.schema import RunResult, Trial
from echotales.research.transforms.attribution_probe import probe

HYPOTHESIS_ID = "H-XDIS"
DEFAULT_PARAMS = {"n_quotes": 1000, "model": "qwen2.5:7b", "context_chars": 600, "candidates_window": 20}
OLLAMA = "http://localhost:11434/api/generate"


def _llm(prompt: str, model: str) -> str:
    # keep_alive 30s: the model frees the GPU soon after the last call
    # instead of ollama's 5-minute default (ENGINEERING_NOTES 16).
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "keep_alive": "30s",
                       "options": {"temperature": 0, "seed": 0, "num_predict": 16}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["response"].strip()


def _auroc(scores: list[float], labels: list[bool]) -> float | None:
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    novels = ([pdnc.synthetic_novel(seed=cfg.base_seed)] if stub
              else [pdnc.load_novel(n) for n in pdnc.available()])
    pool = []
    for nv in novels:
        qidx = {q.id: q for q in nv.quotes}
        for r in probe(nv):
            if r.resolved and r.owners and r.quote_id in qidx:
                pool.append((nv, qidx[r.quote_id], r))
    rng = random.Random(derive_seed(cfg.base_seed, "sample"))
    rng.shuffle(pool)
    sample = pool[: int(p["n_quotes"]) if not stub else 40]
    rows, trials = [], []
    for nv, q, r in sample:
        lo = max(0, q.start - int(p["context_chars"]))
        hi = min(len(nv.text), q.end + int(p["context_chars"]))
        near = [x for x in nv.quotes if abs(x.index - q.index) <= int(p["candidates_window"])]
        cands = sorted({x.speaker for x in near} | {a for x in near for a in x.addressees}
                       | set(r.owners))
        cands = [c for c in cands if c in nv.characters]
        if stub:
            llm = q.speaker if derive_seed(cfg.base_seed, q.id) % 5 else cands[0]
        else:
            prompt = (f"Passage:\n{nv.text[lo:hi]}\n\nIn this passage, who speaks the quotation "
                      f"“{q.text[:300]}”?\nChoose exactly one name from this list: "
                      f"{', '.join(cands)}.\nAnswer with the name only.")
            raw = _llm(prompt, p["model"])
            llm = next((c for c in sorted(cands, key=len, reverse=True)
                        if re.search(re.escape(c), raw, re.I)), None)
        ladder_err = not r.correct_lenient
        disagree = llm is None or llm not in r.owners
        rows.append({"err": ladder_err, "dis": disagree, "conf": r.confidence,
                     "llm_correct": llm == q.speaker})
        trials.append(Trial(unit_id=f"{nv.name}:{q.id}", condition="xdis", seed=0,
                            outputs={"llm": llm, "ladder_owners": list(r.owners)},
                            metrics={"ladder_error": float(ladder_err), "disagree": float(disagree),
                                     "conf": r.confidence}))
    errs = [x["err"] for x in rows]
    # Disagreement is binary; ladder confidence breaks ties within each class.
    score = [(1.0 if x["dis"] else 0.0) + 0.01 * (1 - x["conf"]) for x in rows]
    auc_dis = _auroc(score, errs)
    auc_conf = _auroc([1 - x["conf"] for x in rows], errs)
    killed = auc_dis is None or auc_dis < 0.7

    def _mean(xs):
        return round(float(np.mean(xs)), 4) if xs else None

    summary = {
        "quotes": len(rows), "ladder_error_rate": _mean(errs),
        "disagreement_rate": _mean([x["dis"] for x in rows]),
        "llm_accuracy": _mean([x["llm_correct"] for x in rows]),
        "auroc_disagreement": round(auc_dis, 4) if auc_dis is not None else None,
        "auroc_tier_confidence": round(auc_conf, 4) if auc_conf is not None else None,
        "p_error_given_disagree": _mean([x["err"] for x in rows if x["dis"]]),
        "p_error_given_agree": _mean([x["err"] for x in rows if not x["dis"]]),
        "model": p["model"],
    }
    hint = ("KILL" if killed else "PASSES (product-only)") + (
        f": AUROC disagreement {summary['auroc_disagreement']} vs tier confidence "
        f"{summary['auroc_tier_confidence']}; LLM accuracy {summary['llm_accuracy']}")
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="disagreement_posterior",
                      mode="stub" if stub else "real", config_hash=cfg.hash, n_units=len(rows),
                      n_trials=len(trials), summary=summary, verdict_hint=hint,
                      notes=["only quotes the ladder resolves (it resolves 9.9% of PDNC)",
                             "candidates = speakers/addressees within 20 quotes plus the ladder's owners"]),
            trials, {} if stub else {"pdnc_root": pdnc.PDNC_ROOT})
