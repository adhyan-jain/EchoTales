"""Run EchoTales on LitBank's human-annotated coreference key.

For each of the 100 documents (or a seeded subset): ingest the tokenised
excerpt as a one-chapter novel, run segment -> mentions -> anaphora ->
resolve exactly as `echotales run` does (speaker attribution and personas are
skipped; they do not affect coreference), then score against LitBank's person
clusters. See `eval/litbank.py` for the two scoring conventions and
`docs/results/EXTERNAL_BENCHMARK.md` for the protocol and its incompatibilities.

Needs a local ollama (NER is an LLM call); responses are cached per text hash.

Usage:
    python3 scripts/eval/litbank_eval.py [--limit N] [--seed 20260925]
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any

from echotales.core.store import Store
from echotales.pipeline.anaphora import resolve_novel as anaphora_resolve
from echotales.pipeline.commands import _build_client
from echotales.pipeline.corrections import CorrectionLog
from echotales.pipeline.eval.litbank import (
    ingest_document,
    parse_document,
    person_clusters,
    score,
    system_mentions,
)
from echotales.pipeline.mentions import detect_mentions, load_or_seed
from echotales.pipeline.resolve import resolve_novel as global_resolve
from echotales.pipeline.segment import segment_novel

BASE = Path("data/external/litbank/coref")
RUNS = Path("data/external/litbank_runs")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="seeded subset size (0 = all 100)")
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--out", default="data/eval/litbank_results.json")
    args = ap.parse_args()

    docs = sorted(p.name[: -len("_brat.txt")] for p in (BASE / "brat").glob("*_brat.txt"))
    if args.limit:
        docs = sorted(random.Random(args.seed).sample(docs, args.limit))
    RUNS.mkdir(parents=True, exist_ok=True)
    db = RUNS / "litbank.db"
    if db.exists():
        db.unlink()
    store = Store(str(db))
    client = _build_client(store)
    lexicon = load_or_seed(None)

    results: dict[str, tuple[Any, Any]] = {}
    sanity: dict[str, tuple[Any, Any]] = {}
    per_doc: dict[str, dict[str, int]] = {}
    t0 = time.perf_counter()
    for i, doc in enumerate(docs, 1):
        text, key = parse_document(BASE / "brat" / f"{doc}_brat.txt",
                                   BASE / "conll" / f"{doc}_brat.conll",
                                   BASE / "brat" / f"{doc}_brat.ann")
        novel = f"litbank-{doc}"
        ingest_document(store, novel, text)
        segment_novel(novel, store)
        detect_mentions(novel, store, lexicon=lexicon, client=client)
        anaphora_resolve(novel, store)
        global_resolve(novel, store, lexicon=lexicon,
                       corrections_log=CorrectionLog(RUNS / "corrections.jsonl"))
        store.conn.commit()
        sys_m = system_mentions(store, novel)
        results[doc] = (key, sys_m)
        # Gold scored against itself must give 100 -- checks the adapter and the
        # pooling, not the system.
        people = person_clusters(key)
        sanity[doc] = (key, [(m.start, m.end, m.cluster) for m in key if m.cluster in people])
        per_doc[doc] = {"key_mentions": len(key), "system_mentions": len(sys_m)}
        print(f"[{i}/{len(docs)}] {doc}: key={len(key)} system={len(sys_m)} "
              f"({time.perf_counter() - t0:.0f}s)", flush=True)
    store.close()

    report = {
        "dataset": "LitBank coreference (Bamman, Lewke & Mansoor, LREC 2020), CC BY 4.0",
        "docs": len(docs), "subset_seed": args.seed if args.limit else None,
        "model": "qwen2.5:7b via local ollama (NER only)",
        "runtime_s": round(time.perf_counter() - t0, 1),
        "sanity_gold_vs_gold_standard_P1": score(sanity, prop_only=False, key_restricted=False),
        "protocols": {
            "P1_full_person_key": {
                "key_restricted": score(results, prop_only=False, key_restricted=True),
                "standard": score(results, prop_only=False, key_restricted=False),
            },
            "P2_proper_name_mentions_only": {
                "key_restricted": score(results, prop_only=True, key_restricted=True),
                "standard": score(results, prop_only=True, key_restricted=False),
            },
        },
        "per_doc": per_doc,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print("sanity CoNLL:", report["sanity_gold_vs_gold_standard_P1"]["CoNLL_F1"])
    for proto, modes in report["protocols"].items():
        for mode, s in modes.items():
            print(f"{proto:30} {mode:15} MUC {s['MUC_F1']:5.1f}  B3 {s['B3_F1']:5.1f}  "
                  f"CEAFe {s['CEAFe_F1']:5.1f}  CoNLL {s['CoNLL_F1']:5.1f}  "
                  f"(gold {s['gold_mentions']}, system {s['system_mentions']}, exact {s['exact_span_matches']})")
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
