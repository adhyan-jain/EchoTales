"""RI ch1 named check: the two unmarked cuts (blocks 31, 79) and who is present in each scene.

Usage, always under the GPU lock because the model is used for cuts and presence:

    flock /tmp/echotales-gpu.lock python scripts/eval/segment_ri_ch1_check.py \
        --conventions data/eval/segment/conventions/reverend-insanity.scene_conventions.json \
        --out data/eval/segment/ri_ch1_check.json

Reads a scratch copy of the RI ch1 DB (data/scratch/segment/ri_ch1.db), never data/db/.
The expectations below are the Opus-verified reading of ch1 (docs/results/MANHWA_DIRECTING_PATTERNS.md):
cuts before blocks 31 and 79 (owner gold data/gold/segment/ri_ch1_owner.json); in 31-79 only the clan head and the elders are in the room, and Fang Yuan,
Bai Ning Bing and Fang Zhi are only talked about; in 0-30 and 79-89 Fang Yuan is present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment.cast import FusionParams
from echotales.pipeline.segment.discontinuity import TopicModel, analyse_blocks, load_nlp
from echotales.pipeline.segment.induce import load_conventions
from echotales.pipeline.segment.outline import OutlineCache, OutlineOptions, outline_chapter
from echotales.pipeline.segment.presence import present_cast
from echotales.pipeline.segment.scenes import analyse_chapter_scenes

NOVEL = "reverend-insanity"
FANG_YUAN = "reverend-insanity:self:476821534c"
FANG_ZHI = "reverend-insanity:self:60117b7f5a"
SEGMENTS = [(0, 30), (31, 78), (79, 89)]  # owner gold data/gold/segment/ri_ch1_owner.json


def has(ids: list[str], needle: str) -> bool:
    return any(needle in i for i in ids)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/scratch/segment/ri_ch1.db")
    ap.add_argument("--conventions", default="data/eval/segment/conventions/reverend-insanity.scene_conventions.json")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--fusion", required=True, help="v4 fusion file written by segment_v4_eval.py arms (learn-chosen)")
    ap.add_argument("--lead", type=int, default=7)
    ap.add_argument("--out", default="data/eval/segment/ri_ch1_check_v4.json")
    ap.add_argument("--presence", default="llm", choices=["llm", "outline"], help="v5: outline = who-lines of the cached outline decide presence")
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--raw-words", type=int, default=0)
    ap.add_argument("--num-predict", type=int, default=300)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--tag", default="")
    ap.add_argument("--segment-model", default=None, help="model of the segmentation call when it differs from --model")
    args = ap.parse_args()
    from echotales.pipeline.segment import outline as outline_mod

    outline_mod.LEAD_WORDS = args.lead

    store = Store(args.db)
    llm = OllamaProvider(model=args.model, timeout=600.0, num_ctx=4096)
    seg_llm = OllamaProvider(model=args.segment_model or args.model, timeout=1800.0, num_ctx=args.ctx) if (args.think or args.raw_words or args.segment_model) else None
    options = OutlineOptions(think=args.think, max_tokens=args.num_predict, segment_llm=seg_llm, raw_words=args.raw_words, tag=args.tag)
    nlp = load_nlp()
    chapter = store.get_chapter(NOVEL, 1.0)
    cset = load_conventions(args.conventions)
    topic = TopicModel().fit([s.terms for s in analyse_blocks(chapter, None, nlp).values()])
    # v4: whole-chapter outline + cast continuity, fusion chosen on the learn chapters only (never on this chapter).
    params = FusionParams(**json.loads(Path(args.fusion).read_text())["fused"]["params"])
    analysis = analyse_chapter_scenes(
        chapter, cset, mentions=store.get_mentions(NOVEL, 1.0), llm=llm, nlp=nlp, topic=topic,
        method="outline", outline_params=params, outline_cache_dir="data/scratch/segment/outlinecache", novel_id=NOVEL,
        spans=store.get_spans(NOVEL, 1.0), labels={x.id: x.canonical_label for x in store.all_selves(NOVEL)},
        outline_options=options,
    )
    lines = None
    if args.presence == "outline":
        lines = outline_chapter(chapter, llm, novel_id=NOVEL, cache=OutlineCache("data/scratch/segment/outlinecache", args.model))
    cuts = [
        {"block": c.block, "source": c.source, "type": c.cut_type.value, "time": c.time_relation.value,
         "confidence": c.confidence, "why": c.evidence}
        for c in analysis.cuts
    ]
    found = {c["block"] for c in cuts}

    pres: dict[str, dict[str, list[str]]] = {}
    for lo, hi in SEGMENTS:
        present, referenced = present_cast(store, NOVEL, 1.0, lo, hi, llm=llm, require_quote=True, outline=lines)
        pres[f"{lo}-{hi}"] = {"present": present, "referenced": referenced}
    names = {x.id: x.canonical_label.lower() for x in store.all_selves(NOVEL)}
    p1_labels = sorted({names.get(i, i).lower() for i in pres["31-78"]["present"]})
    p0, p1, p2 = (pres[f"{lo}-{hi}"] for lo, hi in SEGMENTS)
    checks = {
        "cuts exactly {31, 79}": found == {31, 79},
        "cut 31 time relation is not LATER": all(c["time"] != "LATER" for c in cuts if c["block"] == 31),
        "0-30: Fang Yuan present": FANG_YUAN in p0["present"],
        "31-78: clan head present": has(p1["present"], "clan head") or any("clan head" in x for x in p1_labels),
        "31-78: elders present": any("elder" in x for x in p1_labels),
        "31-78: only clan head and elders present": all("clan head" in x or "elder" in x for x in p1_labels),
        "31-78: Fang Yuan NOT present": FANG_YUAN not in p1["present"],
        "31-78: Fang Yuan referenced": FANG_YUAN in p1["referenced"],
        "31-78: Bai Ning Bing referenced": has(p1["referenced"], "bai ning bing"),
        "31-78: Bai Ning Bing NOT present": not has(p1["present"], "bai ning bing"),
        "31-78: Fang Zhi referenced": FANG_ZHI in p1["referenced"],
        "31-78: Fang Zhi NOT present": FANG_ZHI not in p1["present"],
        "segment 0 layer = past (prior loop)": bool(analysis.time_labels) and analysis.time_labels[0].layer == "past"
        and set(analysis.prior_loop_segments) == {0},
        "79-89: Fang Yuan present": FANG_YUAN in p2["present"],
    }
    out = {
        "model": args.model,
        "cuts": cuts,
        "prior_loop_segments": sorted(analysis.prior_loop_segments),
        "time_labels": [{"segment": t.segment, "layer": t.layer, "relation": t.time_relation.value, "quote": t.quote, "verified": t.verified} for t in analysis.time_labels],
        "present_labels_31_78": p1_labels,
        "presence": pres,
        "checks": checks,
        "passed": sum(checks.values()),
        "total": len(checks),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "presence"}, indent=1))
    print(json.dumps(pres, indent=1))


if __name__ == "__main__":
    main()
