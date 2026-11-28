"""Re-run the v1 cutter (`per_boundary`: change score + induced conventions + qwen3 judge; or `place_tags`, v2.1) on every chapter of the current golds.

v1's recorded numbers (data/eval/segment/scene_induction.json) cover only the 25 chapters of the first 22-cut gold. The v5
comparison needs v1 on the same 70 chapters, so this writes its cuts per chapter and `report` scores them (exact and +-1,
both golds). Run under the GPU lock: `flock /tmp/echotales-gpu.lock python scripts/eval/segment_v5_v1.py run [per_boundary|place_tags]`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import segment_v4_eval as v4
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment.discontinuity import (
    TopicModel,
    analyse_blocks,
    canonical_position,
    load_nlp,
)
from echotales.pipeline.segment.induce import induce_conventions
from echotales.pipeline.segment.scenes import analyse_chapter_scenes
from echotales.pipeline.segment.scoring import score_cuts
from segment_tag_tune import prf

METHOD = sys.argv[2] if len(sys.argv) > 2 else "per_boundary"  # per_boundary = v1; place_tags = v2.1 (the current default)
OUT = Path(f"data/scratch/segment/v5_{METHOD}_cuts.json")
LEARN = 10


def run() -> None:
    meta, stores = v4.load(v4.GOLD)
    llm = OllamaProvider(model="qwen3:8b", timeout=300.0)
    nlp = load_nlp()
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    for novel, gold in meta["novels"].items():
        if novel in res:
            continue
        store = stores[novel]
        learn = [c for c in store.iter_chapters(novel) if c.number <= LEARN]
        topic = TopicModel().fit([s.terms for c in learn for s in analyse_blocks(c, None, nlp).values()])
        cset = induce_conventions(novel, learn, mentions_by_chapter={c.number: store.get_mentions(novel, c.number) for c in learn}, llm=llm, nlp=nlp, topic=topic)
        out = {}
        for ch in gold:
            chap = store.get_chapter(novel, float(ch))
            an = analyse_chapter_scenes(chap, cset, mentions=store.get_mentions(novel, float(ch)), llm=llm, nlp=nlp, topic=topic, method=METHOD)
            out[ch] = sorted({c.block for c in an.cuts})
        res[novel] = out
        OUT.write_text(json.dumps(res))
        print(novel, "done", flush=True)


def report() -> None:
    res = json.loads(OUT.read_text())
    for gname, gpath in (("audited", v4.AUDITED), ("original", v4.GOLD)):
        meta, stores = v4.load(gpath)
        for split in ("learn", "held"):
            for tol in (0, 1):
                tot, per = [0, 0, 0], {}
                for novel, gold in meta["novels"].items():
                    for ch, spec in gold.items():
                        if not v4.in_split(meta, novel, ch, split):
                            continue
                        chap = stores[novel].get_chapter(novel, float(ch))
                        g = {canonical_position(chap, x["block"]) for x in spec["cuts"]}
                        amb = {canonical_position(chap, x) for x in spec.get("ambiguous", [])}
                        t = score_cuts(g, set(res[novel][ch]), tol, ignore=amb - g)
                        q = per.setdefault(novel, [0, 0, 0])
                        for i in range(3):
                            tot[i] += t[i]
                            q[i] += t[i]
                print(gname, split, "pm1" if tol else "exact", prf(*tot), {n: prf(*v)["f1"] for n, v in per.items()})


if __name__ == "__main__":
    {"run": run, "report": report}[sys.argv[1]]()
