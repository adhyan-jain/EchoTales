"""Premature-disclosure rate under three readers (PREREG_LABELS.md Addendum 3).

    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/score_permissive.py

Readers of "what does the text up to the cut determine": Luna with the strict prompt, Luna with the permissive prompt, and my
labels (46 original-cut items only). Same diverging (character, cut) pairs for the two Luna readers. Reads files only.
LABELS: MODEL-GENERATED.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_labels2 as S  # noqa: E402

KN = S.KNOWN


def load(name: str) -> dict:
    return {(r["novel"], r["entity"], float(r["k"])): r for r in map(json.loads, (S.LAB / name).read_text().splitlines()) if r["kind"] == "prefix"}


def lab(r: dict) -> str:
    return r["label"] if r["label"] in KN else "undetermined"


def classify(served, p) -> str:
    if served in (None, "unknown"):
        return "reverse"
    return "premature" if p == "undetermined" else "justified" if p == served else "text_says_otherwise"


def main() -> None:
    strict, perm = load("luna_labels.jsonl"), load("luna_labels_permissive.jsonl")
    off = S.rows("repair", "off") | S.rows("dense", "off")
    total_cuts = len(off)
    div = [k for k, r in off.items() if r["exposed"] and r["diverge"] and k in strict and k in perm]
    out: dict = dict(labels="MODEL-GENERATED; strict and permissive prompts are the same model (gpt-5.6-luna)",
                     permissive_records=len(perm), character_cuts=total_cuts, diverging_pairs=len(div))
    for name, src in (("luna_strict", strict), ("luna_permissive", perm)):
        c = Counter(classify(off[k]["full_value"], lab(src[k])) for k in div)
        out[name] = dict(classes=dict(c), premature_rate=S.rate(c["premature"], total_cuts), share_of_diverging_premature=round(c["premature"] / len(div), 4),
                         characters_premature=len({k[1] for k in div if classify(off[k]["full_value"], lab(src[k])) == "premature"}))
    # agreement between the two prompts on all 277 exposed pairs
    both = [k for k in strict if k in perm]
    out["agreement_strict_vs_permissive_all_pairs"] = dict(
        pairs=len(both), kappa=S.kappa([(lab(strict[k]), lab(perm[k])) for k in both]),
        permissive_known_strict_undetermined=sum(lab(perm[k]) in KN and lab(strict[k]) == "undetermined" for k in both),
        strict_known_permissive_undetermined=sum(lab(strict[k]) in KN and lab(perm[k]) == "undetermined" for k in both),
        contradictions=sum(lab(strict[k]) in KN and lab(perm[k]) in KN and lab(strict[k]) != lab(perm[k]) for k in both))
    # my 46 labels on the same pairs (original cuts only)
    key = {(i["novel"], i["entity"], float(i["k"])): i["item"] for i in json.load(open(S.LAB / "prefix_key.json"))}
    mine = {i["item"]: i["label"] for i in json.load(open(S.LAB / "prefix.json"))["items"]}
    dm = [k for k in div if k in key]
    cm = Counter(classify(off[k]["full_value"], mine[key[k]]) for k in dm)
    cs = Counter(classify(off[k]["full_value"], lab(strict[k])) for k in dm)
    cp = Counter(classify(off[k]["full_value"], lab(perm[k])) for k in dm)
    out["same_diverging_pairs_all_three_readers"] = dict(pairs=len(dm), mine=dict(cm), luna_strict=dict(cs), luna_permissive=dict(cp))
    # nesting: is every premature pair under the permissive prompt also premature under the strict one?
    pp = {k for k in div if classify(off[k]["full_value"], lab(perm[k])) == "premature"}
    sp = {k for k in div if classify(off[k]["full_value"], lab(strict[k])) == "premature"}
    out["nesting"] = dict(permissive_premature_subset_of_strict=pp <= sp, only_strict=len(sp - pp), only_permissive=len(pp - sp))
    (S.AUD / "labels_summary_permissive.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
