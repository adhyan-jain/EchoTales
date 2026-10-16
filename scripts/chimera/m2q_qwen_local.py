"""M2Q: arms A, B, closed-book and the unseen-text control on local qwen2.5:7b via ollama (PREREG_M2Q v1).

Local only (127.0.0.1), GPU only (stops if the model is not fully resident in VRAM), no API key, no spend.
Prompts are built in memory by importing the L1 and L2U machinery unchanged and are never written to disk; the repo
receives letters and counts only. LABELS: real items silver; synthetic items by construction.

    python scripts/chimera/m2q_qwen_local.py --db <scratch RI copy> --run --out data/eval/chimera/m2q_results.json
    python scripts/chimera/m2q_qwen_local.py --db <scratch RI copy> --analyze
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
import l1_llm_leakage as L1  # noqa: E402
import l2u_unseen_text as L2U  # noqa: E402
import t4_renaming_v5 as V5  # noqa: E402

from echotales.core.store import Store  # noqa: E402

HOST = "http://127.0.0.1:11434"
MODEL = "qwen2.5:7b"
OPTIONS = {"temperature": 0, "seed": 20261016, "num_predict": 8, "num_ctx": 4096}


def mem_available_gib() -> float:
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable:"):
            return int(ln.split()[1]) / 1024 / 1024
    return 99.0


def ask(client: httpx.Client, prompt: str) -> str:
    if mem_available_gib() < 1.0:
        sys.exit("stopping: available system RAM below 1 GiB")
    r = client.post(f"{HOST}/api/chat", json=dict(model=MODEL, stream=False, options=OPTIONS,
                                                   messages=[dict(role="user", content=prompt)]))
    r.raise_for_status()
    return r.json()["message"]["content"]


def parse(text: str, cands) -> str:
    m = re.match(r"\W*(UNDETERMINED|[A-Z])\b", text.strip())
    t = m.group(1) if m else ""
    return t if (t == "UNDETERMINED" or t in {L for L, _n, _i in cands}) else "INVALID"


def build(db: str):
    store = Store(db)
    tpl = L2U.tpl_v1()
    all_items = L1.load_items(store)
    items = [i for i in all_items if i["truth_letter"]]
    need = {it["chapter"] - k for it in all_items for k in range(0, 4)}
    chapters = {c.number: c.story_text for c in store.iter_chapters(L1.NOVEL) if c.number in need}
    pi3 = L1.build_pi(db)[0]
    real = {d["item"]["id"]: d for d in L1.build_prompts(all_items, chapters, pi3, tpl)}
    _prim, _ctrl, _oth, cb = L1.sets(all_items)
    protected = V5.build_v5(db)[1]
    syn = L2U.build_prompts(L2U.make_items(), tpl, protected)
    return items, real, {i["id"] for i in cb}, syn


def run(args) -> None:
    items, real, cb_ids, syn = build(args.db)
    results: dict = {"real": {i["id"]: {} for i in items}, "synth": {p["id"]: {} for p in syn}}
    with httpx.Client(timeout=120.0) as client:
        first = True
        for it in items:
            d = real[it["id"]]
            for arm in ("A", "B"):
                results["real"][it["id"]][arm] = parse(ask(client, d[arm]), it["cands"])
                if first:
                    ps = client.get(f"{HOST}/api/ps").json().get("models", [])
                    m = next((x for x in ps if x["name"].startswith("qwen2.5")), None)
                    if m is None or m.get("size_vram", 0) < m.get("size", 1):
                        sys.exit(f"stopping: model not fully resident in VRAM (size={m and m.get('size')}, "
                                 f"vram={m and m.get('size_vram')}); no CPU offload allowed")
                    first = False
        for it in items:
            if it["id"] in cb_ids:
                d = real[it["id"]]
                for arm in ("C_orig", "C_ren"):
                    results["real"][it["id"]][arm] = parse(ask(client, d[arm]), it["cands"])
        for p in syn:
            for arm in ("A", "B"):
                results["synth"][p["id"]][arm] = parse(ask(client, p[arm]), p["cands"])
    Path(args.out).write_text(json.dumps(dict(status="COMPLETE", model=MODEL, options=OPTIONS, results=results),
                                         indent=2))
    print("complete; calls =", 2 * len(items) + 2 * len([i for i in items if i["id"] in cb_ids]) + 2 * len(syn))


def boot_pair(a, b, seed, reps=10000):
    rng = random.Random(seed)
    n = len(a)
    return sorted(sum(a[i] - b[i] for i in (rng.randrange(n) for _ in range(n))) / n for _ in range(reps))


def analyze(args) -> None:
    run_ = json.loads(Path(args.results).read_text())
    R, SY = run_["results"]["real"], run_["results"]["synth"]
    store = Store(args.db)
    items = [i for i in L1.load_items(store) if i["truth_letter"]]
    prim = [i for i in items if i["tier"] == "P" and i["reveal_chapter"] is not None]
    ctrl = [i for i in items if i["category"] == "plain_control"]
    cb = [i for i in items if not i["string_trivial"] and "C_orig" in R[i["id"]]]
    out: dict = dict(preregistration="PREREG_M2Q_qwen_local.md v1", model=run_["model"], options=run_["options"],
                     label_provenance="real items SILVER; synthetic items by construction; no human label")
    same = sum(R[i["id"]]["A"] == R[i["id"]]["B"] for i in ctrl)
    valid = same == len(ctrl)
    a = [int(R[i["id"]]["A"] == i["truth_letter"]) for i in items]
    b = [int(R[i["id"]]["B"] == i["truth_letter"]) for i in items]
    bd = boot_pair(a, b, 20261016)
    gr = sum(a) / len(a) - sum(b) / len(b)
    n10 = sum(x == 1 and y == 0 for x, y in zip(a, b))
    n01 = sum(x == 0 and y == 1 for x, y in zip(a, b))
    out["R1_renaming_validity"] = dict(A_equals_B_on_plain_controls=L1.row(same, len(ctrl)), valid=valid)
    out["R2_real_gap"] = dict(acc_A=L1.row(sum(a), len(a)), acc_B=L1.row(sum(b), len(b)), gap=gr,
                              ci95=[bd[250], bd[9750]], discordant_A_right_B_wrong=n10,
                              discordant_B_right_A_wrong=n01,
                              replicates=bool(valid and gr >= 0.05 and bd[250] > 0))
    out["controls_accuracy"] = dict(A=L1.row(sum(R[i["id"]]["A"] == i["truth_letter"] for i in ctrl), len(ctrl)),
                                    B=L1.row(sum(R[i["id"]]["B"] == i["truth_letter"] for i in ctrl), len(ctrl)))
    out["R3_primary_counts"] = dict(n=len(prim), A=sum(R[i["id"]]["A"] == i["truth_letter"] for i in prim),
                                    B=sum(R[i["id"]]["B"] == i["truth_letter"] for i in prim))
    co = [int(R[i["id"]]["C_orig"] == i["truth_letter"]) for i in cb]
    cr = [int(R[i["id"]]["C_ren"] == i["truth_letter"]) for i in cb]
    chance = sum(1 / len(i["cands"]) for i in cb) / max(len(cb), 1)
    k = sum(co)
    p = L1.binom_tail_ge(k, len(co), chance)
    lo = L1.wilson(k, len(co))[0]
    out["R4_closed_book"] = dict(
        C_orig=L1.row(k, len(co)), C_ren=L1.row(sum(cr), len(cr)), chance=chance, exact_p_vs_chance=p,
        memory_consistent=bool(k >= 4 and p < 0.05 and lo > chance),
        abstain_orig=sum(R[i["id"]]["C_orig"] == "UNDETERMINED" for i in cb),
        invalid_orig=sum(R[i["id"]]["C_orig"] == "INVALID" for i in cb))
    syn_ps = L2U.build_prompts(L2U.make_items(), L2U.tpl_v1(), V5.build_v5(args.db)[1])
    sa = [int(SY[p_["id"]]["A"] == p_["truth_letter"]) for p_ in syn_ps]
    sb = [int(SY[p_["id"]]["B"] == p_["truth_letter"]) for p_ in syn_ps]
    gs = sum(sa) / len(sa) - sum(sb) / len(sb)
    sd = boot_pair(sa, sb, 20261016)
    rr, rs = random.Random(20261016), random.Random(20261017)
    nr, ns = len(a), len(sa)
    dd = sorted(sum(a[i] - b[i] for i in (rr.randrange(nr) for _ in range(nr))) / nr
                - sum(sa[i] - sb[i] for i in (rs.randrange(ns) for _ in range(ns))) / ns for _ in range(10000))
    D, lo_d, hi_d = gr - gs, dd[250], dd[9750]
    ceiling = sum(sa) / ns >= 0.95 and sum(sb) / ns >= 0.95
    if gs >= 0.5 * gr and gs >= 0.0 and lo_d <= 0 <= hi_d:
        reading = "(a) the real gap is consistent with renaming damage; leakage not supported"
    elif gs <= 0.02 and lo_d > 0:
        reading = "(b) a residual real-text gap beyond renaming damage (memory-consistent; silver, one model)" + (
            "; WEAKLY INFORMATIVE (ceiling)" if ceiling else "")
    else:
        reading = "(c) inconclusive"
    plain_syn = [p_ for p_ in syn_ps if p_["type"] == "plain"]
    out["R5_unseen_text"] = dict(
        synthetic_acc_A=sum(sa) / ns, synthetic_acc_B=sum(sb) / ns, synthetic_gap=gs,
        synthetic_gap_ci95=[sd[250], sd[9750]],
        synthetic_plain_A_equals_B=L1.row(sum(SY[p_["id"]]["A"] == SY[p_["id"]]["B"] for p_ in plain_syn),
                                          len(plain_syn)),
        real_gap=gr, difference_in_differences=D, did_ci95=[lo_d, hi_d], ceiling=ceiling, reading=reading,
        invalid_answers=sum(v == "INVALID" for r in list(R.values()) + list(SY.values()) for v in r.values()))
    Path(args.analysis_out).write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="data/eval/chimera/m2q_results.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", action="store_true")
    g.add_argument("--analyze", action="store_true")
    ap.add_argument("--results", default="data/eval/chimera/m2q_results.json")
    ap.add_argument("--analysis-out", default="data/eval/chimera/m2q_analysis.json")
    args = ap.parse_args()
    (run if args.run else analyze)(args)


if __name__ == "__main__":
    main()
