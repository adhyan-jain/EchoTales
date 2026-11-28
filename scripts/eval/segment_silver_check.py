"""LotM ch1 and ORV ch1 silver checks for the v4 scene cutter (one scene each; named people present or referenced).

    flock /tmp/echotales-gpu.lock python scripts/eval/segment_silver_check.py --fusion <file> --model qwen3:8b

LotM ch1 (data/gold/segment/lotm_ch1_silver.json): one scene, no cut; Klein present. ORV ch1 (orv_ch1_silver.json): one
scene; Kim Dokja present; tls123 referenced only. Reads the scratch DBs named in scene_boundaries.json, never data/db/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment import outline as outline_mod
from echotales.pipeline.segment.cast import FusionParams
from echotales.pipeline.segment.outline import OutlineCache, OutlineOptions, outline_chapter
from echotales.pipeline.segment.presence import present_cast
from echotales.pipeline.segment.scenes import analyse_chapter_scenes

CASES = {
    # LotM ch1 is the transmigrant Zhou Mingrui in Klein's body; the silver file names him as the same person, and the graph
    # labels him by that name, so either label counts as Klein.
    "lord-of-the-mysteries": ("data/gold/segment/lotm_ch1_silver.json", ("klein", "zhou mingrui"), None),
    "omniscient-readers-viewpoint": ("data/gold/segment/orv_ch1_silver.json", ("kim dokja",), "tls123"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fusion", required=True)
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--lead", type=int, default=7)
    ap.add_argument("--out", default="data/eval/segment/silver_ch1_check_v4.json")
    ap.add_argument("--presence", default="llm", choices=["llm", "outline"])
    ap.add_argument("--think", action="store_true")
    ap.add_argument("--raw-words", type=int, default=0)
    ap.add_argument("--num-predict", type=int, default=300)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--tag", default="")
    ap.add_argument("--segment-model", default=None)
    a = ap.parse_args()
    outline_mod.LEAD_WORDS = a.lead
    params = FusionParams(**json.loads(Path(a.fusion).read_text())["fused"]["params"])
    llm = OllamaProvider(model=a.model, timeout=600.0, num_ctx=4096)
    seg_llm = OllamaProvider(model=a.segment_model or a.model, timeout=1800.0, num_ctx=a.ctx) if (a.think or a.raw_words or a.segment_model) else None
    options = OutlineOptions(think=a.think, max_tokens=a.num_predict, segment_llm=seg_llm, raw_words=a.raw_words, tag=a.tag)
    dbs = json.loads(Path("data/gold/segment/scene_boundaries.json").read_text())["dbs"]
    res = {}
    for novel, (gold_path, must_present, referenced_only) in CASES.items():
        gold = json.loads(Path(gold_path).read_text())
        store = Store(dbs[novel])
        chapter = store.get_chapter(novel, 1.0)
        labels = {x.id: x.canonical_label for x in store.all_selves(novel)}
        an = analyse_chapter_scenes(
            chapter, None, mentions=store.get_mentions(novel, 1.0), llm=llm, method="outline", outline_params=params,
            outline_cache_dir="data/scratch/segment/outlinecache", novel_id=novel, spans=store.get_spans(novel, 1.0), labels=labels,
            outline_options=options,
        )
        lines = outline_chapter(chapter, llm, novel_id=novel, cache=OutlineCache("data/scratch/segment/outlinecache", a.model)) if a.presence == "outline" else None
        sc = gold["scenes"][0]
        present, referenced = present_cast(store, novel, 1.0, sc["block_from"], sc["block_to"], llm=llm, require_quote=True, outline=lines)
        plabels = sorted({labels.get(i, i).lower() for i in present})
        rlabels = sorted({labels.get(i, i).lower() for i in referenced})
        checks = {
            "one scene, no cuts": not an.cuts,
            f"{must_present[0]} present": any(n in x for x in plabels for n in must_present),
        }
        if referenced_only:
            checks[f"{referenced_only} referenced, not present"] = any(referenced_only in x for x in rlabels) and not any(referenced_only in x for x in plabels)
        res[novel] = {"cuts": [c.block for c in an.cuts], "present": plabels, "referenced": rlabels, "checks": checks}
        print(novel, json.dumps(res[novel], indent=1))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
