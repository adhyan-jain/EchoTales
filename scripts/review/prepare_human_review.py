"""Prepare the human-review sheets. Never fills a label.

Draws a seeded, stratified 200-mention sample from the canonical database and
writes one row per mention for a person to judge, plus a sheet for the 88
hard-case records. `reviewer_label` and `reviewer_notes` are always empty:
this project has no human labels yet, and this script must not invent any.

The sheets carry a <=200-character window of the (copyrighted) novel text so
a reviewer can judge the mention, so they are gitignored and must not be
committed or shared outside the review team.

Strata (target counts; a stratum smaller than its target is taken whole):
  easy_name          rigid name linked by exact gazetteer match, surface equals
                     the entity's canonical label                          30
  alias              rigid name linked where the surface differs from the
                     canonical label                                       35
  title              TRANSFERABLE_TITLE mentions                           30
  relational         RELATIONAL_DEICTIC mentions                           35
  unresolved_name    rigid names the system did not link                   all
  observer_sensitive mentions of a revealed Self (see `observation`)
                     within 10 chapters of its reveal                      30
  background         uniform random from everything else, to reach 200
A pronoun stratum is intentionally absent: pronouns never become graph
mentions in this system (they are linked locally in Phase 5), so there is no
system decision to review. The protocol states this.

Usage:
    python3 scripts/review/prepare_human_review.py [--db data/db/reverend-insanity.db] [--seed 20260925]
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import Any

from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import _block_starts
from echotales.pipeline.eval.gold import read_gold

NOVEL = "reverend-insanity"
FIELDS = ["sample_id", "chapter", "source_text", "mention", "predicted_entity",
          "candidate_entities", "system_decision", "reference_set_decision",
          "category", "reviewer_label", "reviewer_notes"]
TARGETS = {"easy_name": 30, "alias": 35, "title": 30, "relational": 35,
           "unresolved_name": 10**6, "observer_sensitive": 30}
TOTAL = 200
WINDOW = 200


def _snippet(text: str, absolute: int, surface: str) -> str:
    lo = max(0, absolute - (WINDOW - len(surface)) // 2)
    return text[lo:lo + WINDOW].replace("\n", " ").replace(surface, f"[[{surface}]]", 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/db/reverend-insanity.db")
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--out-dir", default="data/eval")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    store = Store(args.db)
    conn = store.conn
    label = dict(conn.execute("SELECT id, canonical_label FROM self_entity WHERE novel_id=?", (NOVEL,)))
    alias_targets: dict[str, set[str]] = {}
    for alias, target in conn.execute(
            "SELECT alias_norm, target_id FROM alias_binding WHERE novel_id=?", (NOVEL,)):
        alias_targets.setdefault(alias, set()).add(target)
    revealed: dict[str, int] = {}
    for fact_ref, first in conn.execute(
            "SELECT fact_ref, MIN(learned_chapter) FROM observation GROUP BY fact_ref"):
        target = fact_ref.split(":", 1)[1].rsplit(":", 1)[0]
        revealed[target] = min(first, revealed.get(target, 10**6))

    rows = conn.execute(
        "SELECT id, chapter, block_index, offset, text, alias_type, method, target_id "
        "FROM mention WHERE novel_id=? ORDER BY chapter, block_index, offset", (NOVEL,)).fetchall()

    def stratum(r: Any) -> str:
        _id, ch, _b, _o, text, alias_type, method, target = r
        if target in revealed and abs(ch - revealed[target]) <= 10:
            return "observer_sensitive"
        if alias_type == "TRANSFERABLE_TITLE":
            return "title"
        if alias_type == "RELATIONAL_DEICTIC":
            return "relational"
        if target is None:
            return "unresolved_name"
        if method == "GAZETTEER_EXACT" and label.get(target, "").casefold() == text.casefold():
            return "easy_name"
        if label.get(target, "").casefold() != text.casefold():
            return "alias"
        return "background"

    pools: dict[str, list[Any]] = {}
    for r in rows:
        pools.setdefault(stratum(r), []).append(r)
    chosen: list[tuple[str, Any]] = []
    for name, n in TARGETS.items():
        pool = pools.get(name, [])
        chosen += [(name, r) for r in rng.sample(pool, min(n, len(pool)))]
    taken = {c[1][0] for c in chosen}
    remaining = [r for r in rows if r[0] not in taken]
    chosen += [("background", r) for r in rng.sample(remaining, max(0, TOTAL - len(chosen)))]

    silver = read_gold("data/gold/reverend-insanity.jsonl", NOVEL).silver_only.entities_only
    silver_at = {(m.chapter, m.offset): m.identity for m in silver.mentions}

    texts: dict[float, str] = {}
    starts: dict[float, dict[int, int]] = {}

    def chapter_text(ch: float) -> str:
        if ch not in texts:
            c = store.get_chapter(NOVEL, ch)
            texts[ch] = c.story_text if c else ""
            starts[ch] = _block_starts(store, NOVEL, ch)
        return texts[ch]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    main_path = out_dir / "human_review_200.csv"
    with main_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for i, (cat, r) in enumerate(sorted(chosen, key=lambda x: (x[1][1], x[1][2], x[1][3])), 1):
            _id, ch, block, off, text, alias_type, method, target = r
            t = chapter_text(ch)
            absolute = starts[ch].get(block, 0) + off
            candidates = sorted(label.get(x, x) for x in alias_targets.get(text.casefold(), set()))
            w.writerow({
                "sample_id": f"R{i:03d}", "chapter": f"{ch:g}", "source_text": _snippet(t, absolute, text),
                "mention": text,
                "predicted_entity": label.get(target, target) if target else "UNRESOLVED",
                "candidate_entities": "; ".join(candidates[:5]),
                "system_decision": f"{'LINK' if target else 'NO LINK'} ({method or 'none'}; {alias_type})",
                "reference_set_decision": silver_at.get((ch, absolute), "not in silver set"),
                "category": cat, "reviewer_label": "", "reviewer_notes": "",
            })

    hard = read_gold("data/gold/reverend-insanity-hardcases.jsonl", NOVEL).silver_only.entities_only
    hard_path = out_dir / "human_review_hardcases_88.csv"
    with hard_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for i, m in enumerate(hard.mentions, 1):
            note = m.note or ""
            w.writerow({
                "sample_id": f"H{i:03d}", "chapter": f"{m.chapter:g}",
                "source_text": _snippet(chapter_text(m.chapter), m.offset, m.surface),
                "mention": m.surface, "predicted_entity": "see data/eval/hardcase_resolution.json",
                "candidate_entities": "", "system_decision": "",
                "reference_set_decision": m.identity or "",
                "category": note[1:note.index("]")] if note.startswith("[") and "]" in note else "hard",
                "reviewer_label": "", "reviewer_notes": "",
            })
    store.close()

    counts: dict[str, int] = {}
    for cat, _ in chosen:
        counts[cat] = counts.get(cat, 0) + 1
    print(f"wrote {main_path} ({len(chosen)} rows): {counts}")
    print(f"wrote {hard_path} ({len(hard.mentions)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
