"""Analysis of an L1 run (implements the metrics and decision rules R1-R5 of PREREG_L1_llm_leakage.md v1).

Written BEFORE any L1 result existed, so the analysis is fixed in advance. LABEL PROVENANCE: silver only (model-drafted
gold; pipeline's own link for system-sourced items). Reveal chapters: repository structured data only. Nothing here is
human-verified and nothing is a reader-view accuracy.

    python scripts/chimera/l1_analyze.py --db <SCRATCH RI copy> --results data/eval/chimera/l1_results.json \
        --out data/eval/chimera/l1_analysis.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_llm_leakage as L1  # noqa: E402

from echotales.core.store import Store  # noqa: E402


def answer(res: dict, arm: str) -> str | None:
    """The arm's final letter; for D, an unaccepted link is UNDETERMINED."""
    if arm == "D":
        d = res.get("D")
        if d is None:
            return None
        return d["raw_answer"] if d["accepted"] else "UNDETERMINED"
    return res.get(arm)


def most_frequent_letter(store: Store, item: dict) -> str | None:
    """Always-most-frequent-candidate baseline: candidate with most pipeline mentions in chapters <= c (prefix-causal)."""
    best, best_n = None, -1
    for letter, _name, i4 in item["cands"]:
        n = store.conn.execute(
            "select count(*) from mention where novel_id=? and chapter<=? and target_id like ?",
            (L1.NOVEL, item["chapter"], f"%{i4}")).fetchone()[0]
        if n > best_n:
            best, best_n = letter, n
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    run = json.loads(Path(args.results).read_text())
    results = run["results"]
    store = Store(args.db)
    items = L1.load_items(store)
    prim, ctrl, other_p, cb = L1.sets(items)

    def correct(arm: str, subset: list[dict]) -> tuple[list[int], int]:
        flags, invalid = [], 0
        for it in subset:
            a = answer(results.get(it["id"], {}), arm)
            if a is None:
                continue
            invalid += a == "INVALID"
            flags.append(int(a == it["truth_letter"]))
        return flags, invalid

    out: dict = dict(
        label_provenance="SILVER (model-drafted gold / pipeline's own link); reveal chapters from repo data only; no human labels",
        run_status=run.get("status"), spent_usd=run.get("spent_usd"), calls=run.get("calls"),
        tokens=dict(input=run.get("tok_in"), output=run.get("tok_out")),
    )

    # R1 renaming validity on the 30 plain controls
    same = tot = 0
    for it in ctrl:
        r = results.get(it["id"], {})
        if "A" in r and "B" in r:
            tot += 1
            same += r["A"] == r["B"]
    valid = tot > 0 and same / tot >= 0.98
    out["R1_renaming_validity"] = dict(
        A_equals_B_on_plain_controls=L1.row(same, tot), valid=valid,
        interpretation="valid: A-vs-B and C_orig-vs-C_ren gaps may be interpreted" if valid
        else "INVALID: do not interpret A-vs-B or C_orig-vs-C_ren gaps")

    # controls accuracy per arm
    out["controls_accuracy_vs_silver"] = {}
    for arm in ("A", "B", "D"):
        f, inv = correct(arm, ctrl)
        out["controls_accuracy_vs_silver"][arm] = dict(**L1.row(sum(f), len(f)), invalid=inv)
    mf = [int(most_frequent_letter(store, it) == it["truth_letter"]) for it in ctrl]
    out["controls_accuracy_vs_silver"]["always_most_frequent_candidate"] = L1.row(sum(mf), len(mf))
    out["controls_accuracy_vs_silver"]["uniform_chance"] = sum(1 / len(it["cands"]) for it in ctrl) / max(len(ctrl), 1)

    # R2 primary, counts only
    r2 = dict(n=len(prim), items=[dict(id=i["id"], distance=i["reveal_chapter"] - i["chapter"]) for i in prim],
              events_by_arm={}, exact_95_upper_bound_if_zero=1 - 0.05 ** (1 / max(len(prim), 1)),
              reading="inconclusive by design (pre-registered); counts only")
    for arm in ("A", "B", "D"):
        ev = []
        for it in prim:
            a = answer(results.get(it["id"], {}), arm)
            ev.append(dict(id=it["id"], answer_is_silver_final_truth=(a == it["truth_letter"]),
                            abstained=(a == "UNDETERMINED")))
        r2["events_by_arm"][arm] = dict(k=sum(e["answer_is_silver_final_truth"] for e in ev), n=len(ev), per_item=ev)
    out["R2_primary_P_star"] = r2

    # leakage A - B (only interpretable if R1 valid)
    truth_items = [i for i in items if i["truth_letter"] and "A" in results.get(i["id"], {})
                   and "B" in results.get(i["id"], {})]
    a = [int(results[i["id"]]["A"] == i["truth_letter"]) for i in truth_items]
    b = [int(results[i["id"]]["B"] == i["truth_letter"]) for i in truth_items]
    out["leakage_A_minus_B_accuracy_vs_silver"] = dict(**L1.paired_bootstrap(a, b), interpretable=valid,
                                                       note="only interpretable if R1 is valid")

    # R3 closed-book
    co, inv_o = correct("C_orig", cb)
    cr, inv_r = correct("C_ren", cb)
    chance = sum(1 / len(it["cands"]) for it in cb) / max(len(cb), 1)
    k = sum(co)
    p = L1.binom_tail_ge(k, len(co), chance) if co else None
    lo = L1.wilson(k, len(co))[0] if co else None
    r3 = k >= 4 and p is not None and p < 0.05 and lo is not None and lo > chance
    mfc = [int(most_frequent_letter(store, it) == it["truth_letter"]) for it in cb]
    out["R3_closed_book"] = dict(
        C_orig=dict(**L1.row(k, len(co)), invalid=inv_o), C_ren=dict(**L1.row(sum(cr), len(cr)), invalid=inv_r),
        uniform_chance=chance, exact_one_sided_p_C_orig_vs_chance=p,
        always_most_frequent_candidate=L1.row(sum(mfc), len(mfc)),
        C_orig_minus_C_ren=L1.paired_bootstrap(co, cr), renaming_valid=valid, above_chance_without_passage=bool(r3),
        reading=("this model resolves aliases of this serial above chance with no passage (silver labels, one model, one serial)"
                 if r3 else "no evidence of memorisation for this model on these items; narrows the claim to this "
                            "model, does not kill it for larger models"),
        name_linked=("C_ren within chance and R1 valid" if (r3 and valid and sum(cr) < 4) else "not established"))

    # R4 gating
    ctrl_a = out["controls_accuracy_vs_silver"]["A"]["rate"]
    ctrl_d = out["controls_accuracy_vs_silver"]["D"]["rate"]
    gate_reasons: dict[str, int] = {}
    for r in results.values():
        d = r.get("D")
        if d:
            gate_reasons[d["gate"]] = gate_reasons.get(d["gate"], 0) + 1

    def abst(arm: str) -> int:
        return sum(answer(results.get(i["id"], {}), arm) == "UNDETERMINED" for i in prim)

    out["R4_gating"] = dict(
        controls_accuracy_D_minus_A=(None if ctrl_a is None or ctrl_d is None else ctrl_d - ctrl_a),
        within_5_points=(None if ctrl_a is None or ctrl_d is None else abs(ctrl_d - ctrl_a) <= 0.05),
        P_star_abstentions=dict(A=abst("A"), D=abst("D"), n=len(prim)), D_gate_outcomes=gate_reasons,
        reading="descriptive only on n = 4; any other pattern is reported as it is")

    # exploratory: other pre-reveal (no repo reveal chapter): descriptive, never called premature
    ex = {}
    for arm in ("A", "B", "D"):
        f, _ = correct(arm, [i for i in other_p if i["truth_letter"]])
        ex[arm] = L1.row(sum(f), len(f))
    out["exploratory_other_pre_reveal"] = dict(
        arms=ex, note="share of answers equal to the silver final identity; NOT premature resolution "
                      "(no repo reveal chapter for these items)")
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
