"""Score the audit against the MODEL-GENERATED labels (docs/research/PREFIX_FAITHFULNESS/PREREG_LABELS.md, metrics A-D).

    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/score_labels.py

Run only after the label files are frozen (data/eval/prefix_audit/labels/LABELS.sha256). Reads audit rows; no model call.
LABELS: MODEL-GENERATED, one annotator, no human review.
"""

from __future__ import annotations

import glob
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUD = ROOT / "data" / "eval" / "prefix_audit"
LAB = AUD / "labels"
NOVELS = ("lord-of-the-mysteries", "omniscient-readers-viewpoint", "reverend-insanity")


def wilson(k: int, n: int, z: float = 1.96) -> list[float | None]:
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def frozen_ok() -> bool:
    want = dict(line.split()[::-1] for line in (LAB / "LABELS.sha256").read_text().splitlines() if line.strip())
    return all(hashlib.sha256((LAB / n).read_bytes()).hexdigest() == h for n, h in want.items())


def load_rows(repair: str) -> dict[tuple[str, str, float], dict]:
    out: dict = {}
    for nid in NOVELS:
        d = json.load(open(AUD / f"audit_repair-{repair}_{nid}.json"))
        for r in d["rows"]:
            if r["key"] == "gender":
                out[(nid, r["entity"], float(r["k"]))] = r
    return out


def classify(served: str | None, truth: str) -> str:
    if served in (None, "unknown"):
        return "withheld"
    return "correct" if served == truth else "wrong"


def tally(items: list[str]) -> dict:
    n, c = len(items), Counter(items)
    return {x: dict(n=c[x], share=round(c[x] / n, 4) if n else None, wilson95=wilson(c[x], n)) for x in ("correct", "withheld", "wrong")} | {"cuts": n}


def main() -> None:
    assert frozen_ok(), "label files changed after they were frozen; refusing to score"
    truth = {}
    for nid in NOVELS:
        truth |= {k: v["label"] for k, v in json.load(open(LAB / f"truth_{nid}.json")).items() if not k.startswith("_")}
    off, on = load_rows("off"), load_rows("on")
    key = {i["item"]: i for i in json.load(open(LAB / "prefix_key.json"))}
    plab = {i["item"]: i["label"] for i in json.load(open(LAB / "prefix.json"))["items"]}
    out: dict = dict(labels="MODEL-GENERATED, one annotator, frozen by sha256", truth_distribution=dict(Counter(truth.values())))

    # D. label sanity
    out["D_truth_unknown_share"] = round(sum(v in ("unknown", "non-person") for v in truth.values()) / len(truth), 4)
    clash = [(i, plab[i], truth[key[i]["entity"]]) for i in key if plab[i] in ("male", "female") and truth.get(key[i]["entity"]) in ("male", "female") and plab[i] != truth[key[i]["entity"]]]
    out["D_prefix_vs_truth_clash"] = clash

    # A. justification of the leak, over the diverging cuts in the prefix sheet
    A: Counter = Counter()
    detail = []
    for i, it in key.items():
        if not it["diverge"]:
            continue
        r = off[(it["novel"], it["entity"], float(it["k"]))]
        s, p = r["full_value"], plab[i]
        cls = ("served_unknown_or_none" if s in (None, "unknown") else "premature_disclosure" if p == "undetermined"
               else "justified_by_text" if p == s else "text_says_otherwise")
        A[cls] += 1
        detail.append(dict(item=i, entity=it["entity"], k=it["k"], served=s, prefix_build=r["prefix_value"], text_label=p, truth=truth.get(it["entity"]), cls=cls))
    out["A_diverging_cuts"] = dict(n=sum(A.values()), classes=dict(A), characters=len({d["entity"] for d in detail}), detail=detail)

    # B/C. correctness against the truth label
    def correctness(rows_for_full, rows_for_rep, exposed_only: bool) -> dict:
        sel = [k for k in rows_for_full if truth.get(k[1]) in ("male", "female") and (rows_for_full[k]["exposed"] or not exposed_only)]
        t = lambda k: truth[k[1]]  # noqa: E731
        return dict(
            characters=len({k[1] for k in sel}),
            status_quo=tally([classify(rows_for_full[k]["full_value"], t(k)) for k in sel]),
            prefix_only_build=tally([classify(rows_for_full[k]["prefix_value"], t(k)) for k in sel]),
            repaired=tally([classify(rows_for_rep[k]["full_value"], t(k)) for k in sel if k in rows_for_rep]),
        )

    out["B_exposed_cuts"] = correctness(off, on, True)
    out["B_all_cuts"] = correctness(off, on, False)
    excl = Counter(truth.get(k[1], "unlabelled") for k in off if off[k]["exposed"] and truth.get(k[1]) not in ("male", "female"))
    out["B_exposed_cuts_excluded_for_unknown_truth"] = dict(excl)

    # status-quo value that the prefix-only build does not hold, split by truth: leak of a TRUE value vs a corrupted one
    leak = Counter()
    for k, r in off.items():
        if r["diverge"] and truth.get(k[1]) in ("male", "female"):
            leak[classify(r["full_value"], truth[k[1]]) + "|prefix_" + classify(r["prefix_value"], truth[k[1]])] += 1
    out["C_diverging_cuts_by_correctness"] = dict(leak)

    (AUD / "labels_summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "A_diverging_cuts"} | {"A": {k: v for k, v in out["A_diverging_cuts"].items() if k != "detail"}}, indent=1))


if __name__ == "__main__":
    main()
