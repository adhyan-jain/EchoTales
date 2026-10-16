"""PD v4 (PREREG_PD_v4.md): title-assisted closed-book memory probe M2 and the memory-free validity gate G2, applied as a
pre-registered RE-EVALUATION of the v2 and v3 leakage results.

Why: v3 conditions (i) and (ii) held but condition (iii) failed because the alias-only closed-book probe under-detects
memory (most models name 2-3 of 12 events), and the A-vs-B renaming gate is partly memory. M2 gives the model the novel's
title with the alias (no passage) to measure whether it can map the alias to the cast at all; renamed arms keep the title
but rename the alias and the candidates. G2 = B-vs-B2 agreement on real plain controls >= 90% AND A-vs-B agreement on
unseen synthetic items >= 80% (no original-name arm in the first, no real text in the second).

Commands: freeze | build | run --model M [--budget-usd X for gpt-5.6-luna] | estimate (Luna cost) | analyze.
The v2 / v3 leakage items are NOT re-run; only the 31 closed-book memory events are (31 x 3 calls per model).
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

P = Path("docs/research/preregistrations")
V23_FILES = [P / "PD_events_v1.json", P / "PD_events_v2_additions.json"]
V3_FILE = P / "PD_events_v3_additions.json"
PROMPTS_V4 = P / "PD_prompts_v4.json"
MANIFEST = P / "MANIFEST_PD_v4.json"
OUT = Path("data/eval/chimera/pd_v4")
G2A_BAR, G2B_BAR = 0.90, 0.80
OPTS = {"temperature": 0, "seed": 20261016, "num_predict": 24, "num_ctx": 2048}
CAP_OUT = 32


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_events() -> list[dict]:
    man = json.loads(MANIFEST.read_text())
    evs = []
    for f in V23_FILES + [V3_FILE]:
        if sha(f) != man["event_files_sha256"][f.name]:
            sys.exit(f"REFUSING: {f.name} does not match MANIFEST_PD_v4.json")
        evs += json.loads(f.read_text())["events"]
    return evs


def load_template() -> str:
    if sha(PROMPTS_V4) != json.loads(MANIFEST.read_text())["prompts_v4_sha256"]:
        sys.exit("REFUSING: PD_prompts_v4.json does not match MANIFEST_PD_v4.json")
    return json.loads(PROMPTS_V4.read_text())["M2_title_assisted"]


def prompts(texts: Path):
    tpl = load_template()
    evs = load_events()
    books = {}
    for ev in evs:
        books.setdefault(ev["gutenberg"], PD.load_text(texts, ev["gutenberg"]))
    rn = V2.renamers_for(books)
    out = []
    for k, ev in enumerate(evs):
        r1, r2 = rn[ev["gutenberg"]]
        cl = PD.cand_letters(ev, 9500 + k)
        letter_of = {n: L for L, n, _ in cl}
        surf = ev["alias"][0]
        row = dict(event=ev["id"], identity_letter=letter_of[ev["identity"]], cands=cl)
        row["M2_orig"] = L1.fill(tpl, BOOK=ev["book"], SURFACE=surf, CANDIDATES=L1.cand_block(cl))
        for arm, r in (("M2_ren", r1), ("M2_ren2", r2)):
            row[arm] = L1.fill(tpl, BOOK=ev["book"], SURFACE=r.rename(surf), CANDIDATES=L1.cand_block(cl, r.rename))
        out.append(row)
    return out


def cmd_freeze(args):
    if MANIFEST.exists():
        sys.exit("REFUSING: manifest exists; a change is a new version")
    man = dict(frozen_for="PREREG_PD_v4.md",
               event_files_sha256={f.name: sha(f) for f in V23_FILES + [V3_FILE]},
               prompts_v4_sha256=sha(PROMPTS_V4), prereg_sha256=sha(P / "PREREG_PD_v4.md"),
               script_sha256_at_freeze=sha(Path(__file__)))
    MANIFEST.write_text(json.dumps(man, indent=1))
    print("frozen", json.dumps(man, indent=1))


def cmd_build(args):
    rows = prompts(Path(args.texts))
    print(len(rows), "events;", "longest prompt chars", max(len(r["M2_orig"]) for r in rows))


def parse(text, cands):
    m = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
    t = (m.group(1) if m else "").strip()
    return t if (t == "UNDETERMINED" or t in {L for L, _n, _i in cands}) else "INVALID"


def jobs_for(rows):
    return [(r["event"], arm, r[arm], r["cands"]) for r in rows for arm in ("M2_orig", "M2_ren", "M2_ren2")]


def cmd_estimate(args):
    rows = prompts(Path(args.texts))
    jobs = jobs_for(rows)
    est_in = sum(L1.est_tokens(j[2]) for j in jobs)
    k = 0.8958  # actual/estimated input tokens measured on the v1 Luna run (see pd_v2_luna.py)
    exp_in, exp_out = math.ceil(est_in * k), len(jobs) * 10
    worst_in = math.ceil(est_in * 1.3)
    print(json.dumps(dict(calls=len(jobs),
                          expected=dict(input_tokens=exp_in, output_tokens=exp_out,
                                        usd=round(exp_in * L1.PRICE_IN + exp_out * L1.PRICE_OUT, 5)),
                          worst_case=dict(input_tokens=worst_in, output_tokens=len(jobs) * CAP_OUT,
                                          usd=round(worst_in * L1.PRICE_IN + len(jobs) * CAP_OUT * L1.PRICE_OUT, 5))), indent=1))


def run_luna(args, rows, res):
    import httpx

    if args.budget_usd is None:
        sys.exit("REFUSING: gpt-5.6-luna needs --budget-usd")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set in the environment")
    budget = L1.Budget(args.budget_usd)
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as c:
        del key
        for ev, arm, prompt, cands in jobs_for(rows):
            if not budget.can(L1.est_tokens(prompt), CAP_OUT):
                res["status"] = "STOPPED_AT_BUDGET"
                break
            r = L1.call_model(c, prompt, CAP_OUT)
            budget.calls += 1
            budget.tok_in += r["tok_in"]
            budget.tok_out += r["tok_out"]
            budget.actual += r["tok_in"] * L1.PRICE_IN + r["tok_out"] * L1.PRICE_OUT
            res["probe"].setdefault(ev, {})[arm] = parse(r["text"], cands)
    res.update(spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in, tok_out=budget.tok_out)


def run_local(args, rows, res):
    import httpx

    host = "http://127.0.0.1:11434"
    with httpx.Client(timeout=240.0) as c:
        first = True
        for ev, arm, prompt, cands in jobs_for(rows):
            for ln in open("/proc/meminfo"):
                if ln.startswith("MemAvailable:") and int(ln.split()[1]) / 1048576 < 1.0:
                    sys.exit("stopping: available RAM below 1 GiB")
            allowed = [L for L, _n, _i in cands] + ["UNDETERMINED"]
            schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": allowed}},
                      "required": ["answer"]}
            r = c.post(f"{host}/api/chat", json=dict(model=args.model, stream=False, options=OPTS, format=schema,
                                                      messages=[dict(role="user", content=prompt)]))
            r.raise_for_status()
            try:
                a = json.loads(r.json()["message"]["content"]).get("answer", "")
            except (ValueError, AttributeError):
                a = "INVALID"
            res["probe"].setdefault(ev, {})[arm] = a if a in allowed else "INVALID"
            if first:
                ps = c.get(f"{host}/api/ps").json().get("models", [])
                m = next((x for x in ps if x["name"] == args.model), None)
                if m is None or m.get("size_vram", 0) < m.get("size", 1):
                    sys.exit(f"stopping: {args.model} not fully in VRAM; no CPU offload allowed")
                first = False
        c.post(f"{host}/api/generate", json=dict(model=args.model, keep_alive=0, prompt=""))


def cmd_run(args):
    rows = prompts(Path(args.texts))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"run_{args.model.replace(':', '_').replace('/', '_')}.json"
    if path.exists():
        sys.exit(f"REFUSING: {path} exists (each cell is run once)")
    res = dict(model=args.model, probe={}, status="COMPLETE", truth={r["event"]: r["identity_letter"] for r in rows})
    (run_luna if args.model == "gpt-5.6-luna" else run_local)(args, rows, res)
    path.write_text(json.dumps(res, indent=1))
    print("wrote", path, "| status", res["status"], "| spent_usd", round(res.get("spent_usd", 0.0), 4))


def binom_k(n: int, p: float = 1 / 8, alpha: float = 0.05) -> int:
    for k in range(n + 1):
        if sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1)) <= alpha:
            return k
    return n + 1


def dataset_runs(ver):
    runs = {}
    for f in sorted(Path(f"data/eval/chimera/{ver}").glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    return runs


def g2(r):
    T, S = r["truth"], r["synth_truth"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
    sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
    a = sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl)
    b = sum(r["synth"][i]["A"] == r["synth"][i]["B"] for i in sp) / len(sp)
    return a, b


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r_ = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for q in range(i, j + 1):
            r_[order[q]] = (i + j) / 2 + 1
        i = j + 1
    return r_


def mean_of(d, ks):
    return sum(x for k in ks for x in d[k]) / sum(len(d[k]) for k in ks)


def reevaluate(ver, probes, out):
    runs = dataset_runs(ver)
    valid = {m: r for m, r in runs.items() if g2(r)[0] >= G2A_BAR and g2(r)[1] >= G2B_BAR}
    by, sy, ev_rate = {}, {}, {}
    for m, r in valid.items():
        T, S = r["truth"], r["synth_truth"]
        for i, t in T.items():
            if t["kind"] != "pre":
                continue
            a_ = int(r["real"][i]["A"] == t["identity_letter"])
            b_ = (int(r["real"][i]["B"] == t["identity_letter"]) + int(r["real"][i]["B2"] == t["identity_letter"])) / 2
            by.setdefault(i, []).append(a_ - b_)
            v = ev_rate.setdefault(t["event"], [0, 0])
            v[0] += a_
            v[1] += 1
        for i, t in S.items():
            if t["type"] == "pre_alias":
                sy.setdefault(i, []).append(int(r["synth"][i]["A"] == t["identity_letter"]) - int(r["synth"][i]["B"] == t["identity_letter"]))
    entry = dict(valid_models=sorted(valid), g2={m: [round(x, 3) for x in g2(r)] for m, r in runs.items()})
    if not by:
        return entry
    idl, sid = sorted(by), sorted(sy)
    rng = random.Random(20261016)
    gb, db = [], []
    for _ in range(5000):
        g1 = mean_of(by, [rng.choice(idl) for _ in idl])
        g0 = mean_of(sy, [rng.choice(sid) for _ in sid])
        gb.append(g1)
        db.append(g1 - g0)
    gb.sort()
    db.sort()
    gp, gs = mean_of(by, idl), mean_of(sy, sid)
    mem_models = [m for m in valid if m in probes and out["probe"][m][ver]["memory_present"]]
    cond = dict(i=gp >= 0.10 and gb[125] > 0, ii=(gp - gs) > 0 and db[125] > 0, iii=len(mem_models) >= 3)
    verdict = ("INCONCLUSIVE (fewer than 3 valid models)" if len(valid) < 3 else
               "SUPPORTED" if all(cond.values()) else "PARTIALLY SUPPORTED" if cond["i"] else "NOT SUPPORTED")
    evs = sorted(ev_rate)
    xs = [ev_rate[e][0] / ev_rate[e][1] for e in evs]
    ys = [sum(1 for m in probes if probes[m]["probe"][e]["M2_orig"] == probes[m]["truth"][e]) for e in evs]
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    rho = sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / den if den else None
    entry.update(pooled_gap=gp, pooled_gap_ci95=[gb[125], gb[4875]], synthetic_gap=gs, did=gp - gs,
                 did_ci95=[db[125], db[4875]], memory_models_among_valid=mem_models, conditions=cond,
                 verdict=verdict, spearman_event_premature_vs_M2_models=rho, n_events=len(evs))
    return entry


def cmd_analyze(args):
    probes = {}
    for f in sorted(OUT.glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            probes[r["model"]] = r
    ids_v3 = [e["id"] for e in json.loads(V3_FILE.read_text())["events"]]
    ids_v2 = [e["id"] for f in V23_FILES for e in json.loads(f.read_text())["events"]]
    sets = {"pd_v2": ids_v2, "pd_v3": ids_v3, "all": ids_v2 + ids_v3}
    out = dict(preregistration="PREREG_PD_v4.md", probe={}, reevaluation={},
               label_provenance="TEXT-DERIVED oracle; selection by model-drafter; owner spot-check pending; no human labels")
    for m, r in probes.items():
        row = {}
        for name, ids in sets.items():
            k = binom_k(len(ids))
            n_o = sum(r["probe"][e]["M2_orig"] == r["truth"][e] for e in ids)
            row[name] = dict(events=len(ids), k_needed=k, M2_orig=n_o,
                             M2_ren=sum(r["probe"][e]["M2_ren"] == r["truth"][e] for e in ids),
                             M2_ren2=sum(r["probe"][e]["M2_ren2"] == r["truth"][e] for e in ids), memory_present=n_o >= k)
        out["probe"][m] = row
    for ver in ("pd_v2", "pd_v3"):
        out["reevaluation"][ver] = reevaluate(ver, probes, out)
    (OUT / "analysis.json").write_text(json.dumps(out, indent=1))
    for m, row in out["probe"].items():
        print(m, {k: (v["M2_orig"], v["M2_ren"], v["M2_ren2"], "k" + str(v["k_needed"]), v["memory_present"]) for k, v in row.items()})
    keys = ("valid_models", "pooled_gap", "pooled_gap_ci95", "synthetic_gap", "did_ci95", "memory_models_among_valid",
            "conditions", "verdict", "spearman_event_premature_vs_M2_models")
    for ver, e in out["reevaluation"].items():
        print(ver, json.dumps({k: e.get(k) for k in keys}))


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
