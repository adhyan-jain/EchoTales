"""RI ch1 named check: the two unmarked cuts (blocks 31, 80) and who is present in each scene.

Usage, always under the GPU lock because the model is used for cuts and presence:

    flock /tmp/echotales-gpu.lock python scripts/eval/segment_ri_ch1_check.py \
        --conventions data/eval/segment/conventions/reverend-insanity.scene_conventions.json \
        --out data/eval/segment/ri_ch1_check.json

Reads a scratch copy of the RI ch1 DB (data/scratch/segment/ri_ch1.db), never data/db/.
The expectations below are the Opus-verified reading of ch1 (docs/results/MANHWA_DIRECTING_PATTERNS.md):
cuts before blocks 31 and 80; in 31-79 only the clan head and the elders are in the room, and Fang Yuan,
Bai Ning Bing and Fang Zhi are only talked about; in 0-30 and 80-91 Fang Yuan is present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment.discontinuity import TopicModel, analyse_blocks, load_nlp
from echotales.pipeline.segment.induce import load_conventions
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
    ap.add_argument("--conventions", required=True)
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--out", default="data/eval/segment/ri_ch1_check.json")
    args = ap.parse_args()

    store = Store(args.db)
    llm = OllamaProvider(model=args.model, timeout=300.0)
    nlp = load_nlp()
    chapter = store.get_chapter(NOVEL, 1.0)
    cset = load_conventions(args.conventions)
    topic = TopicModel().fit([s.terms for s in analyse_blocks(chapter, None, nlp).values()])
    analysis = analyse_chapter_scenes(
        chapter, cset, mentions=store.get_mentions(NOVEL, 1.0), llm=llm, nlp=nlp, topic=topic
    )
    cuts = [
        {"block": c.block, "source": c.source, "type": c.cut_type.value, "time": c.time_relation.value,
         "confidence": c.confidence, "why": c.evidence}
        for c in analysis.cuts
    ]
    found = {c["block"] for c in cuts}

    pres: dict[str, dict[str, list[str]]] = {}
    for lo, hi in SEGMENTS:
        present, referenced = present_cast(store, NOVEL, 1.0, lo, hi, llm=llm)
        pres[f"{lo}-{hi}"] = {"present": present, "referenced": referenced}
    p0, p1, p2 = (pres[f"{lo}-{hi}"] for lo, hi in SEGMENTS)
    checks = {
        "cuts exactly {31, 79}": found == {31, 79},
        "0-30: Fang Yuan present": FANG_YUAN in p0["present"],
        "31-78: clan head present": has(p1["present"], "clan head"),
        "31-78: Fang Yuan NOT present": FANG_YUAN not in p1["present"],
        "31-78: Fang Yuan referenced": FANG_YUAN in p1["referenced"],
        "31-78: Bai Ning Bing referenced": has(p1["referenced"], "bai ning bing"),
        "31-78: Bai Ning Bing NOT present": not has(p1["present"], "bai ning bing"),
        "31-78: Fang Zhi referenced": FANG_ZHI in p1["referenced"],
        "31-78: Fang Zhi NOT present": FANG_ZHI not in p1["present"],
        "prior-loop flag on segment 0 only": set(analysis.prior_loop_segments) == {0},
        "cut 31 time relation EARLIER or UNKNOWN": any(
            c["block"] == 31 and c["time"] in ("EARLIER", "UNKNOWN") for c in cuts
        ),
        "79-89: Fang Yuan present": FANG_YUAN in p2["present"],
    }
    out = {
        "model": args.model,
        "cuts": cuts,
        "prior_loop_segments": sorted(analysis.prior_loop_segments),
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
