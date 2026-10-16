"""PD v6 (PREREG_PD_v6.md): final confirmatory test on 7 fresh books with every instrument fixed in advance.

Arms per real item: A (original names), B and B2 (two independent letter ciphers), B3 (cue-preserving natural pseudonyms,
PREREG_PD_v5). Per event: alias-only closed book (C_orig, C_ren, C_ren2) and the title-assisted probe M2 (PREREG_PD_v4,
M2_orig, M2_ren, M2_ren2). The 62-item synthetic unseen-text control is NOT re-run: G2b (A-vs-B agreement on unseen
synthetic items) is taken from each model's PD v3 run, which used the identical items and prompts. Validity gate G2:
B-vs-B2 on this set's real plain controls >= 90% AND the model's PD v3 synthetic A-vs-B >= 80%. Inference is event-cluster
(the resampling unit is the event). Local ollama (schema-constrained JSON) or Luna (budget-guarded, parsed JSON).

Commands: freeze | build | run --texts D --model M [--budget-usd X] | estimate | analyze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_llm_leakage as L1  # noqa: E402
import pd_reveal_benchmark as PD  # noqa: E402
import pd_v2 as V2  # noqa: E402
import pd_v3 as V3  # noqa: E402
import pd_v5_cuepres as V5  # noqa: E402

P = Path("docs/research/preregistrations")
EVENTS6 = P / "PD_events_v6_additions.json"
MANIFEST = P / "MANIFEST_PD_v6.json"
OUT = Path("data/eval/chimera/pd_v6")
V3.EVENT_FILES = [EVENTS6]  # pd_v3's builders read these module globals
V3.MANIFEST = MANIFEST
V3.OUT = OUT
OPTS = {"temperature": 0, "seed": 20261016, "num_predict": 24, "num_ctx": 2048}
CAP_OUT = 32
SEED = 20261019
REAL_ARMS, CLOSED_ARMS, M2_ARMS = ("A", "B", "B2", "B3"), ("C_orig", "C_ren", "C_ren2"), ("M2_orig", "M2_ren", "M2_ren2")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen():
    man = json.loads(MANIFEST.read_text())
    for name, h in man["inputs_sha256"].items():
        if sha(P / name) != h:
            sys.exit(f"REFUSING: {name} does not match MANIFEST_PD_v6.json")
    return man


def cmd_freeze(args):
    if MANIFEST.exists():
        sys.exit("REFUSING: manifest exists; a change is a new version")
    files = [EVENTS6, P / "PD_prompts_v1.json", P / "PD_prompts_v2.json", P / "PD_prompts_v4.json"]
    man = dict(frozen_for="PREREG_PD_v6.md", prereg_sha256=sha(P / "PREREG_PD_v6.md"),
               event_files_sha256={EVENTS6.name: sha(EVENTS6)},  # read by pd_v3.load_events
               inputs_sha256={f.name: sha(f) for f in files},
               script_sha256_at_freeze=sha(Path(__file__)))
    MANIFEST.write_text(json.dumps(man, indent=1))
    print("frozen", json.dumps(man, indent=1))


def prompts(texts: Path):
    check_frozen()
    real, cb = V3.prompts(texts)  # A, B, B2 + alias-only closed book, identical machinery to PD v3
    items, books = V3.build_items(texts)
    evs = {e["id"]: e for e in V3.load_events()}
    maps, audit = V5.build_maps(list(evs.values()), books)
    rn = V3.renamers_for(books)
    base_tpl = json.loads((P / "PD_prompts_v1.json").read_text())
    tail = json.loads((P / "PD_prompts_v2.json").read_text())
    for i, (row, it) in enumerate(zip(real, items)):
        assert row["id"] == it["id"]
        ev = evs[it["event"]]
        b3 = V5.make_b3(rn[ev["gutenberg"]][0], maps[ev["gutenberg"]])
        win = PD.window_for(books[ev["gutenberg"]], it)
        cl = PD.cand_letters(ev, i)
        row["B3"] = V2.tail_swap(L1.fill(base_tpl["A_B_prefix"], WINDOW=b3(win), SURFACE=b3(it["surface"]),
                                          CANDIDATES=L1.cand_block(cl, b3)), tail)
    m2tpl = json.loads((P / "PD_prompts_v4.json").read_text())["M2_title_assisted"]
    m2 = []
    for k, ev in enumerate(evs.values()):
        r1, r2 = rn[ev["gutenberg"]]
        cl = PD.cand_letters(ev, 9500 + k)
        letter_of = {n: L for L, n, _ in cl}
        surf = ev["alias"][0]
        row = dict(event=ev["id"], identity_letter=letter_of[ev["identity"]], cands=cl)
        row["M2_orig"] = L1.fill(m2tpl, BOOK=ev["book"], SURFACE=surf, CANDIDATES=L1.cand_block(cl))
        for arm, r in (("M2_ren", r1), ("M2_ren2", r2)):
            row[arm] = L1.fill(m2tpl, BOOK=ev["book"], SURFACE=r.rename(surf), CANDIDATES=L1.cand_block(cl, r.rename))
        m2.append(row)
    return real, cb, m2, audit


def jobs(real, cb, m2):
    out = [("real", p["id"], a, p[a], p["cands"]) for p in real for a in REAL_ARMS]
    out += [("closed", p["event"], a, p[a], p["cands"]) for p in cb for a in CLOSED_ARMS]
    out += [("m2", p["event"], a, p[a], p["cands"]) for p in m2 for a in M2_ARMS]
    return out


def parse(text, cands):
    m = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
    t = (m.group(1) if m else "").strip()
    return t if (t == "UNDETERMINED" or t in {L for L, _n, _i in cands}) else "INVALID"


def cmd_build(args):
    real, cb, m2, audit = prompts(Path(args.texts))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pseudonym_map_audit.json").write_text(json.dumps(audit, indent=1))
    from collections import Counter
    print(dict(Counter(p["kind"] for p in real)), len(cb), "closed", len(m2), "M2;", len(jobs(real, cb, m2)), "calls per model")


def cmd_estimate(args):
    real, cb, m2, _ = prompts(Path(args.texts))
    js = jobs(real, cb, m2)
    est_in = sum(L1.est_tokens(j[3]) for j in js)
    print(json.dumps(dict(calls=len(js), expected_usd=round(est_in * 0.8958 * L1.PRICE_IN + len(js) * 10 * L1.PRICE_OUT, 4),
                          worst_usd=round(est_in * 1.3 * L1.PRICE_IN + len(js) * CAP_OUT * L1.PRICE_OUT, 4))))


def cmd_run(args):
    import httpx

    real, cb, m2, _ = prompts(Path(args.texts))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"run_{args.model.replace(':', '_').replace('/', '_')}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    res = dict(model=args.model, real={}, closed={}, m2={}, status="COMPLETE")
    js = jobs(real, cb, m2)
    if args.model == "gpt-5.6-luna":
        if args.budget_usd is None:
            sys.exit("REFUSING: gpt-5.6-luna needs --budget-usd")
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            sys.exit("OPENAI_API_KEY is not set in the environment")
        budget = L1.Budget(args.budget_usd)
        with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as c:
            del key
            for sec, kid, arm, prompt, cands in js:
                if not budget.can(L1.est_tokens(prompt), CAP_OUT):
                    res["status"] = "STOPPED_AT_BUDGET"
                    break
                x = L1.call_model(c, prompt, CAP_OUT)
                budget.calls += 1
                budget.tok_in += x["tok_in"]
                budget.tok_out += x["tok_out"]
                budget.actual += x["tok_in"] * L1.PRICE_IN + x["tok_out"] * L1.PRICE_OUT
                res[sec].setdefault(kid, {})[arm] = parse(x["text"], cands)
        res.update(spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in, tok_out=budget.tok_out)
    else:
        host = "http://127.0.0.1:11434"
        with httpx.Client(timeout=240.0) as c:
            first = True
            for sec, kid, arm, prompt, cands in js:
                for ln in open("/proc/meminfo"):
                    if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 1.0:
                        sys.exit("stopping: available RAM below 1 GiB")
                allowed = [L for L, _n, _i in cands] + ["UNDETERMINED"]
                schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": allowed}}, "required": ["answer"]}
                x = c.post(f"{host}/api/chat", json=dict(model=args.model, stream=False, options=OPTS, format=schema,
                                                          messages=[dict(role="user", content=prompt)]))
                x.raise_for_status()
                try:
                    a = json.loads(x.json()["message"]["content"]).get("answer", "")
                except (ValueError, AttributeError):
                    a = "INVALID"
                res[sec].setdefault(kid, {})[arm] = a if a in allowed else "INVALID"
                if first:
                    ps = c.get(f"{host}/api/ps").json().get("models", [])
                    m = next((y for y in ps if y["name"] == args.model), None)
                    if m is None or m.get("size_vram", 0) < m.get("size", 1):
                        sys.exit(f"stopping: {args.model} not fully in VRAM; no CPU offload allowed")
                    first = False
            c.post(f"{host}/api/generate", json=dict(model=args.model, keep_alive=0, prompt=""))
    res["truth"] = {p["id"]: dict(truth_letter=p["truth_letter"], identity_letter=p["identity_letter"], kind=p["kind"],
                                  event=p["event"], distance=p["distance"], baseline_letter=p["baseline_letter"]) for p in real}
    res["closed_truth"] = {p["event"]: p["identity_letter"] for p in cb}
    res["m2_truth"] = {p["event"]: p["identity_letter"] for p in m2}
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "| status", res["status"], "| spent_usd", round(res.get("spent_usd", 0.0), 4))


# ---------------------------------------------------------------- analysis
def binom_k(n, p=1 / 8, alpha=0.05):
    for k in range(n + 1):
        if sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1)) <= alpha:
            return k
    return n + 1


def cluster(per_event, n=5000):
    """per_event: event -> list of dict(arm->0/1); pooled gaps A-B and A-B3, recovered fraction, event-cluster CIs, event sign test."""
    evs = sorted(per_event)

    def stat(es):
        rows = [x for e in es for x in per_event[e]]
        a, b, b3 = (sum(r[k] for r in rows) / len(rows) for k in ("A", "B", "B3"))
        return a - b, a - b3, ((b3 - b) / (a - b) if a - b > 1e-9 else float("nan"))

    pt = stat(evs)
    rng = random.Random(SEED)
    bs = [stat([rng.choice(evs) for _ in evs]) for _ in range(n)]
    ci = []
    for k in range(3):
        v = sorted(x[k] for x in bs if not math.isnan(x[k]))
        ci.append([round(v[int(0.025 * len(v))], 4), round(v[int(0.975 * len(v))], 4)] if v else [None, None])
    pos = sum(1 for e in evs if sum(r["A"] - r["B"] for r in per_event[e]) > 0)
    neg = sum(1 for e in evs if sum(r["A"] - r["B"] for r in per_event[e]) < 0)
    k = min(pos, neg)
    n_ = pos + neg
    p = min(1.0, 2 * sum(math.comb(n_, i) for i in range(k + 1)) / 2**n_) if n_ else 1.0
    return dict(events=len(evs), pairs=sum(len(v) for v in per_event.values()), gap_A_minus_B=round(pt[0], 4),
                gap_A_minus_B_ci=ci[0], gap_A_minus_B3=round(pt[1], 4), gap_A_minus_B3_ci=ci[1],
                recovered_fraction=round(pt[2], 4), recovered_fraction_ci=ci[2], events_positive=pos, events_negative=neg,
                event_sign_test_p=round(p, 5))


def cmd_analyze(args):
    runs = {}
    for f in sorted(OUT.glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    v3 = {}
    for f in sorted(Path("data/eval/chimera/pd_v3").glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            v3[r["model"]] = r
    out = dict(preregistration="PREREG_PD_v6.md", per_model={}, label_provenance="TEXT-DERIVED oracle; model-selected; no human labels")
    pool_rows = {}
    for m, r in runs.items():
        T = r["truth"]
        pre = [i for i, t in T.items() if t["kind"] == "pre"]
        ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
        g2a = sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl)
        S = v3[m]["synth_truth"] if m in v3 else {}
        sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
        g2b = (sum(v3[m]["synth"][i]["A"] == v3[m]["synth"][i]["B"] for i in sp) / len(sp)) if sp else float("nan")
        valid = bool(g2a >= 0.90 and g2b >= 0.80)
        rows = {}
        for i in pre:
            h = {arm: int(r["real"][i][arm] == T[i]["identity_letter"]) for arm in REAL_ARMS}
            h["B"] = (h["B"] + int(r["real"][i]["B2"] == T[i]["identity_letter"])) / 2
            rows.setdefault(T[i]["event"], []).append(h)
        n_ev = len(r["m2_truth"])
        k = binom_k(n_ev)
        m2c = {a: sum(r["m2"][e][a] == r["m2_truth"][e] for e in r["m2_truth"]) for a in M2_ARMS}
        cbc = {a: sum(r["closed"][e][a] == r["closed_truth"][e] for e in r["closed_truth"]) for a in CLOSED_ARMS}

        def acc(arm, r=r, T=T, ctrl=ctrl):
            return round(sum(r["real"][i][arm] == T[i]["truth_letter"] for i in ctrl) / len(ctrl), 4)

        out["per_model"][m] = dict(G2a=round(g2a, 4), G2b_from_v3=round(g2b, 4), G2_valid=valid, events=n_ev, k_needed=k,
                                   M2=m2c, M2_memory_present=m2c["M2_orig"] >= k, alias_only_closed_book=cbc,
                                   ctrl_acc={a: acc(a) for a in REAL_ARMS}, cluster=cluster(rows),
                                   invalid=sum(v == "INVALID" for d in r["real"].values() for v in d.values()))
        pool_rows[m] = (valid, rows)
    valid_models = [m for m, (v, _) in pool_rows.items() if v]
    pooled = {}
    for m in valid_models:
        for e, v in pool_rows[m][1].items():
            pooled.setdefault(e, []).extend(v)
    if pooled:
        st = cluster(pooled)
        mem_models = [m for m in valid_models if out["per_model"][m]["M2_memory_present"]]
        c1 = bool(st["gap_A_minus_B"] >= 0.10 and st["gap_A_minus_B_ci"][0] > 0)
        c2 = bool(st["gap_A_minus_B3"] >= 0.10 and st["gap_A_minus_B3_ci"][0] > 0)
        c3 = len(mem_models) >= 3
        verdict = ("INCONCLUSIVE (fewer than 3 valid models)" if len(valid_models) < 3 else
                   "SUPPORTED" if (c1 and c2 and c3) else "PARTIALLY SUPPORTED" if c1 else "NOT SUPPORTED")
        out["pool"] = dict(valid_models=valid_models, **st, memory_models=mem_models,
                           conditions=dict(i_gap_AB=c1, ii_gap_AB3_cue_preserving=c2, iii_M2_memory_in_3=c3), verdict=verdict)
    (OUT / "analysis.json").write_text(json.dumps(out, indent=1))
    for m, d in out["per_model"].items():
        c = d["cluster"]
        print(f"{m:22s} G2a {d['G2a']:.3f} G2b {d['G2b_from_v3']:.3f} valid {d['G2_valid']} | gapAB {c['gap_A_minus_B']:+.3f} {c['gap_A_minus_B_ci']} gapAB3 {c['gap_A_minus_B3']:+.3f} rec {c['recovered_fraction']:+.2f} | M2 {d['M2']} k{d['k_needed']} | ctrl {d['ctrl_acc']}")
    print(json.dumps(out.get("pool", {})))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("freeze", "build", "run", "estimate", "analyze"):
        s = sp.add_parser(n)
        if n in ("build", "run", "estimate"):
            s.add_argument("--texts", required=True)
        if n == "run":
            s.add_argument("--model", required=True)
            s.add_argument("--budget-usd", type=float, default=None)
    a = ap.parse_args()
    dict(freeze=cmd_freeze, build=cmd_build, run=cmd_run, estimate=cmd_estimate, analyze=cmd_analyze)[a.cmd](a)


if __name__ == "__main__":
    main()
