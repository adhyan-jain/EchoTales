"""Scene-cut v5 evaluation: exact and +-1 block scoring, a thinking segmentation call, a larger model.

    PYTHONPATH=packages/core/src:packages/pipeline/src ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local \
        python scripts/eval/segment_v5_eval.py segment --model qwen3:8b --split learn --think --tag think   # model calls (GPU lock per chapter)
    ... arms --model qwen3:8b --tag think --out data/scratch/segment/v5_fusion_think.json                   # learn grid, audited gold, +-1
    ... report --model qwen3:8b --tag think --fusion <file> --out data/eval/segment/scene_induction_v5_*.json

`rescore` re-scores cached outputs (no GPU). Held-out chapters are only read by `segment --split held` and `report`/`rescore
--split held`, after the configuration is frozen on learn. Selection uses the audited gold and the +-1 metric; exact and the
original gold are always reported next to it.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import segment_v4_eval as v4
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment import outline as outline_mod
from echotales.pipeline.segment.cast import FusionParams
from echotales.pipeline.segment.outline import (
    OutlineCache,
    SegmentCache,
    name_hints,
    outline_chapter,
    segment_outline,
)

LOCK = "/tmp/echotales-gpu.lock"
GOLDS = (("audited", v4.AUDITED), ("original", v4.GOLD))
TOLS = (("exact", 0), ("pm1", 1))
ARMS = ("outline", "cast", "and", "or", "fused")


def cmd_segment(a, meta, stores):
    llm = OllamaProvider(model=a.model, timeout=1800.0, num_ctx=a.ctx)
    # The outline model is separate so a bigger segmentation model reuses the cached 8B outlines (one change at a time).
    olm = llm if not a.outline_model else OllamaProvider(model=a.outline_model, timeout=900.0, num_ctx=4096)
    omodel = a.outline_model or a.model
    oc, sc = OutlineCache(v4.OCACHE, omodel), SegmentCache(v4.SCACHE, a.model, a.tag)
    todo = v4.chapters(meta, a.split)
    if a.only:
        todo = [t for t in todo if f"{t[0]}:{t[1]}" in a.only.split(",")]
    fails = []
    for novel, ch in todo:
        if sc.get(novel, float(ch)) is not None:
            continue
        chap, ments, spans, labels = v4.ctx(stores, novel, ch)
        t0 = time.time()
        with open(LOCK, "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            lines = outline_chapter(chap, olm, novel_id=novel, hints=name_hints(chap, ments, spans, labels), cache=oc)
            t1 = time.time()
            starts = segment_outline(chap, lines, llm, novel_id=novel, cache=sc, think=a.think, max_tokens=a.num_predict)
        ok = sc.get(novel, float(ch)) is not None or len(lines) < 4
        if not ok:
            # A call that produced no usable answer counts as "no cut" in the scores (never dropped from them), and is listed.
            fails.append(f"{novel}:{ch}")
            sc.put(novel, float(ch), [])
        print(f"{novel}:{ch} blocks={len(lines)} outline={t1 - t0:.0f}s seg={time.time() - t1:.0f}s {'OK' if ok else 'FAILED(scored as no cut)'} starts={[(s, c) for s, _, c in starts]}", flush=True)
    print("failed chapters:", fails)


def _arms_from_fusion(fus):
    return {arm: FusionParams(**fus[arm]["params"]) for arm in ARMS if arm in fus}


def cmd_arms(a, meta, stores):
    """Learn grid on the audited gold with the +-1 metric (--tol); writes the best params per arm."""
    gmeta, _ = v4.load(v4.AUDITED if a.gold == "audited" else v4.GOLD)
    data = v4.Data(gmeta, stores, a.model, "learn", tag=a.tag)
    best: dict[str, tuple] = {}
    for p in v4.grid():
        pooled, per, _hn = data.score(gmeta, p, a.tol)
        key = (pooled["f1"], -p.min_gap, -p.cast_k)
        if p.mode not in best or key > best[p.mode][0]:
            best[p.mode] = (key, p, pooled, per)
    out = {}
    for mode, (_, p, pooled, per) in best.items():
        print(f"{mode:8s} learn F1 {pooled['f1']:.3f} P {pooled['precision']:.2f} R {pooled['recall']:.2f} (tol {a.tol}, {a.gold}) {asdict(p)}")
        out[mode] = {"params": asdict(p), "learn": pooled, "per_novel": per}
    fused = max(("and", "or"), key=lambda m: out[m]["learn"]["f1"])
    out["fused"] = {"mode": fused, **out[fused]}
    out["model"], out["tag"], out["selected_on"] = a.model, a.tag, f"{a.gold} gold, tol {a.tol}, learn"
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


def cmd_report(a, meta, stores):
    fus = json.loads(Path(a.fusion).read_text())
    params = _arms_from_fusion(fus)
    res = {"model": a.model, "tag": a.tag, "selected_on": fus.get("selected_on"), "params": {k: asdict(v) for k, v in params.items()}}
    splits = ("learn", "held") if a.split == "all" else (a.split,)
    for gname, gpath in GOLDS:
        gmeta, _ = v4.load(gpath)
        for split in splits:
            data = v4.Data(gmeta, stores, a.model, split, tag=a.tag)
            for arm, p in params.items():
                for tname, tol in TOLS:
                    pooled, per, hn = data.score(gmeta, p, tol)
                    res.setdefault(gname, {}).setdefault(split, {}).setdefault(arm, {})[tname] = {"pooled": pooled, "per_novel": per, "hard_negatives": hn}
                    if arm in ("outline", "fused"):
                        print(gname, split, f"{arm:8s} {tname:5s}", pooled, "chapters", len(data.rows), flush=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["segment", "arms", "report"])
    ap.add_argument("--split", default="learn", choices=["learn", "held", "all"])
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--outline-model", help="model whose cached outlines are used (default: --model)")
    ap.add_argument("--tag", default="", help="segmentation configuration label (cache directory suffix)")
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--num-predict", type=int, default=300)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--only")
    ap.add_argument("--gold", default="audited", choices=["original", "audited"])
    ap.add_argument("--tol", type=int, default=1)
    ap.add_argument("--fusion")
    ap.add_argument("--out")
    ap.add_argument("--lead", type=int, default=7)
    a = ap.parse_args()
    outline_mod.LEAD_WORDS = a.lead
    meta, stores = v4.load(v4.AUDITED if a.gold == "audited" else v4.GOLD)
    v4.STORES.update(stores)
    {"segment": cmd_segment, "arms": cmd_arms, "report": cmd_report}[a.cmd](a, meta, stores)


if __name__ == "__main__":
    main()
