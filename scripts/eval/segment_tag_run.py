"""Tag gold chapters with per-block place/time (segment v2.1) and cache the raw tags per (model, novel, chapter).

    PYTHONPATH=packages/core/src:packages/pipeline/src python scripts/eval/segment_tag_run.py \
        --model qwen3:8b --split learn

The GPU lock (/tmp/echotales-gpu.lock, shared with other agents) is held per chapter, never for the whole run.
Tuning (segment_tag_tune.py) reads only these caches, so it needs no GPU.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import time
from dataclasses import asdict
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.llm.ollama import OllamaProvider
from echotales.pipeline.segment.place_tags import PROMPT_VERSION, tag_chapter

CACHE = Path("data/scratch/segment/tagcache")


def cache_path(model: str, novel: str, ch: str) -> Path:
    return CACHE / f"{model.replace(':', '_')}_{PROMPT_VERSION}" / f"{novel}_{ch}.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--gold", default="data/gold/segment/scene_boundaries.json")
    ap.add_argument("--learn-chapters", type=int, default=10)
    ap.add_argument("--split", choices=["learn", "held", "all"], default="learn")
    ap.add_argument("--novels", nargs="*")
    ap.add_argument("--chapters", nargs="*", help="only these chapter keys (default: whole split)")
    a = ap.parse_args()
    meta = json.loads(Path(a.gold).read_text())
    llm = OllamaProvider(model=a.model, timeout=600.0, num_ctx=4096)
    for novel, gold in meta["novels"].items():
        if a.novels and novel not in a.novels:
            continue
        store = Store(meta["dbs"][novel])
        for ch in gold:
            if a.chapters and ch not in a.chapters:
                continue
            n = float(ch)
            lm = meta.get("learn_max", {}).get(novel, a.learn_chapters)
            if (a.split == "learn" and n > lm) or (a.split == "held" and n <= lm):
                continue
            path = cache_path(a.model, novel, ch)
            if path.exists():
                continue
            chapter = store.get_chapter(novel, n)
            t0 = time.time()
            with open("/tmp/echotales-gpu.lock", "w") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                tags = tag_chapter(chapter, llm)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps([{**asdict(t), "time_shift": t.time_shift.value} for t in tags]))
            print(novel, ch, len(tags), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
