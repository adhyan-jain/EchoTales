"""Why each undetected hard case was missed -- a rule-based failure taxonomy.

`hardcase_resolution.py` showed the resolver links every decidable hard case
it sees (23/23) and that the loss is detection: 59 of 88 never become a
mention. This classifies those misses by what the surface *is*, so a fix can
be aimed at a class instead of a case, and so the classes that need new
coreference research are named rather than silently counted as "missed".

Modes, checked in this order (first match wins):

  gold-span-defect  the annotated surface is a clause, not a mention
                    ("he is really Fang Yuan", "his identity") -- no detector
                    could produce it; an annotation issue, left unedited
  pronoun           he / she / I / you / him / her -- by design never a graph
                    mention (anaphora links them locally, Phase 5)
  relational        kinship or household relation: "his uncle", "his uncle and
                    aunt", "his master", "the other master"
  address-term      vocative / honorific address: senior|junior brother,
                    young lord|master|landlord, Brother Bai
  definite-title    "the clan leader", "the previous landlord", "a clan leader"
  possessive-np     a name inside a possessive phrase the annotator took whole
                    ("big brother's", "Wang Da's true identity")
  rigid-name        a capitalised name the NER/gazetteer layers did not emit
  annotation-control  the hardcases file's one not_entity control record,
                    which carries an identity (GOLD_DATASET_README Section 5)
  other             anything else, printed so it can be read

Uses the overlap alignment from `hardcase_resolution.py` (which reproduces
scorer_diagnosis's 59), so "undetected" means no system span overlaps at all.

Usage:
    python3 scripts/hardcase_taxonomy.py [--db data/reruns/ner-window-ri.db]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from echotales.core.store import Store
from echotales.pipeline.eval.gold import SILVER_BANNER, read_gold
from hardcase_resolution import GOLD, NOVEL, _overlap, category

_PRONOUN = re.compile(r"^(?:he|she|him|her|his|i|me|you|they|them)$", re.IGNORECASE)
_KINSHIP = re.compile(
    r"\b(?:uncle|aunt|grandpa|grandfather|father|mother|cousin)\b"
    r"|^(?:his|her|the other)\s+master$",
    re.IGNORECASE,
)
_ADDRESS = re.compile(
    r"\b(?:senior brother|junior brother|young (?:lord|master|landlord)|brother \w+)\b",
    re.IGNORECASE,
)
_TITLE = re.compile(
    r"^(?:the|a|an|your)\s+(?:\w+\s+)?(?:clan leader|landlord|master|leader|elder)$", re.IGNORECASE
)
_CLAUSE_WORDS = {"is", "was", "really", "turned", "out", "to", "be", "identity", "fake", "true"}

MODES = ("annotation-control", "gold-span-defect", "pronoun", "relational", "address-term", "definite-title",
         "possessive-np", "rigid-name", "other")


def classify(surface: str) -> str:
    s = surface.strip()
    words = s.replace("’", "'").split()
    lowered = {w.lower().removesuffix("'s") for w in words}
    if len(words) >= 3 and lowered & _CLAUSE_WORDS and not _KINSHIP.search(s):
        return "gold-span-defect"
    if s.lower() == "his identity":
        return "gold-span-defect"
    if _PRONOUN.match(s):
        return "pronoun"
    if _KINSHIP.search(s):
        return "relational"
    if _ADDRESS.search(s):
        return "address-term"
    if _TITLE.match(s) or s.lower() in {"clan leader", "the clan leader"}:
        return "definite-title"
    if re.search(r"['’]s?\b", s) or s.endswith("’"):
        return "possessive-np"
    capitalised = [w for w in words if w[:1].isupper()]
    if words and words[0][:1].isupper() and len(capitalised) >= len(words) - 1:
        return "rigid-name"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/reruns/ner-window-ri.db")
    ap.add_argument("--out", default="data/eval/hardcase_taxonomy.json")
    args = ap.parse_args()

    store = Store(args.db)
    gold = read_gold(GOLD, novel_id=NOVEL).silver_only.entities_only
    aligned = _overlap(store, gold)
    store.close()

    records = []
    counts: Counter[str] = Counter()
    by_cat: dict[str, Counter[str]] = defaultdict(Counter)
    for m in gold.mentions:
        if not m.identity or aligned.get(m.key) is not None:
            continue
        cat = category(m.note)
        mode = "annotation-control" if cat == "not_entity_control" else classify(m.surface)
        counts[mode] += 1
        by_cat[cat][mode] += 1
        records.append({"chapter": m.chapter, "offset": m.offset, "surface": m.surface,
                        "category": cat, "mode": mode})

    print(SILVER_BANNER)
    print(f"undetected hard cases: {len(records)} (db {args.db})")
    for mode in MODES:
        if counts[mode]:
            print(f"  {mode:17} {counts[mode]:>3}")
    for r in records:
        if r["mode"] in ("other", "rigid-name"):
            print(f"    {r['mode']:10} ch{r['chapter']:g}@{r['offset']} {r['surface']!r}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "banner": SILVER_BANNER,
        "db": args.db,
        "undetected": len(records),
        "counts": {m: counts[m] for m in MODES if counts[m]},
        "by_category": {c: dict(v) for c, v in sorted(by_cat.items())},
        "records": records,
    }, indent=2) + "\n")
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
