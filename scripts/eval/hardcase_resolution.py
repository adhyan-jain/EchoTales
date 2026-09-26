"""End-to-end resolver outcome on each hard-case category (SILVER).

REMAINING_WORK.md 1.1 listed this as the one hard-case number nobody had
taken: retrieval by category (`recall_by_category.py`) and detection loss
(SCORER_DIAGNOSIS Section 4) were both measured, but not what the resolver
finally *decided* for the hard cases it did detect.

Uses the scorer's own alignment (`coref_score.align_system_mentions`: exact
surface, chapter-absolute offset within 8 chars) and the scorer's own
identity mapping (`calibrate._identity_to_target`), so an outcome here is
the same event the coreference metrics count -- not a second, looser
matcher. Every record lands in exactly one bucket:

  not-detected    no system mention at that position with that surface
  unresolved      detected, target_id None (DEFER / NEW-without-link)
  correct         detected, linked to the identity's mapped target
  wrong           detected, linked to some other target
  gold-unmapped   the gold identity maps to no system entity at all, so
                  correct/wrong is undecidable; the detection half still counts

Two alignments are reported, because they disagree and both are in use:

  exact    -- the coreference scorer's own rule above. A system span of
              "Gu Yue Fang Yuan" does not match gold "Fang Yuan".
  overlap  -- any system span overlapping the gold span, the rule
              `scorer_diagnosis.py` used for its "59 of 89 never detected".
              Boundary disagreement is not a detection failure, so this is
              the fairer detection figure; the exact one is what B3/MUC see.

For title transfer, `unresolved` is not automatically a failure: EVOLUTION
4.69 found such mentions often *correctly* resolve to None. Read that column
as "declined to commit", not as an error.

Usage:
    python3 scripts/eval/hardcase_resolution.py [--db data/db/reverend-insanity.db]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from echotales.core.models import Mention
from echotales.core.store import Store
from echotales.pipeline.eval.calibrate import _identity_to_target
from echotales.pipeline.eval.coref_score import _block_starts, align_system_mentions
from echotales.pipeline.eval.gold import SILVER_BANNER, GoldMention, GoldSet, MentionKey, read_gold

NOVEL = "reverend-insanity"
GOLD = "data/gold/reverend-insanity-hardcases.jsonl"
BUCKETS = ("not-detected", "unresolved", "correct", "wrong", "gold-unmapped")


def category(note: str) -> str:
    return note[1 : note.index("]")] if note.startswith("[") and "]" in note else "uncategorised"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/db/reverend-insanity.db")
    ap.add_argument("--out", default="data/eval/hardcase_resolution.json")
    args = ap.parse_args()

    store = Store(args.db)
    gold = read_gold(GOLD, novel_id=NOVEL).silver_only.entities_only
    mapping, _unmapped = _identity_to_target(store, NOVEL, gold)
    alignments = {"exact": align_system_mentions(store, NOVEL, gold), "overlap": _overlap(store, gold)}
    store.close()

    tables = {mode: _tabulate(gold, aligned, mapping) for mode, aligned in alignments.items()}
    print(SILVER_BANNER)
    for mode, table in tables.items():
        print(f"\nalignment = {mode}")
        print(f"{'category':20} {'n':>4} " + " ".join(f"{b:>13}" for b in BUCKETS))
        for cat, row in table.items():
            print(f"{cat:20} {row['n']:>4} " + " ".join(f"{row[b]:>13}" for b in BUCKETS))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"banner": SILVER_BANNER, "db": args.db, "gold": GOLD, "outcomes": tables}, indent=2)
        + "\n"
    )
    print(f"\nwritten: {args.out}")
    return 0


def _overlap(store: Store, gold: GoldSet) -> dict[MentionKey, Mention | None]:
    """Gold key -> the longest system mention whose span overlaps the gold span."""
    out: dict[MentionKey, Mention | None] = {}
    by_chapter: dict[float, list[GoldMention]] = defaultdict(list)
    for m in gold.mentions:
        by_chapter[m.chapter].append(m)
    for chapter, wanted in by_chapter.items():
        starts = _block_starts(store, NOVEL, chapter)
        spans = [
            (starts[sm.block_index] + sm.offset, sm)
            for sm in store.get_mentions(NOVEL, chapter=chapter)
            if sm.block_index in starts
        ]
        for gm in wanted:
            hits: list[Mention] = [
                sm for a, sm in spans if a < gm.offset + len(gm.surface) and gm.offset < a + len(sm.text)
            ]
            out[gm.key] = max(hits, key=lambda sm: len(sm.text)) if hits else None
    return out


def _tabulate(
    gold: GoldSet, aligned: dict[MentionKey, Mention | None], mapping: dict[str, str]
) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for m in gold.mentions:
        if not m.identity:
            continue
        sm = aligned.get(m.key)
        detected = sm is not None
        target = sm.target_id if sm is not None else None
        expected = mapping.get(m.identity)
        if not detected:
            bucket = "not-detected"
        elif expected is None:
            bucket = "gold-unmapped"
        elif target is None:
            bucket = "unresolved"
        else:
            bucket = "correct" if target == expected else "wrong"
        for cat in (category(m.note), "ALL"):
            counts[cat][bucket] += 1

    return {cat: {b: c[b] for b in BUCKETS} | {"n": sum(c.values())} for cat, c in sorted(counts.items())}


if __name__ == "__main__":
    raise SystemExit(main())
