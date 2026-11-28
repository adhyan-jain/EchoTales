"""Tune and read the place/time tag cutter (segment v2.1) from cached tags; no GPU needed except for embeddings.

    PYTHONPATH=packages/core/src:packages/pipeline/src python scripts/eval/segment_tag_tune.py \
        --models qwen3:8b --split learn          # grid search on LEARN chapters only, prints the best params
    ... --split held --params data/scratch/segment/best_params.json   # read once on held-out chapters

Held-out numbers use parameters chosen on the learn chapters of ALL novels pooled (one global setting; a per-novel
cap rate comes from each novel's own learn-chapter gold, i.e. the learned prior).
"""

from __future__ import annotations

import argparse
import fcntl
import itertools
import json
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from echotales.core.store import Store
from echotales.pipeline.segment.cuts import TimeRelation
from echotales.pipeline.segment.discontinuity import canonical_position
from echotales.pipeline.segment.embed import get_embedder
from echotales.pipeline.segment.place_tags import (
    PlaceCutParams,
    TaggedBlock,
    place_candidates,
    rule_cuts,
    select_cuts,
)
from segment_tag_run import cache_path


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}


def load_tags(model: str, novel: str, ch: str) -> list[TaggedBlock] | None:
    p = cache_path(model, novel, ch)
    if not p.exists():
        return None
    return [
        TaggedBlock(d["block"], d["place"], TimeRelation(d["time_shift"]), d["time_anchor"])
        for d in json.loads(p.read_text())
    ]


def score(preds: dict, gold_by_novel: dict, chapters: dict, keep) -> dict:
    """P/R/F1 plus false cuts on labelled hard negatives (`negatives` in the gold, exact canonical block)."""
    tp = fp = fn = hn_total = hn_hit = 0
    for (novel, ch), pred in preds.items():
        spec = gold_by_novel[novel][ch]
        if not keep(novel, float(ch)):
            continue
        c = chapters[(novel, ch)]
        g = {canonical_position(c, x["block"]) for x in spec["cuts"]}
        amb = {canonical_position(c, x) for x in spec.get("ambiguous", [])}
        neg = {canonical_position(c, x["block"]) for x in spec.get("negatives", [])}
        p = {x for x in pred if x not in (amb - g)}
        tp += len(g & p)
        fn += len(g - p)
        fp += len(p - g)
        hn_total += len(neg)
        hn_hit += len(neg & p)
    out = prf(tp, fp, fn)
    out["hard_negatives"] = hn_total
    out["hard_negative_false_cuts"] = hn_hit
    return out


def cap_rates(gold_by_novel: dict, chapters: dict, learn_max: Callable[[str], float], mult: float) -> dict[str, float]:
    """Per novel: mult x learn-chapter gold cuts per block (the learned prior on cuts per chapter)."""
    out = {}
    for novel, gold in gold_by_novel.items():
        cuts = blocks = 0
        for ch, spec in gold.items():
            if float(ch) <= learn_max(novel):
                cuts += len(spec["cuts"])
                blocks += spec.get("n_blocks") or len(chapters[(novel, ch)].blocks)
        out[novel] = mult * cuts / blocks if blocks else 0.0
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen3:8b"])
    ap.add_argument("--gold", default="data/gold/segment/scene_boundaries.json")
    ap.add_argument("--learn-chapters", type=int, default=10)
    ap.add_argument("--split", choices=["learn", "held", "all"], default="learn")
    ap.add_argument("--params", help="json file {model: {embed|tokens: params}} to apply instead of searching")
    ap.add_argument("--out")
    a = ap.parse_args()
    meta = json.loads(Path(a.gold).read_text())
    gold = meta["novels"]
    stores = {n: Store(meta["dbs"][n]) for n in gold}
    chapters = {(n, ch): stores[n].get_chapter(n, float(ch)) for n, g in gold.items() for ch in g}
    with open("/tmp/echotales-gpu.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        embedder = get_embedder()
    # learn_max per novel (Scarlet learns on 1-7, ORV on 1-10 with chapters 2 and 3 labelled): tagging uses the same rule.
    lmax = lambda novel: float(meta.get("learn_max", {}).get(novel, a.learn_chapters))  # noqa: E731
    keep = {
        "learn": lambda novel, n: n <= lmax(novel),
        "held": lambda novel, n: n > lmax(novel),
        "all": lambda novel, n: True,
    }[a.split]
    result: dict = {"split": a.split, "models": {}}
    for model in a.models:
        tags = {k: t for k in chapters if (t := load_tags(model, *k)) is not None}
        for feat, emb in (("rule", None), ("embed", embedder), ("tokens", None)):
            if feat == "embed" and embedder is None:
                continue
            if feat == "rule":
                # Place change AND flagged time jump (place_tags.rule_cuts); only min_gap is free.
                gaps = [json.loads(Path(a.params).read_text())[model][feat]["min_gap"]] if a.params else [1, 3, 5, 8]
                rows = []
                for gap in gaps:
                    par = PlaceCutParams(min_gap=gap, both=True)
                    preds = {k: {canonical_position(chapters[k], c.block) for c in rule_cuts(chapters[k], t, par)} for k, t in tags.items()}
                    rows.append(({"min_gap": gap}, score(preds, gold, chapters, keep), preds))
                rows.sort(key=lambda r: -r[1]["f1"])
                best = rows[0]
                per_novel = {n: score({k: v for k, v in best[2].items() if k[0] == n}, gold, chapters, keep) for n in gold if any(k[0] == n for k in best[2])}
                result["models"].setdefault(model, {})[feat] = {"params": best[0], "pooled": best[1], "per_novel": per_novel}
                print(model, feat, a.split, best[0], best[1])
                for n, s in per_novel.items():
                    print("   ", n[:14], s)
                continue
            # Embedding calls are cached in the embedder; the candidate lists do not depend on the threshold.
            cands = {k: {side: place_candidates(t, emb, side=side) for side in (2, 3)} for k, t in tags.items()}
            grid = list(itertools.product((0.15, 0.25, 0.35, 0.45, 0.6), (0.0, 0.5, 1.0), (2, 3), (3, 5, 8), (None, 1.5, 2.0, 3.0)))
            if a.params:
                best_p = json.loads(Path(a.params).read_text())[model][feat]
                grid = [(best_p["threshold"], best_p["time_weight"], best_p["side"], best_p["min_gap"], best_p["cap_mult"])]
            rows = []
            for thr, tw, side, gap, capm in grid:
                rates = cap_rates(gold, chapters, lmax, capm) if capm else {}
                preds = {}
                for k, t in tags.items():
                    cs = cands[k][side]
                    par = PlaceCutParams(threshold=thr, time_weight=tw, side=side, min_gap=gap, cap_rate=rates.get(k[0]) if capm else None)
                    preds[k] = {canonical_position(chapters[k], c.block) for c in select_cuts(chapters[k], cs, par, len(t))}
                rows.append(
                    ({"threshold": thr, "time_weight": tw, "side": side, "min_gap": gap, "cap_mult": capm}, score(preds, gold, chapters, keep), preds)
                )
            rows.sort(key=lambda r: -r[1]["f1"])
            best = rows[0]
            per_novel = {}
            for n in gold:
                sub = {k: v for k, v in best[2].items() if k[0] == n}
                if sub:
                    per_novel[n] = score(sub, gold, chapters, keep)
            result["models"].setdefault(model, {})[feat] = {"params": best[0], "pooled": best[1], "per_novel": per_novel, "top5": [(r[0], r[1]["f1"]) for r in rows[:5]]}
            print(model, feat, a.split, best[0], best[1])
            for n, s in per_novel.items():
                print("   ", n[:14], s)
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
