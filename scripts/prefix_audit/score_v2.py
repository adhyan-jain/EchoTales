"""Score hypothesis H6 of PREREG_ANCHORED.md Addendum 1: cue window v2 against v1.

    /home/adhyan/Desktop/EchoTales/.venv/bin/python -I scripts/prefix_audit/score_v2.py

Confirmatory: the three web-novel serials, combined reference T* (PREREG_LABELS.md), 24 cuts. Development (reported, not
evidence): the two English books, Luna reference. Reads files only; no model call. LABELS: MODEL-GENERATED.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_labels2 as S  # noqa: E402

AUD, LAB, KN = S.AUD, S.LAB, S.KNOWN
SETTINGS = ((1, 0.8), (2, 0.8))
PD = ("oliver-twist", "three-musketeers")


def load(name: str) -> dict:
    d = json.load(open(AUD / name))
    return {(d["novel"], r["entity"], float(r["k"])): r for r in d["rows"] if r["key"] == "gender"}


def stats(vals: list[tuple[str, str]]) -> dict:
    c = Counter(S.classify(s, t) for s, t in vals)
    n = len(vals)
    return dict(cuts=n, correct=c["correct"], withheld=c["withheld"], wrong=c["wrong"], correct_share=round(c["correct"] / n, 4) if n else None)


def block(novels: tuple[str, ...], tstar: dict, off: dict, plain: dict) -> dict:
    """off and plain are baselines covering every cut that v1 and v2 cover."""
    v1 = {s: {} for s in SETTINGS}
    v2 = {s: {} for s in SETTINGS}
    for n in novels:
        for m, g in SETTINGS:
            v1[(m, g)] |= load(f"audit_anch{m}_{round(g * 100)}-on_{n}.json")
            v2[(m, g)] |= load(f"audit_anchv2_{m}_{round(g * 100)}-on_{n}.json")
    keys = set(plain) & set(off)
    for s in SETTINGS:
        keys &= set(v1[s]) & set(v2[s])
    keys = sorted(k for k in keys if tstar.get(k[1]) in KN)
    out = dict(pairs=len(keys), characters=len({k[1] for k in keys}),
               status_quo=stats([(off[k]["full_value"], tstar[k[1]]) for k in keys]),
               plain=stats([(plain[k]["full_value"], tstar[k[1]]) for k in keys]))
    added = [k for k in keys if plain[k]["full_value"] in (None, "unknown")]
    for s in SETTINGS:
        a = stats([(v1[s][k]["full_value"], tstar[k[1]]) for k in keys])
        b = stats([(v2[s][k]["full_value"], tstar[k[1]]) for k in keys])
        d1 = [k for k in added if v1[s][k]["full_value"] in KN]
        d2 = [k for k in added if v2[s][k]["full_value"] in KN]
        out[f"setting_{s[0]}_{s[1]}"] = dict(
            v1=a, v2=b,
            divergence_v2=sum(bool(r["diverge"]) for r in v2[s].values()),
            decisions_v1=dict(n=len(d1), correct=sum(v1[s][k]["full_value"] == tstar[k[1]] for k in d1)),
            decisions_v2=dict(n=len(d2), correct=sum(v2[s][k]["full_value"] == tstar[k[1]] for k in d2)),
            H6=dict(a_zero_divergence=all(not r["diverge"] for r in v2[s].values()),
                    b_correct_within_2_points=abs(b["correct_share"] - a["correct_share"]) <= 0.02,
                    c_no_more_wrong_than_v1=b["wrong"] <= a["wrong"]))
    return out


def main() -> None:
    mine = {}
    for n in S.NOVELS:
        mine |= {k: v["label"] for k, v in json.load(open(LAB / f"truth_{n}.json")).items() if not k.startswith("_")}
    lun = [json.loads(line) for line in (LAB / "luna_labels.jsonl").read_text().splitlines()]
    Lt = {r["entity"]: r["label"] for r in lun if r["kind"] == "truth"}
    web_t = {e: S.combine(mine.get(e), Lt[e])[0] for e in Lt if e.split(":")[0] in S.NOVELS}
    pd_t = {e: Lt[e] for e in Lt if e.split(":")[0] in PD}
    out: dict = dict(labels="MODEL-GENERATED; web novels: two annotators (combined T*), English originals: Luna only")
    out["confirmatory_web_novels"] = block(S.NOVELS, web_t, S.rows("repair", "off") | S.rows("dense", "off"),
                                           S.rows("repair", "on") | S.rows("dense", "on"))
    pd_off, pd_plain = {}, {}
    for n in PD:
        pd_off |= load(f"audit_repair-off_{n}.json")
        pd_plain |= load(f"audit_repair-on_{n}.json")
    out["development_english_originals"] = block(PD, pd_t, pd_off, pd_plain)
    verdict = {}
    for s in SETTINGS:
        h = out["confirmatory_web_novels"][f"setting_{s[0]}_{s[1]}"]["H6"]
        verdict[f"{s[0]},{s[1]}"] = "SUPPORTED" if all(h.values()) else "NOT SUPPORTED (" + ", ".join(k for k, v in h.items() if not v) + ")"
    out["H6_verdict_web_novels"] = verdict
    (AUD / "anchored_v2_summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
