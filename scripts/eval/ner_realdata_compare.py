"""Legacy vs hybrid mention detection on a trimmed scratch copy of a real novel DB (D69 real-data check).

Copies a source DB, keeps chapters 1..N (text, spans, segments) and drops every derived row, runs `detect_mentions`
with the chosen `mentions.detector`, then `anaphora` + `resolve_novel`, and writes one JSON of counts, surfaces,
wall time, loaded models and peak GPU. The name caches live in a scratch lexicon dir so a cold run is measured and the
shared `data/lexicons/*-ner-cache.json` is never read or written. The source DB is opened read-only.

Usage (from the repo root, env ECHOTALES_MODEL_BACKEND=ollama):
    python scripts/eval/ner_realdata_compare.py --novel reverend-insanity --src SRC.db --last 5 --mode hybrid --out OUT_DIR
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sqlite3
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

DERIVED = [
    "mention", "self_entity", "persona", "self_persona_binding", "alias_binding", "attribute", "relation",
    "resolution_event", "observation", "llm_call", "scoring_evidence", "review_item", "scene_state",
    "span_emotion", "span_emotion_override", "persona_version", "voice_profile", "bible_lock", "derived_artifact",
    "ref_image_candidate", "ref_image_selection_log", "location_plate", "screenplay_episode",
]


def trim(src: Path, dst: Path, last: float) -> None:
    dst.unlink(missing_ok=True)
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    s.backup(d)
    s.close()
    for t in DERIVED:
        if d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone():
            d.execute(f"DELETE FROM {t}")
    d.execute("DELETE FROM chapter WHERE number > ?", (last,))
    d.execute("DELETE FROM span WHERE chapter > ?", (last,))
    d.execute("DELETE FROM narrative_segment WHERE chapter_from > ?", (last,))
    d.commit()
    d.close()


class GpuWatch(threading.Thread):
    """Samples nvidia-smi used MiB and `ollama ps` model names every second; peak is the max sample."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.peak = 0
        self.base = 0
        self.ollama: set[str] = set()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                used = int(subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True).split()[0])
                self.peak = max(self.peak, used)
                ps = subprocess.check_output(["ollama", "ps"], text=True).splitlines()[1:]
                self.ollama |= {line.split()[0] for line in ps if line.strip()}
            except Exception:
                pass
            self.stop.wait(1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--last", type=float, required=True)
    ap.add_argument("--mode", choices=["legacy", "hybrid"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--gliner-model", default="")
    ap.add_argument("--classifier-model", default="")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    db = out / f"{a.novel}-ch1-{int(a.last)}-{a.mode}.db"
    trim(Path(a.src), db, a.last)
    lexdir = out / f"lex-{a.mode}"
    lexdir.mkdir(exist_ok=True)

    from echotales.core.store import Store
    from echotales.pipeline.anaphora import resolve_anaphora_for_novel
    from echotales.pipeline.commands import _build_client
    from echotales.pipeline.config import get_settings
    from echotales.pipeline.corrections import CorrectionLog
    from echotales.pipeline.ingest import get_source
    from echotales.pipeline.mentions import detect_mentions, load_or_seed
    from echotales.pipeline.resolve import resolve_novel

    cfg = get_settings().model_copy(update={"lexicon_path": lexdir, "mentions_detector": "llm" if a.mode == "legacy" else "hybrid"})
    if a.gliner_model:
        cfg = cfg.model_copy(update={"mentions_gliner_model": a.gliner_model})
    if a.classifier_model:
        cfg = cfg.model_copy(update={"mentions_classifier_model": a.classifier_model})
    store = Store(db)
    lexicon = load_or_seed(get_source(a.novel).lexicon)
    client = _build_client(store)
    client.settings = cfg

    watch = GpuWatch()
    watch.start()
    t0 = time.perf_counter()
    report = detect_mentions(a.novel, store, lexicon=lexicon, settings=cfg, client=client)
    t_mentions = time.perf_counter() - t0
    store.conn.commit()
    watch.stop.set()
    watch.join()

    rows = store.conn.execute("SELECT text, chapter, method, provenance FROM mention WHERE novel_id=?", (a.novel,)).fetchall()
    surfaces = Counter(r["text"] for r in rows)

    resolve_anaphora_for_novel(a.novel, store)
    t1 = time.perf_counter()
    rr = resolve_novel(a.novel, store, lexicon=lexicon, settings=cfg,
                       corrections_log=CorrectionLog(out / f"{a.novel}-{a.mode}-corrections.jsonl"), force_rewipe=True)
    t_resolve = time.perf_counter() - t1
    store.conn.commit()

    result = {
        "novel": a.novel, "mode": a.mode, "chapters": f"1-{int(a.last)}",
        "detector_name": report.detector_name,
        "mentions": len(rows), "distinct_surfaces": len(surfaces), "surface_counts": dict(surfaces),
        "mention_wall_s": round(t_mentions, 1), "resolve_wall_s": round(t_resolve, 1),
        "ollama_models_seen": sorted(watch.ollama), "gpu_peak_mib": watch.peak,
        "resolve": {k: v for k, v in dataclasses.asdict(rr).items() if isinstance(v, (int, float, str, dict)) and k != "novel_id"},
        "db": str(db),
    }
    (out / f"{a.novel}-ch1-{int(a.last)}-{a.mode}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "surface_counts"}, indent=1))
    store.close()


if __name__ == "__main__":
    main()
