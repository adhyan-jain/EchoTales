"""Scene-cut v2 benchmark: whole-chapter model segmentation combined with the discontinuity score.

Usage (repo root; scratch DB copies under data/scratch/segment/, never data/db/):

    flock /tmp/echotales-gpu.lock python scripts/eval/segment_v2_eval.py --models qwen3:8b gemma2:9b \
        --out data/eval/segment/scene_induction_v2.json

The raw model scene lists are cached per (model, novel, chapter) under data/scratch/segment/llmcache/ so the
combination rule can be tuned offline on the LEARN chapters only (chapter number <= --learn-chapters) and then
read once on the held-out chapters. Gold is data/gold/segment/scene_boundaries.json (silver, not owner-checked).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.segment.cuts import TimeRelation
from echotales.pipeline.segment.discontinuity import (
    TopicModel,
    analyse_blocks,
    canonical_position,
    load_nlp,
    score_chapter,
)
from echotales.pipeline.segment.embed import get_embedder
from echotales.pipeline.segment.induce import induce_conventions
from echotales.pipeline.segment.llm_segment import LLMScene, segment_chapter_llm
from echotales.pipeline.segment.scenes import combine_llm_cuts

DB_DIR = Path("data/scratch/segment")
CACHE = DB_DIR / "llmcache"


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}


def score_preds(pred: dict[str, set[int]], gold: dict, chapters: dict, subset, tol: int = 0) -> dict:
    tp = fp = fn = 0
    for ch, spec in gold.items():
        if not subset(float(ch)):
            continue
        c = chapters[ch]
        g = {canonical_position(c, x["block"]) for x in spec["cuts"]}
        amb = {canonical_position(c, x) for x in spec.get("ambiguous", [])}
        p = {x for x in pred.get(ch, set()) if x not in (amb - g)}
        matched_g = {x for x in g if any(abs(x - y) <= tol for y in p)}
        matched_p = {y for y in p if any(abs(x - y) <= tol for x in g)}
        tp += len(matched_g)
        fn += len(g - matched_g)
        fp += len(p - matched_p)
    return prf(tp, fp, fn)


def load_scenes(model: str, novel: str, ch: str, chapter, llm) -> list[LLMScene]:
    path = CACHE / model.replace(":", "_") / f"{novel}_{ch}.json"
    if path.exists():
        return [
            LLMScene(**{**d, "time_relation": TimeRelation(d["time_relation"])}) for d in json.loads(path.read_text())
        ]
    scenes = segment_chapter_llm(chapter, llm)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{**asdict(s), "time_relation": s.time_relation.value} for s in scenes]))
    return scenes


def prepare(novel: str, db: str, gold: dict, learn_n: int, embedder):
    store = Store(db)
    nlp = load_nlp()
    allc = list(store.iter_chapters(novel))
    learn = [c for c in allc if c.number <= learn_n]
    topic = TopicModel().fit([s.terms for c in learn for s in analyse_blocks(c, None, nlp).values()])
    cset = induce_conventions(novel, learn, nlp=nlp, topic=topic, mentions_by_chapter={})
    chapters = {ch: store.get_chapter(novel, float(ch)) for ch in gold}
    return store, nlp, topic, cset, chapters


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen3:8b"])
    ap.add_argument("--gold", default="data/gold/segment/scene_boundaries.json")
    ap.add_argument("--out", default="data/eval/segment/scene_induction_v2.json")
    ap.add_argument("--learn-chapters", type=int, default=10)
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--novels", nargs="*", default=None)
    ap.add_argument("--split", choices=["learn", "all"], default="all", help="learn: only chapters <= --learn-chapters")
    args = ap.parse_args()
    meta = json.loads(Path(args.gold).read_text())
    golds = meta["novels"]
    dbs = meta["dbs"]
    from echotales.pipeline.llm.ollama import OllamaProvider

    llms = {m: OllamaProvider(model=m, timeout=600.0) for m in args.models}
    embedder = None if args.no_embed else get_embedder()
    print("embedder:", "nomic-embed-text" if embedder else "TF-IDF fallback")
    out = {"models": args.models, "embedder": bool(embedder), "learn_chapters": args.learn_chapters, "novels": {}}
    for novel, gold in golds.items():
        if args.novels and novel not in args.novels:
            continue
        if args.split == "learn":
            gold = {ch: v for ch, v in gold.items() if float(ch) <= args.learn_chapters}
        _store, nlp, topic, cset, chapters = prepare(novel, dbs[novel], gold, args.learn_chapters, embedder)
        raw: dict[str, dict] = {}
        for ch, chapter in chapters.items():
            tf = score_chapter(chapter, None, nlp=nlp, topic=topic)
            em = score_chapter(chapter, None, nlp=nlp, topic=topic, embedder=embedder) if embedder else tf
            raw[ch] = {"tfidf": tf, "embed": em}
        scenes = {m: {ch: load_scenes(m, novel, ch, chapters[ch], llms[m]) for ch in chapters} for m in args.models}
        res: dict[str, dict] = {}
        for feat in ("tfidf", "embed"):
            k = 0.06
            base = {
                ch: {b.position for b in sorted(raw[ch][feat], key=lambda b: -b.score)[: max(1, round(len(raw[ch][feat]) * k))]}
                for ch in chapters
            }
            res[f"{feat}:score_top6pct"] = base
            for m in args.models:
                for name, thr in (("all", -1.0), ("p75", cset.candidate_threshold), ("p90", cset.high_threshold)):
                    res[f"{feat}:{m}:{name}"] = {
                        ch: {c.block for c in combine_llm_cuts(chapters[ch], scenes[m][ch], raw[ch][feat], accept_score=thr)}
                        for ch in chapters
                    }
        out["novels"][novel] = {
            "p75": cset.candidate_threshold,
            "p90": cset.high_threshold,
            "results": {
                name: {
                    split: score_preds(pred, gold, chapters, fn, tol)
                    for split, fn in (
                        ("learn", lambda n: n <= args.learn_chapters),
                        ("held_out", lambda n: n > args.learn_chapters),
                        ("all", lambda n: True),
                    )
                    for tol in (0,)
                }
                for name, pred in res.items()
            },
            "preds": {n: {ch: sorted(v) for ch, v in p.items()} for n, p in res.items()},
        }
        for name in res:
            r = out["novels"][novel]["results"][name]
            print(f"{novel[:10]:10} {name:28} learn F1 {r['learn']['f1']:.2f} (P {r['learn']['precision']:.2f} R {r['learn']['recall']:.2f})"
                  f" | held F1 {r['held_out']['f1']:.2f} (P {r['held_out']['precision']:.2f} R {r['held_out']['recall']:.2f})")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
