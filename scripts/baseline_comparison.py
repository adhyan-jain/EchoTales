"""Put Baselines A, B and EchoTales on one scored footing, ch1-10, SILVER.

BASELINES.md's comparison table was assembled by hand, and on 2026-09-25 it
turned out to compare the baselines' ch1-10 B3 recall (0.2%, 4.6%) against
EchoTales' *full-volume* 96.3%. On the same 356 ch1-10 silver mentions,
EchoTales scores 79.1%. This script is the single place all three numbers
come from, so that cannot recur: the baselines from their persisted run
records, EchoTales scored here from its database with the same `score_b3`.

Usage:
    python3 scripts/baseline_comparison.py [--db data/reruns/ner-window-ri.db]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import score_b3
from echotales.pipeline.eval.gold import SILVER_BANNER, GoldSet, read_gold

NOVEL = "reverend-insanity"
GOLD = "data/gold/reverend-insanity.jsonl"
LO, HI = 1, 10
RECORDS = {
    "Baseline A (long-context)": Path("data/eval/results/baseline-a-ch1-10.json"),
    "Baseline B (dual-LLM memorisation)": Path("data/eval/results/baseline-b-ch1-10-r2.json"),
}


def _from_record(name: str, path: Path) -> dict[str, Any] | None:
    if not path.exists():
        print(f"  {name}: no run record at {path} -- skipped")
        return None
    rec = json.loads(path.read_text())
    scores = rec.get("scores", {})
    score = scores.get(f"ch{LO}-{HI}") or scores.get(f"ch1-{HI}")
    if not score:
        print(f"  {name}: {path} carries no ch{LO}-{HI} SILVER score -- skipped")
        return None
    calls = rec.get("calls", rec.get("extractor_calls", 0) + rec.get("linker_calls", 0))
    return {
        "name": name,
        "calls": calls,
        "prompt_tokens": rec.get("prompt_tokens"),
        "wall_seconds": round(rec.get("wall_seconds", 0.0), 1),
        "mentions": rec.get("mentions"),
        "b3_precision": score["b3_precision"],
        "b3_recall": score["b3_recall"],
        "source": str(path),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/reruns/ner-window-ri.db")
    ap.add_argument("--out", default="data/eval/baseline_comparison.json")
    args = ap.parse_args()

    systems = [s for name, p in RECORDS.items() if (s := _from_record(name, p))]

    gold = read_gold(GOLD, novel_id=NOVEL)
    sub = GoldSet(
        NOVEL, [m for m in gold.silver_only.entities_only.mentions if LO <= m.chapter <= HI]
    )
    store = Store(args.db)
    r = score_b3(store, NOVEL, sub)
    (mentions,) = store.conn.execute(
        "SELECT count(*) FROM mention WHERE novel_id=? AND chapter BETWEEN ? AND ?",
        (NOVEL, LO, HI),
    ).fetchone()
    store.close()
    systems.append({
        "name": "EchoTales",
        # Resolution makes no model calls. Its ~30 upstream NER calls for this
        # range are excluded, as BASELINES.md states; the baselines' counts
        # include their own extraction, so this column favours EchoTales by
        # that margin and says so rather than hiding it.
        "calls": 0,
        "prompt_tokens": None,
        "wall_seconds": None,
        "mentions": mentions,
        "b3_precision": r.precision,
        "b3_recall": r.recall,
        "source": f"{args.db} scored here",
    })

    print(SILVER_BANNER)
    print(f"ch{LO}-{HI}, {len(sub.mentions)} silver mentions")
    for s in systems:
        print(f"  {s['name']:36} calls={s['calls']!s:>4} mentions={s['mentions']!s:>4} "
              f"B3 P={s['b3_precision']:.1%} R={s['b3_recall']:.1%}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "banner": SILVER_BANNER,
        "chapters": [LO, HI],
        "gold": GOLD,
        "gold_mentions": len(sub.mentions),
        "systems": systems,
    }, indent=2) + "\n")
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
