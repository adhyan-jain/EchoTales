"""Scene-cut v4 evaluation: whole-chapter outline pass, cast continuity from the graph, fusion learned on LEARN.

    PYTHONPATH=packages/core/src:packages/pipeline/src ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local \
        python scripts/eval/segment_v4_eval.py outline --model qwen3:8b --split learn     # model calls, GPU lock per chapter, resumable
    ... arms --model qwen3:8b --out data/scratch/segment/v4_fusion_qwen3.json              # learn grid, writes the chosen fusion
    ... outline --model qwen3:8b --split held; ... report --model qwen3:8b --fusion <file> --out data/eval/segment/...

Held-out chapters are only read by `outline --split held` and `report`, after the prompt and fusion are frozen.
"""

from __future__ import annotations

import argparse
import fcntl
import itertools
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from echotales.core.store import Store
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment import outline
from echotales.pipeline.segment.cast import (
    FusionParams,
    block_casts,
    cast_scores,
    fuse,
    separator_positions,
)
from echotales.pipeline.segment.discontinuity import canonical_position
from echotales.pipeline.segment.outline import (
    OutlineCache,
    SegmentCache,
    name_hints,
    outline_chapter,
    segment_outline,
)
from segment_tag_tune import prf

GOLD = "data/gold/segment/scene_boundaries.json"
AUDITED = "data/gold/segment/scene_boundaries_audited.json"
OCACHE = "data/scratch/segment/outlinecache"
SCACHE = "data/scratch/segment/outlinecache"
LOCK = "/tmp/echotales-gpu.lock"
K_GRID = (2, 3, 4, 5)
THETA_GRID = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def load(gold_path=GOLD):
    meta = json.loads(Path(gold_path).read_text())
    base = json.loads(Path(GOLD).read_text())
    meta.setdefault("dbs", base["dbs"])
    meta.setdefault("learn_max", base.get("learn_max", {}))
    stores = {n: Store(base["dbs"][n]) for n in meta["novels"]}
    return meta, stores


def in_split(meta, novel, ch, split):
    lm = float(meta.get("learn_max", {}).get(novel, 10))
    return {"learn": float(ch) <= lm, "held": float(ch) > lm, "all": True}[split]


def chapters(meta, split):
    return [(n, ch) for n, g in meta["novels"].items() for ch in g if in_split(meta, n, ch, split)]


def ctx(stores, novel, ch):
    st = stores[novel]
    chap = st.get_chapter(novel, float(ch))
    ments = st.get_mentions(novel, float(ch))
    spans = st.get_spans(novel, float(ch))
    labels = {s.id: s.canonical_label for s in st.all_selves(novel)}
    return chap, ments, spans, labels


def cmd_outline(a, meta, stores):
    llm = OllamaProvider(model=a.model, timeout=900.0, num_ctx=4096)
    oc, sc = OutlineCache(OCACHE, a.model), SegmentCache(SCACHE, a.model)
    todo = chapters(meta, a.split)
    if a.only:
        todo = [t for t in todo if f"{t[0]}:{t[1]}" in a.only.split(",")]
    for novel, ch in todo:
        if oc.get(novel, float(ch)) is not None and (sc.get(novel, float(ch)) is not None or a.outline_only):
            continue
        chap, ments, spans, labels = ctx(stores, novel, ch)
        t0 = time.time()
        with open(LOCK, "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            lines = outline_chapter(chap, llm, novel_id=novel, hints=name_hints(chap, ments, spans, labels), cache=oc)
            t1 = time.time()
            starts = [] if a.outline_only else segment_outline(chap, lines, llm, novel_id=novel, cache=sc)
        print(f"{novel}:{ch} blocks={len(lines)} outline={t1 - t0:.0f}s seg={time.time() - t1:.0f}s starts={[(s, c) for s, _, c in starts]}", flush=True)


def gold_sets(meta, stores, novel, ch):
    spec = meta["novels"][novel].get(ch)
    chap = stores[novel].get_chapter(novel, float(ch))
    if spec is None:
        return chap, None, set(), set()
    g = {canonical_position(chap, x["block"]) for x in spec["cuts"]}
    amb = {canonical_position(chap, x) for x in spec.get("ambiguous", [])}
    neg = {canonical_position(chap, x["block"]) for x in spec.get("negatives", [])}
    return chap, g, amb, neg


class Data:
    """Per (novel, chapter): story blocks, outline cuts, cast scores per K, separators, loaded once."""

    def __init__(self, meta, stores, model, split, gold_meta=None):
        self.rows = []
        sc = SegmentCache(SCACHE, model)
        for novel, ch in chapters(meta, split):
            starts = sc.get(novel, float(ch))
            if starts is None:
                continue
            chap, ments, spans, _labels = ctx(stores, novel, ch)
            casts = block_casts(chap, ments, spans)
            self.rows.append({
                "novel": novel, "ch": ch, "chap": chap,
                "starts": [(canonical_position(chap, b), c) for b, _, c in starts],
                "scores": {k: cast_scores(chap, casts, k) for k in K_GRID},
                "seps": separator_positions(chap),
            })

    def score(self, meta, params: FusionParams):
        per: dict[str, list[int]] = {}
        hn = [0, 0]
        for r in self.rows:
            chap, g, amb, neg = gold_sets(meta, STORES, r["novel"], r["ch"])
            if g is None:
                continue
            out = sorted({b for b, c in r["starts"] if c >= params.conf_min})
            pred = {canonical_position(chap, b) for b in fuse(chap, out, r["scores"][params.cast_k], r["seps"], params)}
            pred = {x for x in pred if x not in (amb - g)}
            p = per.setdefault(r["novel"], [0, 0, 0])
            p[0] += len(g & pred)
            p[1] += len(pred - g)
            p[2] += len(g - pred)
            hn[0] += len(neg)
            hn[1] += len(neg & pred)
        tp, fp, fn = (sum(v[i] for v in per.values()) for i in range(3))
        return prf(tp, fp, fn), {n: prf(*v) for n, v in per.items()}, hn


STORES = {}


def grid():
    for g, cm in itertools.product((1, 3, 5), (1, 3, 4, 5)):
        yield FusionParams("outline", min_gap=g, conf_min=cm)
    for k, th, g in itertools.product(K_GRID, THETA_GRID, (3, 5, 8)):
        yield FusionParams("cast", k, th, min_gap=g)
    for k, th, w, sep, g, cm in itertools.product(K_GRID, THETA_GRID, (0, 2, 4), (True, False), (1, 3), (1, 3, 4, 5)):
        yield FusionParams("and", k, th, w, sep, g, cm)
    for k, th, g, cm in itertools.product(K_GRID, THETA_GRID, (1, 3), (1, 3, 4, 5)):
        yield FusionParams("or", k, th, min_gap=g, conf_min=cm)


def cmd_arms(a, meta, stores):
    data = Data(meta, stores, a.model, "learn")
    best: dict[str, tuple] = {}
    for p in grid():
        pooled, per, hn = data.score(meta, p)
        key = (pooled["f1"], -p.min_gap, -p.cast_k)  # ties go to the simpler setting
        if p.mode not in best or key > best[p.mode][0]:
            best[p.mode] = (key, p, pooled, per, hn)
    out = {}
    for mode, (_, p, pooled, per, _hn) in best.items():
        print(f"{mode:8s} learn F1 {pooled['f1']:.3f} P {pooled['precision']:.2f} R {pooled['recall']:.2f} {asdict(p)}")
        out[mode] = {"params": asdict(p), "learn": pooled, "per_novel": per}
    fused = max(("and", "or"), key=lambda m: out[m]["learn"]["f1"])
    out["fused"] = {"mode": fused, **out[fused]}
    out["model"] = a.model
    print("fused arm:", fused)
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


def cmd_report(a, meta, stores):
    fus = json.loads(Path(a.fusion).read_text())
    res = {"model": a.model, "fusion": {k: v for k, v in fus.items() if k in ("outline", "cast", "and", "or", "fused")}}
    for gname, gpath in (("original", GOLD), ("audited", AUDITED)):
        if not Path(gpath).exists():
            continue
        gmeta, _ = load(gpath)
        for split in ("learn", "held"):
            data = Data(gmeta, stores, a.model, split)
            for arm in ("outline", "cast", "and", "or", "fused"):
                p = FusionParams(**fus[arm]["params"])
                pooled, per, hn = data.score(gmeta, p)
                res.setdefault(gname, {}).setdefault(split, {})[arm] = {"pooled": pooled, "per_novel": per, "hard_negatives": hn[0], "hard_negative_false_cuts": hn[1], "params": fus[arm]["params"]}
                print(gname, split, f"{arm:8s}", pooled, "hn", hn, flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["outline", "arms", "report"])
    ap.add_argument("--split", default="learn", choices=["learn", "held", "all"])
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--only")
    ap.add_argument("--outline-only", action="store_true")
    ap.add_argument("--gold", default="original", choices=["original", "audited"])
    ap.add_argument("--fusion")
    ap.add_argument("--out")
    ap.add_argument("--lead", type=int, default=None, help="opening words per block in the outline line (default: module value)")
    a = ap.parse_args()
    if a.lead is not None:
        outline.LEAD_WORDS = a.lead
    meta, stores = load(AUDITED if a.gold == "audited" else GOLD)
    STORES.update(stores)
    {"outline": cmd_outline, "arms": cmd_arms, "report": cmd_report}[a.cmd](a, meta, stores)


if __name__ == "__main__":
    main()
