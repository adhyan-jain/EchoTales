"""Scene-cut induction benchmark: learn on a novel's first volume, score against silver gold.

Usage (from the repo root, scratch DB copies under data/scratch/segment/):

    python scripts/eval/segment_induction_eval.py --out data/eval/segment/scene_induction.json [--llm qwen3:8b]

Wrap the invocation in `flock /tmp/echotales-gpu.lock` whenever --llm is given.
Gold is data/gold/segment/scene_boundaries.json (silver: drafted by reading, not human-verified).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.segment.discontinuity import (
    TopicModel,
    analyse_blocks,
    canonical_position,
    load_nlp,
)
from echotales.pipeline.segment.induce import (
    conventions_path,
    induce_conventions,
    save_conventions,
)
from echotales.pipeline.segment.scenes import analyse_chapter_scenes

DBS = {
    "reverend-insanity": "data/scratch/segment/reverend-insanity.db",
    "lord-of-the-mysteries": "data/scratch/segment/lord-of-the-mysteries.db",
    "omniscient-readers-viewpoint": "data/scratch/segment/omniscient-readers-viewpoint.db",
    "pride-and-prejudice": "data/scratch/segment/pp.db",
}
LEARN_CHAPTERS = 10


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}


def score_set(pred: dict[str, set[int]], gold: dict, chapters: dict[str, object], subset) -> dict[str, float]:
    tp = fp = fn = 0
    for ch, spec in gold.items():
        if not subset(float(ch)):
            continue
        c = chapters[ch]
        g = {canonical_position(c, x["block"]) for x in spec["cuts"]}
        amb = {canonical_position(c, x) for x in spec["ambiguous"]}
        p = pred.get(ch, set()) - (amb - g)
        tp += len(p & g)
        fp += len(p - g)
        fn += len(g - p)
    return prf(tp, fp, fn)


def run(novel: str, db: str, gold: dict, llm, out_dir: Path) -> dict:
    store = Store(db)
    nlp = load_nlp()
    chapters_all = list(store.iter_chapters(novel))
    learn = [c for c in chapters_all if c.number <= LEARN_CHAPTERS]
    topic = TopicModel().fit(
        [s.terms for c in learn for s in analyse_blocks(c, None, nlp).values()]
    )
    mentions = {c.number: store.get_mentions(novel, c.number) for c in learn}
    cset = induce_conventions(novel, learn, mentions_by_chapter=mentions, llm=llm, nlp=nlp, topic=topic)
    save_conventions(cset, conventions_path(novel, out_dir))

    gold_ch = {ch: store.get_chapter(novel, float(ch)) for ch in gold}
    preds: dict[str, dict[str, set[int]]] = {"score_top6pct": {}, "induced_strong": {}, "full": {}}
    labels: dict[str, list[dict]] = {}
    for ch, chapter in gold_ch.items():
        ments = store.get_mentions(novel, float(ch))
        base = analyse_chapter_scenes(chapter, cset, mentions=ments, llm=None, nlp=nlp, topic=topic)
        k = max(1, round(len(base.boundaries) * 0.06))
        preds["score_top6pct"][ch] = {b.position for b in sorted(base.boundaries, key=lambda b: -b.score)[:k]}
        preds["induced_strong"][ch] = {c.block for c in base.cuts}
        if llm is not None:
            full = analyse_chapter_scenes(chapter, cset, mentions=ments, llm=llm, nlp=nlp, topic=topic)
            preds["full"][ch] = {c.block for c in full.cuts}
            labels[ch] = [
                {"block": c.block, "source": c.source, "type": c.cut_type.value, "time": c.time_relation.value,
                 "conf": c.confidence, "why": c.evidence[:2]}
                for c in full.cuts
            ] + [{"prior_loop_segments": sorted(full.prior_loop_segments)}]
    def split(pred):
        return {
            "all": score_set(pred, gold, gold_ch, lambda n: True),
            "learned_range": score_set(pred, gold, gold_ch, lambda n: n <= LEARN_CHAPTERS),
            "held_out": score_set(pred, gold, gold_ch, lambda n: n > LEARN_CHAPTERS),
        }
    return {
        "novel": novel,
        "base_rate": cset.base_rate,
        "high_threshold": cset.high_threshold,
        "conventions": [
            {k: getattr(c, k) for k in ("id", "support", "hits", "hit_rate", "lift", "accepted", "strength", "reason")}
            for c in cset.conventions
            if c.accepted or c.lift >= 1.5
        ],
        "results": {name: split(p) for name, p in preds.items() if p},
        "predictions": {name: {k: sorted(v) for k, v in p.items()} for name, p in preds.items() if p},
        "labels": labels,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/eval/segment/scene_induction.json")
    ap.add_argument("--conventions-dir", default="data/eval/segment/conventions")
    ap.add_argument("--llm", default="", help="ollama model for convention confirmation (empty = stats only)")
    args = ap.parse_args()
    gold = json.loads(Path("data/gold/segment/scene_boundaries.json").read_text())["novels"]
    llm = None
    if args.llm:
        from echotales.pipeline.llm.ollama import OllamaProvider

        llm = OllamaProvider(model=args.llm, timeout=300.0)
    results = [run(n, DBS[n], gold[n], llm, Path(args.conventions_dir)) for n in DBS]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"llm": args.llm or None, "learn_chapters": LEARN_CHAPTERS, "novels": results}, indent=1))
    for r in results:
        print(r["novel"], "base", r["base_rate"], "thr", r["high_threshold"])
        for c in r["conventions"]:
            if c["accepted"]:
                print("   +", c["id"], c["support"], c["hits"], c["lift"], c["strength"], c["reason"])
        for name, res in r["results"].items():
            print("   ", name, "all", res["all"], "held", res["held_out"])


if __name__ == "__main__":
    main()
