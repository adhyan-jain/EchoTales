"""Scene-cut v5b evaluation: the boundary-placement refine step against the frozen v5 configuration.

    PYTHONPATH=packages/core/src:packages/pipeline/src ECHOTALES_MODEL_BACKEND=ollama ECHOTALES_LLM_MODE=local \
        flock /tmp/echotales-gpu.lock python scripts/eval/segment_v5b_eval.py --split learn --out data/eval/segment/scene_induction_v5b_learn.json

Reads the cached v5 segmentation answers (tag think_raw40), fuses them with the frozen learn-chosen parameters, then scores the cuts
with and without `refine_cuts` (one cheap no-thinking call per cut, cached). Exact and +-1, audited and original gold. Held-out is
read only with `--split held`, once, after the learn decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import segment_v4_eval as v4
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment.cast import (
    FusionParams,
    block_casts,
    cast_scores,
    fuse,
    separator_positions,
)
from echotales.pipeline.segment.discontinuity import canonical_position
from echotales.pipeline.segment.outline import RefineCache, SegmentCache, refine_cuts
from echotales.pipeline.segment.scoring import score_cuts
from segment_tag_tune import prf

TAG = "think_raw40"
GOLDS = (("audited", v4.AUDITED), ("original", v4.GOLD))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="learn", choices=["learn", "held"])
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--fusion", default="data/scratch/v5_FROZEN_8b_think_raw40.json")
    ap.add_argument("--out")
    a = ap.parse_args()
    params = FusionParams(**json.loads(Path(a.fusion).read_text())["fused"]["params"])
    meta, stores = v4.load(v4.AUDITED)
    v4.STORES.update(stores)
    llm = OllamaProvider(model=a.model, timeout=300.0, num_ctx=4096)
    sc = SegmentCache(v4.SCACHE, a.model, TAG)
    rc = RefineCache(v4.SCACHE, a.model)
    rows = []
    for novel, ch in v4.chapters(meta, a.split):
        starts = sc.get(novel, float(ch))
        if starts is None:
            continue
        chap, ments, spans, _ = v4.ctx(stores, novel, ch)
        scores = cast_scores(chap, block_casts(chap, ments, spans), params.cast_k)
        out = sorted({canonical_position(chap, b) for b, _, c in starts if c >= params.conf_min})
        base = fuse(chap, out, scores, separator_positions(chap), params)
        ref = refine_cuts(chap, base, llm, novel_id=novel, cache=rc)
        rows.append((novel, ch, chap, base, ref))
        if base != ref:
            print(f"{novel}:{ch} {base} -> {ref}", flush=True)
    res = {"split": a.split, "params": params.__dict__ if hasattr(params, "__dict__") else str(params), "chapters": len(rows)}
    for gname, gpath in GOLDS:
        gmeta, _ = v4.load(gpath)
        for arm, idx in (("base", 3), ("refined", 4)):
            for tname, tol in (("exact", 0), ("pm1", 1)):
                per: dict[str, list[int]] = {}
                for r in rows:
                    chap, g, amb, _neg = v4.gold_sets(gmeta, stores, r[0], r[1])
                    if g is None:
                        continue
                    pred = {canonical_position(chap, b) for b in r[idx]}
                    tp, fp, fn = score_cuts(g, pred, tol, ignore=amb - g)
                    p = per.setdefault(r[0], [0, 0, 0])
                    p[0] += tp
                    p[1] += fp
                    p[2] += fn
                tp, fp, fn = (sum(v[i] for v in per.values()) for i in range(3))
                res.setdefault(gname, {}).setdefault(arm, {})[tname] = {"pooled": prf(tp, fp, fn), "per_novel": {n: prf(*v) for n, v in per.items()}}
                print(gname, a.split, arm, tname, prf(tp, fp, fn), flush=True)
    res["moves"] = [{"novel": r[0], "chapter": r[1], "before": r[3], "after": r[4]} for r in rows if r[3] != r[4]]
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
