"""POST HOC: how much do model-mined events whose "identity" is a description rather than a name move the results?

Why this exists: preparing the journal revision, reading the 24 alias-merged events of the selection-leak test showed
that the confirmatory miner sometimes returned a descriptive phrase as the identity ("the son of a long-descended
English peer", "a Greek"). The course report quoted a sensitivity (+15.9 [+2.9, +30.4] over 23 events) that came from
excluding one such event by hand and was never stored. This script replaces it with a fixed rule, applied to every
analysis that uses the confirmatory events, and stores the result so the manuscript can cite a file:

  descriptive identity  <=>  the identity string starts with an article or pronoun (the, a, an, him, his, her, one).

It recomputes, with the stored labels and the original estimators only (no model calls): the selection-leak contrast
(rf_selection.cmd_analyze logic, pd_rf_e2e.boot) and the confirmatory H1 per-model gaps and random-effects pool
(pd_confirm_analyze functions) with descriptive-identity events removed.

Output: data/eval/chimera/posthoc_descriptive_identity.json
Run   : python scripts/paper/posthoc_descriptive_identity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts/chimera")
import pd_confirm_analyze as CA  # noqa: E402
import pd_rf_e2e as R  # noqa: E402

EVENTS = Path("docs/research/preregistrations/PD_confirm_events_v1.json")
SEL = Path("data/eval/chimera/rf_e2e")
OUT = Path("data/eval/chimera/posthoc_descriptive_identity.json")
DESCRIPTIVE_START = {"the", "a", "an", "him", "his", "her", "one"}


def descriptive(ev) -> bool:
    return ev["identity"].split()[0].lower() in DESCRIPTIVE_START


def selection(exclude: set[str]):
    res_lab = json.loads((SEL / "selection_resolver.json").read_text())["labels"]
    per = {}
    for f in sorted(SEL.glob("judge_qwen3_8b_of_*_selection.json")):
        d = json.loads(f.read_text())
        m = d["of"]
        old = json.loads((SEL / f"judge_qwen3_8b_of_{m.replace(':', '_')}.json").read_text())["labels"]
        per[m] = {i: dict(M=d["labels"][i]["M_ren"], P=old[i]["P_ren"]) for i in d["labels"] if i in old}
    models = sorted(per)
    ids = sorted(set.intersection(*[{i for i, v in per[m].items() if v["M"] is not None and v["P"] is not None} for m in models]))
    ids = [i for i in ids if res_lab.get(i) and i not in exclude]
    pe = {i: dict(M=sum(float(per[m][i]["M"]) for m in models) / len(models),
                  P=sum(float(per[m][i]["P"]) for m in models) / len(models)) for i in ids}
    pt, lo, hi = R.boot(pe, lambda xs: sum(x["M"] - x["P"] for x in xs) / len(xs))
    return dict(events=len(ids), M_rate=round(sum(v["M"] for v in pe.values()) / len(ids), 4),
                P_rate=round(sum(v["P"] for v in pe.values()) / len(ids), 4), estimate=round(pt, 4), ci=[round(lo, 4), round(hi, 4)])


def confirmatory_h1(exclude: set[str]):
    by = {e["id"]: e for e in json.loads(EVENTS.read_text())["events"]}
    ys, vs, per_model = [], [], {}
    for m, r in CA.load_e1(CA.OUT / "main").items():
        rows = {e: v for e, v in CA.event_rows(r, by, "test", True).items() if e not in exclude}
        pt, lo, hi, var, _ = CA.boot_events(rows, CA.gap_stat("B"))
        per_model[m] = dict(events=len(rows), gap_A_minus_B=round(pt, 4), ci=[round(lo, 4), round(hi, 4)])
        ys.append(pt)
        vs.append(max(var, 1e-6))
    th, lo, hi, tau2, p = CA.dl_hk(ys, vs)
    return dict(per_model=per_model, H1_pooled=round(th, 4), ci=[round(lo, 4), round(hi, 4)], p_one_sided=None if p is None else round(p, 4))


def main():
    evs = json.loads(EVENTS.read_text())["events"]
    desc = {e["id"] for e in evs if descriptive(e)}
    prim = [e for e in evs if e["split"] == "test" and e["audit"] == "EXPLICIT"]
    out = dict(
        note="POST HOC; rule fixed before recomputation; stored labels and original estimators only; no model calls",
        rule="identity starts with one of: " + ", ".join(sorted(DESCRIPTIVE_START)),
        descriptive_events_all=sorted(desc), descriptive_count_all=f"{len(desc)}/{len(evs)}",
        descriptive_count_primary=f"{sum(e['id'] in desc for e in prim)}/{len(prim)}",
        selection_leak=dict(as_reported=selection(set()), excluding_descriptive=selection(desc)),
        confirmatory_H1=dict(as_reported=confirmatory_h1(set()), excluding_descriptive=confirmatory_h1(desc)),
    )
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
