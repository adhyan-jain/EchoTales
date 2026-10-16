"""Score the anchored pronoun cue exactly as declared in docs/research/PREFIX_FAITHFULNESS/PREREG_ANCHORED.md.

    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/score_anchored.py

Builds compared on the same (character, cut) pairs where the combined reference label T* is male or female:
status quo (single first-sighting stamp), plain horizon repair, and the horizon repair with the anchored cue at each of six
settings. Leave-one-serial-out selection of the setting; H5 verdict. LABELS: MODEL-GENERATED. Reads files only.
"""

from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_labels2 as S  # noqa: E402

AUD, LAB, KNOWN = S.AUD, S.LAB, S.KNOWN
GRID = [(m, g) for m in (1, 2, 3) for g in (0.8, 1.0)]
WRONG_LIMIT = 0.03


def load(path: str) -> dict:
    d = json.load(open(path))
    return {(d["novel"], r["entity"], float(r["k"])): r for r in d["rows"] if r["key"] == "gender"}


def tally(vals: list[tuple[str, str]]) -> dict:
    """vals = (served, truth). Correct / withheld / wrong."""
    c = Counter(S.classify(s, t) for s, t in vals)
    n = len(vals)
    return dict(cuts=n, correct=c["correct"], withheld=c["withheld"], wrong=c["wrong"],
                correct_share=round(c["correct"] / n, 4) if n else None, wrong_share=round(c["wrong"] / n, 4) if n else None)


def main() -> None:
    mine = {}
    for nid in S.NOVELS:
        mine |= {k: v["label"] for k, v in json.load(open(LAB / f"truth_{nid}.json")).items() if not k.startswith("_")}
    lun = [json.loads(line) for line in (LAB / "luna_labels.jsonl").read_text().splitlines()]
    L_truth = {r["entity"]: r for r in lun if r["kind"] == "truth"}
    L_pre = {(r["novel"], r["entity"], float(r["k"])): r for r in lun if r["kind"] == "prefix"}
    reference = sys.argv[1] if len(sys.argv) > 1 else "combined"  # combined (declared) | mine | luna: sensitivity of the verdict
    if reference == "mine":
        tstar = {e: mine[e] for e in mine}
    elif reference == "luna":
        tstar = {e: L_truth[e]["label"] for e in L_truth}
    else:
        tstar = {e: S.combine(mine.get(e), L_truth[e]["label"])[0] for e in L_truth}

    off = S.rows("repair", "off") | S.rows("dense", "off")  # status quo
    plain = S.rows("repair", "on") | S.rows("dense", "on")  # plain horizon repair
    anch = {}
    for m, g in GRID:
        a: dict = {}
        for nid in S.NOVELS:
            a |= load(str(AUD / f"audit_anch{m}_{round(g * 100)}-on_{nid}.json"))
        anch[(m, g)] = a

    keys = set(off) & set(plain)
    for a in anch.values():
        keys &= set(a)
    keys = sorted(k for k in keys if tstar.get(k[1]) in KNOWN)
    out: dict = dict(labels="MODEL-GENERATED, two annotators (T* rule of PREREG_LABELS Addendum 2); no human labels",
                     pairs=len(keys), characters=len({k[1] for k in keys}),
                     divergence_stamp_vs_prefix_build={f"{m},{g}": sum(bool(a[k]["diverge"]) for k in a) for (m, g), a in anch.items()})

    def view(kind: str, ks: list) -> dict:
        t = lambda k: tstar[k[1]]  # noqa: E731
        if kind == "status_quo":
            return tally([(off[k]["full_value"], t(k)) for k in ks])
        if kind == "plain":
            return tally([(plain[k]["full_value"], t(k)) for k in ks])
        return tally([(anch[kind][k]["full_value"], t(k)) for k in ks])

    out["all_pairs"] = {"status_quo": view("status_quo", keys), "plain_repair": view("plain", keys)}
    for st in GRID:
        v = view(st, keys)
        sq, pl = out["all_pairs"]["status_quo"]["correct"], out["all_pairs"]["plain_repair"]["correct"]
        v["recovered_fraction"] = round((v["correct"] - pl) / (sq - pl), 4) if sq != pl else None
        out["all_pairs"][f"anchored_{st[0]}_{st[1]}"] = v

    # Leave-one-serial-out selection (declared)
    chosen, held = {}, {"status_quo": [], "plain": [], "chosen": []}
    for nid in S.NOVELS:
        rest = [k for k in keys if k[0] != nid]
        cand = []
        for st in GRID:
            v = view(st, rest)
            if v["wrong_share"] <= WRONG_LIMIT:
                cand.append((v["correct_share"], -v["wrong"], st[0], st))
        if not cand:
            chosen[nid] = None
            continue
        best = max(cand)[3]
        chosen[nid] = best
        mine_k = [k for k in keys if k[0] == nid]
        held["status_quo"] += [(off[k]["full_value"], tstar[k[1]]) for k in mine_k]
        held["plain"] += [(plain[k]["full_value"], tstar[k[1]]) for k in mine_k]
        held["chosen"] += [(anch[best][k]["full_value"], tstar[k[1]]) for k in mine_k]
    out["selected_setting_by_heldout_serial"] = {n: (None if s is None else list(s)) for n, s in chosen.items()}
    ho = {n: tally(v) for n, v in held.items()}
    if ho["status_quo"]["cuts"]:
        sq, pl, ch = ho["status_quo"]["correct"], ho["plain"]["correct"], ho["chosen"]["correct"]
        ho["recovered_fraction"] = round((ch - pl) / (sq - pl), 4) if sq != pl else None
    out["heldout_pooled"] = ho
    zero_div = all(v == 0 for v in out["divergence_stamp_vs_prefix_build"].values())
    rec = ho.get("recovered_fraction")
    wr = ho["chosen"]["wrong_share"] if ho["chosen"]["cuts"] else None
    out["H5"] = dict(a_zero_stamp_divergence=zero_div, b_recovered_ge_50pct=None if rec is None else rec >= 0.5,
                     c_wrong_le_3pct=None if wr is None else wr <= WRONG_LIMIT,
                     verdict="SUPPORTED" if zero_div and rec is not None and rec >= 0.5 and wr is not None and wr <= WRONG_LIMIT
                     else "NOT SUPPORTED (see which of a, b, c failed)")

    # Over-reading on the exposed pairs that carry a second-annotator prefix label (reported, not thresholded)
    over: dict = {}
    exp = [k for k in off if off[k]["exposed"] and k in L_pre and k in plain and all(k in a for a in anch.values())]
    und = lambda k: L_pre[k]["label"] not in KNOWN  # noqa: E731
    over["pairs"] = len(exp)
    over["status_quo"] = sum(off[k]["full_value"] in KNOWN and und(k) for k in exp)
    over["plain_repair"] = sum(plain[k]["full_value"] in KNOWN and und(k) for k in exp)
    for st in GRID:
        over[f"anchored_{st[0]}_{st[1]}"] = sum(anch[st][k]["full_value"] in KNOWN and und(k) for k in exp)
    out["over_reading_on_exposed_pairs_with_luna_prefix_label"] = over

    out["reference"] = reference
    (AUD / ("anchored_summary.json" if reference == "combined" else f"anchored_summary_{reference}.json")).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
