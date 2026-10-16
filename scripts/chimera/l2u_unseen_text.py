"""L2U: unseen-text control for the renaming gap (implements PREREG_L2U_unseen_text_control.md v1).

Synthetic worlds with invented names: no memory is possible, so an A-minus-B gap measures renaming damage alone.
Labels by construction (SYNTHETIC). Reuses the L1 machinery, the SIO generator and the T4 v5 cipher by import
(unedited). Only letters, hashes and counts are written; no novel text is involved.

  --dry-run   no key, no network: builds prompts, estimates tokens and cost
  --run       needs --budget-usd and OPENAI_API_KEY in the environment (never printed)
  --analyze   metrics and decision readings (needs the run output and the L1 results)

    python scripts/chimera/l2u_unseen_text.py --db <scratch RI copy> --dry-run --out data/eval/chimera/l2u_dryrun.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import l1_llm_leakage as L1  # noqa: E402
import sio_synthetic_oracle as S  # noqa: E402
import t4_renaming_v5 as V5  # noqa: E402

from echotales.core.enums import ReferenceMode  # noqa: E402

LETTERS = "ABCDEFGH"
DECOYS = ["Hadrin Colvane", "Pelle Orsk", "Vexin", "Mirabel Thorne", "Okwen", "Sorrel Quist"]
SEED_ITEM = 20261017


def tpl_v1() -> dict:
    man = json.loads(Path(L1.MANIFEST).read_text())
    raw = Path(L1.PROMPTS).read_bytes()
    if hashlib.sha256(raw).hexdigest() != man["prompts_file_sha256"]:
        sys.exit("REFUSING: L1_prompts_v1.json hash mismatch")
    return json.loads(raw)


def make_items() -> list[dict]:
    items: list[dict] = []
    n_plain = 0
    for seed in range(40):
        w = S.make_world(seed)
        rv0 = w.reveals[0]
        alias0 = rv0["alias"]
        chosen = []
        if seed <= 20:
            pre = next(m for m in w.mentions if m.kind == "pre_alias" and m.text.lower() == alias0)
            post = next(m for m in w.mentions if m.kind == "post_alias" and m.text.lower() == alias0
                        and m.chapter == rv0["r"] + 1)
            chosen += [("pre_alias", pre, "UNDETERMINED"), ("post_alias", post, w.names[rv0["y"]])]
        if seed >= 20 and n_plain < 20:
            ctl = next((m for m in w.mentions if m.kind == "control" and m.mode is ReferenceMode.PRESENT
                        and m.chapter >= 5 and m.text in w.names), None)
            if ctl is not None:
                chosen.append(("plain", ctl, ctl.text))
                n_plain += 1
        for kind, m, truth in chosen:
            items.append(dict(id=f"U{len(items):03d}", type=kind, seed=seed, world=w, chapter=float(m.chapter),
                              offset=m.offset, surface=m.text, truth=truth))
    return items


def build_prompts(items, tpl, protected):
    out = []
    for k, it in enumerate(items):
        w = it["world"]
        rng = random.Random(SEED_ITEM + k)
        cands = list(w.names) + rng.sample(DECOYS, 2)
        rng.shuffle(cands)
        cl = [(LETTERS[i], n, "0000") for i, n in enumerate(cands)]
        chapters = {float(n): t for n, t in w.chapters.items()}
        win, _ = L1.build_window(chapters, dict(id=it["id"], chapter=it["chapter"], offset=it["offset"],
                                                surface=it["surface"]))
        truth_letter = "UNDETERMINED" if it["truth"] == "UNDETERMINED" else next(L for L, n, _ in cl if n == it["truth"])
        vocab = {t for n in cands for t in L1.TOKEN.findall(n) if t[:1].isupper()}
        existing = {t.lower() for t in L1.TOKEN.findall(" ".join(w.chapters.values()))}
        pi = V5.CipherRenamerV5(vocab, protected, 20261015, existing)
        pa = L1.fill(tpl["A_B_prefix"], WINDOW=win, SURFACE=it["surface"], CANDIDATES=L1.cand_block(cl))
        pb = L1.fill(tpl["A_B_prefix"], WINDOW=pi.rename(win), SURFACE=pi.rename(it["surface"]),
                     CANDIDATES=L1.cand_block(cl, pi.rename))
        out.append(dict(id=it["id"], type=it["type"], truth_letter=truth_letter, cands=cl, A=pa, B=pb,
                        names_changed=sum(pi.rename(n) != n for n in cands)))
    return out


def dry_run(args, ps):
    n_in = sum(L1.est_tokens(p["A"]) + L1.est_tokens(p["B"]) for p in ps)
    n_calls = 2 * len(ps)
    exp_out = n_calls * 3
    worst_in, worst_out = n_in * 1.3, n_calls * L1.CAPS["A"]
    res = dict(mode="dry-run (no network, no key)", model=L1.MODEL, n_items=len(ps), calls=n_calls,
               by_type={t: sum(p["type"] == t for p in ps) for t in ("pre_alias", "post_alias", "plain")},
               items_where_renaming_changed_no_name=[p["id"] for p in ps if p["names_changed"] == 0],
               expected=dict(input_tokens=n_in, output_tokens=exp_out,
                             usd=n_in * L1.PRICE_IN + exp_out * L1.PRICE_OUT),
               worst_case=dict(input_tokens=int(worst_in), output_tokens=worst_out,
                               usd=worst_in * L1.PRICE_IN + worst_out * L1.PRICE_OUT,
                               assumption="every call at its max_completion_tokens cap; input 1.3x"),
               token_estimate_method=f"chars/{L1.CHARS_PER_TOKEN} + {L1.OVERHEAD_TOK} per call; ESTIMATE",
               prices_usd_per_1M=dict(input=0.20, output=1.20, source="OpenAI pricing page, fetched 2026-10-15"))
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


def live_run(args, ps):
    import httpx

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set in the environment")
    budget = L1.Budget(args.budget_usd)
    results: dict = {p["id"]: {} for p in ps}
    log: list = []
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as client:
        del key
        for arm in ("A", "B"):
            for p in ps:
                if not budget.can(L1.est_tokens(p[arm]), L1.CAPS["A"]):
                    Path(args.out).write_text(json.dumps(dict(status="STOPPED_AT_BUDGET", spent_usd=budget.actual,
                                                              results=results, log=log), indent=2))
                    sys.exit(f"stopping: next call could exceed the approved budget (spent ${budget.actual:.4f})")
                r = L1.call_model(client, p[arm], L1.CAPS["A"])
                budget.calls += 1
                budget.tok_in += r["tok_in"]
                budget.tok_out += r["tok_out"]
                budget.actual += r["tok_in"] * L1.PRICE_IN + r["tok_out"] * L1.PRICE_OUT
                results[p["id"]][arm] = L1.parse_letter(r["text"], p["cands"])
                log.append(dict(item=p["id"], arm=arm, tok_in=r["tok_in"], tok_out=r["tok_out"]))
    out = dict(status="COMPLETE", spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in,
               tok_out=budget.tok_out, results=results, log=log)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"complete. calls={budget.calls} tokens_in={budget.tok_in} tokens_out={budget.tok_out} "
          f"spent=${budget.actual:.4f}")


def boot_diff(a: list[int], b: list[int], seed: int, reps: int = 10000) -> list[float]:
    rng = random.Random(seed)
    n = len(a)
    return sorted(sum(a[i] - b[i] for i in (rng.randrange(n) for _ in range(n))) / n for _ in range(reps))


def analyze(args, ps):
    run = json.loads(Path(args.results).read_text())
    R = run["results"]
    l1 = json.loads(Path("data/eval/chimera/l1_results.json").read_text())["results"]
    syn_a = [int(R[p["id"]]["A"] == p["truth_letter"]) for p in ps]
    syn_b = [int(R[p["id"]]["B"] == p["truth_letter"]) for p in ps]
    plain = [p for p in ps if p["type"] == "plain"]
    same = sum(R[p["id"]]["A"] == R[p["id"]]["B"] for p in plain)
    gs_boot = boot_diff(syn_a, syn_b, 20261016)
    ns = len(syn_a)
    gs = sum(syn_a) / ns - sum(syn_b) / ns
    real_a = [int(l1[i]["A"] == t) for i, t in args.real_items]
    real_b = [int(l1[i]["B"] == t) for i, t in args.real_items]
    nr = len(real_a)
    gr = sum(real_a) / nr - sum(real_b) / nr
    rr, rs = random.Random(20261016), random.Random(20261017)
    dd = []
    for _ in range(10000):
        ir = [rr.randrange(nr) for _ in range(nr)]
        isy = [rs.randrange(ns) for _ in range(ns)]
        dd.append(sum(real_a[i] - real_b[i] for i in ir) / nr - sum(syn_a[i] - syn_b[i] for i in isy) / ns)
    dd.sort()
    D, lo, hi = gr - gs, dd[250], dd[9750]
    acc_a, acc_b = sum(syn_a) / ns, sum(syn_b) / ns
    ceiling = acc_a >= 0.95 and acc_b >= 0.95
    if gs >= 0.048 and lo <= 0 <= hi:
        reading = "(a) the real gap is consistent with renaming damage; leakage not supported"
    elif gs <= 0.02 and lo > 0:
        reading = ("(b) a residual gap on real text beyond renaming damage (consistent with memory; silver labels, "
                   "one model)" + ("; WEAKLY INFORMATIVE (ceiling on synthetic items)" if ceiling else ""))
    else:
        reading = "(c) inconclusive"
    by_type = {}
    for t in ("pre_alias", "post_alias", "plain"):
        idx = [i for i, p in enumerate(ps) if p["type"] == t]
        by_type[t] = dict(n=len(idx), A=sum(syn_a[i] for i in idx), B=sum(syn_b[i] for i in idx))
    out = dict(
        preregistration="PREREG_L2U_unseen_text_control.md v1",
        label_provenance="SYNTHETIC by construction (this side); SILVER (L1 real-text side)",
        status=run.get("status"), spent_usd=run.get("spent_usd"), calls=run.get("calls"),
        tokens=dict(input=run.get("tok_in"), output=run.get("tok_out")),
        U1_renaming_validity_synthetic_plain=dict(A_equals_B=L1.row(same, len(plain)), valid=(same == len(plain))),
        synthetic=dict(n=ns, acc_A=acc_a, acc_B=acc_b, gap_g_s=gs, gap_ci95=[gs_boot[250], gs_boot[9750]],
                       by_type=by_type, ceiling_both_arms_95=ceiling),
        real_L1=dict(n=nr, acc_A=sum(real_a) / nr, acc_B=sum(real_b) / nr, gap_g_r=gr),
        difference_in_differences=dict(D=D, ci95=[lo, hi]), reading=reading)
    Path(args.analysis_out).write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="SCRATCH RI copy (protected-word set and the real items)")
    ap.add_argument("--out", default="data/eval/chimera/l2u_results.json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--analyze", action="store_true")
    ap.add_argument("--budget-usd", type=float, default=0.0)
    ap.add_argument("--results", default="data/eval/chimera/l2u_results.json")
    ap.add_argument("--analysis-out", default="data/eval/chimera/l2u_analysis.json")
    args = ap.parse_args()
    if args.run and args.budget_usd <= 0:
        sys.exit("--run needs an explicit --budget-usd (the amount the owner approved)")
    tpl = tpl_v1()
    _pi, protected, _v, _s, _e = V5.build_v5(args.db)
    ps = build_prompts(make_items(), tpl, protected)
    if args.analyze:
        from echotales.core.store import Store

        args.real_items = [(i["id"], i["truth_letter"]) for i in L1.load_items(Store(args.db)) if i["truth_letter"]]
        return analyze(args, ps)
    (dry_run if args.dry_run else live_run)(args, ps)


if __name__ == "__main__":
    main()
