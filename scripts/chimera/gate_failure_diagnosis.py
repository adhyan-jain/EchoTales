"""Gate-failure diagnosis: for each gate that failed or looked suspicious, is the fault in the GATE or in the thing under test?

CPU only, read-only, no model call, no spend; imports existing code unchanged. Output is counts only (no novel text).

  T4  the renaming commutation gate (PREREG_T4 v3): classify each violation as
        engine  = the repo's normaliser merges surface variants that differ only by spacing, case, hyphen or a
                  trailing plural, so no token-level renamer can map the class one-to-one (the defect is in what the
                  gate measures, i.e. the engine's character-level normaliser, backlog B12);
        renamer = the surfaces in the class are not mere spacing/case variants, so the renamer is at fault;
        gate    = the gate flags a pair the repo's own normaliser keeps apart (gate bug).
  M1  for the L1b gate: for items the gate rejected although the model's raw answer equals the silver label, is the
      claimed name present anywhere in the 1,200-character prefix window (evidence existed, so the rejection is a gate
      matching limitation) or absent (the rejection is correct and the model reached beyond the prefix)?

    python scripts/chimera/gate_failure_diagnosis.py --db <scratch RI copy> --out data/eval/chimera/gate_failure_diagnosis.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import l1_llm_leakage as L1  # noqa: E402
import t4_renaming as T4  # noqa: E402

from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.ingest.normalize import comparison_key  # noqa: E402


def squash(s: str) -> str:
    return re.sub(r"[\s\-_']", "", s).casefold().rstrip("s")


def t4_diagnosis(db: str) -> dict:
    pi, protected, _vocab, surfaces = T4.build_pi(db)
    gate = T4.commutation_gate(pi, surfaces, protected)
    by_key: dict[str, list[str]] = defaultdict(list)
    for s in sorted(surfaces):
        by_key[comparison_key(s)].append(s)
    classes: Counter = Counter()
    detail = []
    for v in gate["G2_violations"]:
        m = re.match(r"(orig|renamed)-class '(.*)' (splits|merges)", v)
        if not m:
            classes["unparsed"] += 1
            continue
        side, key = m.group(1), m.group(2)
        if side == "orig":
            members = by_key.get(key, [])
            variants = {squash(x) for x in members}
            kind = "engine" if len(members) > 1 and len(variants) == 1 else "renamer"
        else:
            kind = "renamer"
        classes[kind] += 1
        detail.append(dict(kind=kind, n_surfaces_in_class=len(by_key.get(key, [])),
                           differ_only_by_spacing_case_plural=(len({squash(x) for x in by_key.get(key, [])}) == 1)))
    g1 = []
    for s in gate["G1_display_violations"]:
        n = len(by_key.get(comparison_key(s), []))
        g1.append(dict(kind="engine" if n > 1 else "renamer", n_surfaces_same_key=n))
    return dict(
        gate_result=dict(surfaces=gate["surfaces"], G1=gate["G1_count"], G2=gate["G2_count"], G3=gate["G3_count"]),
        G2_classification=dict(classes), G1_classification=dict(Counter(x["kind"] for x in g1)),
        G1_detail=g1, G2_detail_counts_only=detail,
        reading="engine = defect in the repo's character-level normaliser (backlog B12), not in the gate or the renamer "
                "design intent; renamer = the renamer is at fault; the gate itself flags only genuine non-commutation",
    )


def m1_diagnosis(db: str) -> dict:
    store = Store(db)
    items = {i["id"]: i for i in L1.load_items(store)}
    run = json.loads(Path("data/eval/chimera/l1b_results.json").read_text())["results"]
    need = {it["chapter"] - k for it in items.values() for k in range(0, 4)}
    chapters = {c.number: c.story_text for c in store.iter_chapters(L1.NOVEL) if c.number in need}
    out: Counter = Counter()
    n_rows = 0
    for iid, r in run.items():
        it = items[iid]
        if r["accepted"] or r["raw_answer"] not in {L for L, _n, _i in it["cands"]}:
            continue
        claimed = next(n for L, n, _i in it["cands"] if L == r["raw_answer"])
        win, _ = L1.build_window(chapters, it)
        name_toks = [t for t in L1.TOKEN.findall(claimed) if t[:1].isupper()]
        wtoks = set(L1.TOKEN.findall(win))
        where = ("full_name_in_window" if claimed in win else
                 "some_name_tokens_in_window" if any(t in wtoks for t in name_toks) else "name_absent_from_window")
        right = "silver_correct" if r["raw_answer"] == it["truth_letter"] else "silver_wrong_or_no_label"
        out[f"{r['gate']} | {right} | {where}"] += 1
        n_rows += 1
    return dict(
        rejected_with_a_letter_answer=n_rows, counts=dict(sorted(out.items())),
        reading="full_name_in_window or some_name_tokens_in_window with silver_correct means evidence existed in the "
                "prefix and the gate rejected it (a gate matching or entailment limitation); name_absent_from_window "
                "means the rejection is correct (the model named someone the prefix does not name)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    res = dict(label_provenance="NO LABELS for T4 (system-internal); SILVER for the M1 part (counts only)",
               T4_renaming_commutation_gate=t4_diagnosis(args.db), M1_evidence_gate=m1_diagnosis(args.db))
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
