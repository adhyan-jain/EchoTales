"""Score the second text domain exactly as declared in docs/research/PREFIX_FAITHFULNESS/PREREG_PD.md (PD1, PD2, PD3).

    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/score_pd.py

Reference: gpt-5.6-luna, strict prompt, one annotator. LABELS: MODEL-GENERATED. Reads files only; no model call.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_labels2 as S  # noqa: E402

BOOKS = ("oliver-twist", "three-musketeers")
KN = S.KNOWN
BUILDS = {"status_quo": "audit_repair-off_{n}.json", "plain": "audit_repair-on_{n}.json",
          "anch_1_80": "audit_anch1_80-on_{n}.json", "anch_2_80": "audit_anch2_80-on_{n}.json"}


def load(name: str) -> dict:
    d = json.load(open(S.AUD / name))
    return {(d["novel"], r["entity"], float(r["k"])): r for r in d["rows"] if r["key"] == "gender"}


def lab(r: dict) -> str:
    return r["label"] if r["label"] in KN else "undetermined"


def main() -> None:
    lun = [json.loads(line) for line in (S.LAB / "luna_labels.jsonl").read_text().splitlines()]
    truth = {r["entity"]: r["label"] for r in lun if r["kind"] == "truth" and r["novel"] in BOOKS}
    pre = {(r["novel"], r["entity"], float(r["k"])): r for r in lun if r["kind"] == "prefix" and r["novel"] in BOOKS}
    out: dict = dict(labels="MODEL-GENERATED, one annotator (gpt-5.6-luna, strict prompt); no human labels", per_book={})
    pooled = {b: [] for b in BUILDS}
    pooled_cls = Counter()
    for nid in BOOKS:
        rows = {b: load(f.format(n=nid)) for b, f in BUILDS.items()}
        off = rows["status_quo"]
        res: dict = dict(character_cuts=len(off), characters=len({k[1] for k in off}), truth_distribution=dict(Counter(v for e, v in truth.items() if e.startswith(nid))))
        res["stamp_divergence_gender_pairs"] = {b: sum(bool(r["diverge"]) for r in rows[b].values()) for b in BUILDS}
        exp = [k for k, r in off.items() if r["exposed"] and r["diverge"] and k in pre]
        cls = Counter()
        for k in exp:
            s, p = off[k]["full_value"], lab(pre[k])
            cls["reverse" if s in (None, "unknown") else "premature" if p == "undetermined" else "justified" if p == s else "text_says_otherwise"] += 1
        res["diverging_pairs_labelled"] = len(exp)
        res["diverging_classes"] = dict(cls)
        pooled_cls.update(cls)
        keys = sorted(k for k in off if truth.get(k[1]) in KN and all(k in rows[b] for b in BUILDS))
        res["pairs_with_known_reference"] = len(keys)
        res["builds"] = {}
        for b in BUILDS:
            vals = [(rows[b][k]["full_value"], truth[k[1]]) for k in keys]
            c = Counter(S.classify(s, t) for s, t in vals)
            res["builds"][b] = dict(cuts=len(vals), correct=c["correct"], withheld=c["withheld"], wrong=c["wrong"],
                                    correct_share=round(c["correct"] / len(vals), 4) if vals else None)
            pooled[b] += vals
        out["per_book"][nid] = res
    pl = {}
    for b, vals in pooled.items():
        c = Counter(S.classify(s, t) for s, t in vals)
        n = len(vals)
        pl[b] = dict(cuts=n, correct=c["correct"], withheld=c["withheld"], wrong=c["wrong"], correct_share=round(c["correct"] / n, 4),
                     wrong_share=round(c["wrong"] / n, 4), correct_wilson95=S.wilson(c["correct"], n))
    sq, plain, a1 = pl["status_quo"], pl["plain"], pl["anch_1_80"]
    pl["recovered_fraction_anch_1_80"] = round((a1["correct"] - plain["correct"]) / (sq["correct"] - plain["correct"]), 4) if sq["correct"] != plain["correct"] else None
    out["pooled"] = pl
    out["pooled_diverging_classes"] = dict(pooled_cls)
    div = {b: sum(res["stamp_divergence_gender_pairs"][b] for res in out["per_book"].values()) for b in BUILDS}
    out["H"] = dict(
        PD1_status_quo_diverges=div["status_quo"] > 0,
        PD2_repairs_zero=all(div[b] == 0 for b in ("plain", "anch_1_80", "anch_2_80")),
        PD3_within_5_points_and_wrong_le_3pct=(sq["correct_share"] - a1["correct_share"] <= 0.05) and a1["wrong_share"] <= 0.03,
        divergence_by_build=div)
    (S.AUD / "labels_summary_pd.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
