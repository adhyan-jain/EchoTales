"""Score a database against every reader-gold chapter for its novel and print the four Phase A gate numbers.

Usage: python scripts/eval/score_reader_gold.py <db> <novel_id> [--misses]

The numbers are against model-drafted silver references (`data/gold/reader/`), and the output says so. Open the
database read-only-ish: pass a copy (`sqlite3 x.db ".backup copy.db"`), because `Store` rewrites the schema row on open.
"""

from __future__ import annotations

import sys
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval import reader_gold as g

GOLD_DIR = Path(__file__).resolve().parents[2] / "data" / "gold" / "reader"
#: Gate A (docs/design/decisions.md D4).
GATES = {"speakers": 0.90, "appearance": 0.85, "persona_links": 0.90, "kinds": 0.95}


def main(db: str, novel_id: str, show_misses: bool) -> None:
    store = Store(db)
    files = sorted(GOLD_DIR.glob(f"{novel_id}-ch*.json"))
    totals: dict[str, g.Score] = {k: g.Score() for k in (*GATES, "ages")}
    false_dialogue = 0
    for path in files:
        gold = g.load_reader_gold(path)
        results = {
            "speakers": g.score_speakers(gold, store),
            "appearance": g.score_appearance(gold, store),
            "persona_links": g.score_persona_links(gold, store),
            "kinds": g.score_kinds(gold, store),
            "ages": g.score_ages(gold, store),
        }
        false_dialogue += results["speakers"].false_dialogue  # type: ignore[attr-defined]
        for key, score in results.items():
            totals[key].correct += score.correct
            totals[key].total += score.total
            if show_misses:
                for miss in score.misses:
                    print(f"  ch{gold.chapter} {key}: {miss}")
    print(f"{novel_id}: {len(files)} reference chapters (model-drafted silver, not gold)")
    for key, score in totals.items():
        gate = GATES.get(key)
        verdict = "" if gate is None else ("  PASS" if score.rate >= gate else f"  below gate {gate:.0%}")
        print(f"  {key:14s} {score.correct:4d}/{score.total:<4d} {score.rate:6.1%}{verdict}")
    print(f"  false dialogue spans (cover no reference line): {false_dialogue}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--misses" in sys.argv)
