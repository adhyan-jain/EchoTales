"""Luna (gpt-5.6-luna) run of the frozen PD v2 items (PREREG_PD_v2.md), budget-guarded.

Why a separate file: pd_v2.py is hash-frozen and local-only (ollama constrained decoding). Luna has no schema-constrained
path here, so the same v2 prompts (which ask for {"answer": X}) are sent as plain chat and the JSON answer is parsed; an
unparseable or out-of-list answer is INVALID. Output is written in the same schema as the local runs so
`pd_v2.py analyze` picks it up unchanged.

Owner authorisation (2026-10-16): "run luna, if it is below 0.15 then run it". `estimate` calibrates the character-based
token estimate against the measured v1 Luna run (117,136 input tokens over 282 calls) and prints expected and worst-case
cost; `run` refuses unless --budget-usd is given, stops before any call that could exceed it, and never prints the key.
"""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l1_llm_leakage as L1  # noqa: E402
import pd_reveal_benchmark as PD  # noqa: E402
import pd_v2 as V2  # noqa: E402

CAP_OUT = 32  # {"answer": "UNDETERMINED"} is about 10 tokens; the cap bounds the worst case
V1_ACTUAL_IN, V1_ACTUAL_OUT, V1_CALLS = 117136, 1636, 282  # data/eval/chimera/pd/run_gpt-5.6-luna.json


def all_prompts(texts, ri_db):
    real, cb = V2.prompts(Path(texts))
    syn = V2.synthetic(ri_db)
    jobs = []
    for p in real:
        for arm in ("A", "B", "B2"):
            jobs.append(("real", p["id"], arm, p[arm], p["cands"]))
    for p in cb:
        for arm in ("C_orig", "C_ren", "C_ren2"):
            jobs.append(("closed", p["event"], arm, p[arm], p["cands"]))
    for p in syn:
        for arm in ("A", "B"):
            jobs.append(("synth", p["id"], arm, p[arm], p["cands"]))
    return real, cb, syn, jobs


def v1_calibration(texts, ri_db):
    real, cb = PD.prompts_for(Path(texts))
    syn = PD.synthetic_prompts(ri_db)
    est = sum(L1.est_tokens(p[a]) for p in real for a in ("A", "B"))
    est += sum(L1.est_tokens(p[a]) for p in cb for a in ("C_orig", "C_ren"))
    est += sum(L1.est_tokens(p[a]) for p in syn for a in ("A", "B"))
    return V1_ACTUAL_IN / est


def cmd_estimate(args):
    _, _, _, jobs = all_prompts(args.texts, args.ri_db)
    k = v1_calibration(args.texts, args.ri_db)
    est_in = sum(L1.est_tokens(j[3]) for j in jobs)
    exp_in = math.ceil(est_in * k)
    exp_out = round(len(jobs) * V1_ACTUAL_OUT / V1_CALLS * 1.6)  # JSON wrapper adds tokens over a bare letter
    exp = exp_in * L1.PRICE_IN + exp_out * L1.PRICE_OUT
    worst_in = math.ceil(est_in * 1.3)
    worst = worst_in * L1.PRICE_IN + len(jobs) * CAP_OUT * L1.PRICE_OUT
    print(json.dumps(dict(calls=len(jobs), calibration_actual_over_estimated_v1=round(k, 4),
                          expected=dict(input_tokens=exp_in, output_tokens=exp_out, usd=round(exp, 4)),
                          worst_case=dict(input_tokens=worst_in, output_tokens=len(jobs) * CAP_OUT, usd=round(worst, 4)),
                          prices_per_million=dict(input=0.20, output=1.20)), indent=1))


def parse(text, cands):
    m = re.search(r'"answer"\s*:\s*"([^"]+)"', text)
    t = (m.group(1) if m else "").strip()
    return t if (t == "UNDETERMINED" or t in {L for L, _n, _i in cands}) else "INVALID"


def cmd_run(args):
    import httpx

    real, cb, syn, jobs = all_prompts(args.texts, args.ri_db)
    out = V2.OUT / "run_gpt-5.6-luna.json"
    if out.exists():
        sys.exit(f"REFUSING: {out} exists (each cell is run once)")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set in the environment")
    budget = L1.Budget(args.budget_usd)
    res = dict(model="gpt-5.6-luna", options=dict(reasoning_effort="none", max_completion_tokens=CAP_OUT),
               real={}, closed={}, synth={}, status="COMPLETE")
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=60.0) as c:
        del key
        for section, key_id, arm, prompt, cands in jobs:
            if not budget.can(L1.est_tokens(prompt), CAP_OUT):
                res["status"] = "STOPPED_AT_BUDGET"
                break
            r = L1.call_model(c, prompt, CAP_OUT)
            budget.calls += 1
            budget.tok_in += r["tok_in"]
            budget.tok_out += r["tok_out"]
            budget.actual += r["tok_in"] * L1.PRICE_IN + r["tok_out"] * L1.PRICE_OUT
            res[section].setdefault(key_id, {})[arm] = parse(r["text"], cands)
    res.update(spent_usd=budget.actual, calls=budget.calls, tok_in=budget.tok_in, tok_out=budget.tok_out)
    res["truth"] = {p["id"]: dict(truth_letter=p["truth_letter"], identity_letter=p["identity_letter"],
                                  kind=p["kind"], event=p["event"], distance=p["distance"],
                                  baseline_letter=p["baseline_letter"]) for p in real}
    res["closed_truth"] = {p["event"]: p["identity_letter"] for p in cb}
    res["synth_truth"] = {p["id"]: dict(type=p["type"], truth_letter=p["truth_letter"],
                                        identity_letter=p["identity_letter"]) for p in syn}
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out, "| status", res["status"], "| calls", budget.calls, "| spent_usd", round(budget.actual, 4))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("estimate", "run"):
        s = sp.add_parser(n)
        s.add_argument("--texts", required=True)
        s.add_argument("--ri-db", required=True)
        if n == "run":
            s.add_argument("--budget-usd", type=float, required=True)
    a = ap.parse_args()
    dict(estimate=cmd_estimate, run=cmd_run)[a.cmd](a)


if __name__ == "__main__":
    main()
