"""Power analysis and cost model for the confirmatory study (PREREG_PD_CONFIRM.md). No model calls, no spend.

POWER. Event-level spread of the leakage gap is measured on the 38 existing events (PD v2, v3, v6 runs): per model, the
per-event gap A minus mean(B, B2) over pre-reveal items. The minimum detectable effect (MDE) at 80% power for a
one-sample event-level test is (z_{1-alpha/2} + z_{power}) * SD / sqrt(n_events), with alpha Holm-adjusted for the number of
models (worst case alpha / k). Also computed: events needed for a +/-5 point equivalence band (E2) and events needed to
detect a Spearman correlation (dose-response) at 80% power.

COST. Tokens per short call and per long call come from measured usage (PD v2 Luna run: 477 input and 9.7 output tokens per
call over 1,132 calls). Prices are per 1M tokens as read on 2026-10-16 through a summarising fetch tool (tag SUMM, not
verbatim): OpenAI gpt-4o-mini $0.15 in / $0.60 out (developers.openai.com model page); gpt-5.6-luna $0.20 / $1.20 (ledger,
read 2026-10-15); DeepInfra Llama-3.3-70B-Instruct-Turbo $0.10 / $0.32, Qwen3-235B-A22B-Instruct-2507 $0.09 / $0.55,
Qwen2.5-72B-Instruct $0.36 / $0.40 (deepinfra.com/pricing, no date shown); RunPod on-demand A100 PCIe 80GB $1.19/h community,
$1.79/h secure; H100 SXM 80GB $2.69/h and $3.99/h (runpod.io/pricing, page dated 2026-10-08). Open-model tokenisers are
assumed 10% longer than OpenAI's. Worst case is 2x expected. Output: data/eval/chimera/confirm_design_numbers.json.
"""
import json
import math
from pathlib import Path

ROOT = Path("data/eval/chimera")


def z(p):  # inverse normal CDF by bisection on erf
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def event_gaps(ver, model):
    f = ROOT / ver / f"run_{model.replace(':', '_')}.json"
    if not f.exists():
        return {}
    r = json.loads(f.read_text())
    per = {}
    for i, t in r["truth"].items():
        if t["kind"] != "pre":
            continue
        a = int(r["real"][i]["A"] == t["identity_letter"])
        b = (int(r["real"][i]["B"] == t["identity_letter"]) + int(r["real"][i]["B2"] == t["identity_letter"])) / 2
        per.setdefault(t["event"], []).append(a - b)
    return {e: sum(v) / len(v) for e, v in per.items()}


def sd(xs):
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def power_block():
    out = {}
    for model in ("gpt-5.6-luna", "llama3.1:8b", "gemma2:9b", "mistral:7b-instruct", "qwen2.5:7b", "phi4-mini:latest"):
        gaps = {}
        for ver in ("pd_v2", "pd_v3", "pd_v6"):
            gaps.update(event_gaps(ver, model))
        if len(gaps) >= 10:
            xs = list(gaps.values())
            out[model] = dict(events=len(xs), mean_gap=round(sum(xs) / len(xs), 4), event_sd=round(sd(xs), 4))
    s_use = max(out["gpt-5.6-luna"]["event_sd"], 0.25)
    res = dict(per_model_existing=out, assumed_event_sd=s_use)
    for k_models in (1, 4):
        alpha = 0.05 / k_models
        for n in (100, 120, 160, 200):
            se = s_use / math.sqrt(n)
            res[f"MDE_80pct_power_alpha_{alpha:.4f}_n_events_{n}"] = round((z(1 - alpha / 2) + z(0.80)) * se, 4)
    for n in (30, 60, 100, 150, 200, 300):
        res[f"E2_halfwidth_95CI_n_{n}"] = round(1.96 * s_use / math.sqrt(n), 4)
    res["E2_events_needed_equivalence_pm5pts_80pct"] = math.ceil(((z(0.95) + z(0.90)) * s_use / 0.05) ** 2)
    res["E2_events_needed_equivalence_pm8pts_80pct"] = math.ceil(((z(0.95) + z(0.90)) * s_use / 0.08) ** 2)
    for rho in (0.2, 0.25, 0.3, 0.4):
        res[f"events_to_detect_spearman_{rho}"] = math.ceil(((z(0.975) + z(0.80)) / (0.5 * math.log((1 + rho) / (1 - rho)))) ** 2 + 3)
    for n in (100, 160):
        res[f"E4_noninferiority_5pt_power_n_{n}"] = round(0.5 * (1 + math.erf(((0.05 / (0.15 / math.sqrt(n))) - z(0.95)) / math.sqrt(2))), 4)
    return res


IN_TOK, OUT_TOK = 477, 9.7          # measured per short call (PD v2 Luna run)
LONG_IN, LONG_OUT = 6300, 450       # E5 recap / profile call (last 6,000 tokens of prefix + instructions; output cap)
OPEN_TOKEN_FACTOR = 1.10
PRICES = {  # (input, output, token factor) USD per 1M tokens
    "gpt-5.6-luna": (0.20, 1.20, 1.0),
    "gpt-4o-mini": (0.15, 0.60, 1.0),
    "meta-llama/Llama-3.3-70B-Instruct-Turbo (DeepInfra)": (0.10, 0.32, OPEN_TOKEN_FACTOR),
    "Qwen/Qwen3-235B-A22B-Instruct-2507 (DeepInfra)": (0.09, 0.55, OPEN_TOKEN_FACTOR),
    "Qwen/Qwen2.5-72B-Instruct (DeepInfra, optional)": (0.36, 0.40, OPEN_TOKEN_FACTOR),
}


def design(events_total, items_per_event, e2_events, e5_frac):
    dev = round(events_total * 0.2)
    test = events_total - dev
    items_dev, items_test = dev * items_per_event, test * items_per_event
    arms = dict(
        E1_dev_A_B_B3=items_dev * 3,
        E1_test_A_B_B3=items_test * 3,
        E1_B2_on_controls=test * 4,
        M2_probe_3_arms=events_total * 3,
        G2b_synthetic_62x2=124,
        E2_post_cutoff_A_B_B3=e2_events * items_per_event * 3,
        E4_open_name_4_arms=items_test * 4,
    )
    return dict(events_total=events_total, dev_events=dev, test_events=test, items_per_event=items_per_event,
                short_calls_by_block=arms, short_calls=sum(arms.values()), long_calls_E5=round(test * e5_frac) * 2 * 3)


def model_cost(d, key):
    pin, pout, fac = PRICES[key]
    t_in = (d["short_calls"] * IN_TOK + d["long_calls_E5"] * LONG_IN) * fac
    t_out = (d["short_calls"] * OUT_TOK + d["long_calls_E5"] * LONG_OUT) * fac
    return dict(input_tokens=round(t_in), output_tokens=round(t_out), expected_usd=round(t_in / 1e6 * pin + t_out / 1e6 * pout, 3))


def cost_block():
    out = {}
    for name, params in (("full_200_events", (200, 12, 60, 1.0)), ("lean_150_events", (150, 10, 40, 0.5))):
        d = design(*params)
        models = {k: model_cost(d, k) for k in PRICES}
        mining = round(3.0 * 0.15 + 0.3 * 0.60, 3)       # gpt-4o-mini over ~2,000 regex candidate passages of ~1,500 tokens
        audit = round(0.52 * 0.20 + 0.02 * 1.20, 3)      # independent audit by Luna of ~400 candidate events
        judge = round(4 * (d["long_calls_E5"] * 0.25) * (LONG_IN + LONG_OUT) / 1e6 * 0.15, 3)  # faithfulness judge, 25% sample, 4 models
        core = list(PRICES)[:4]
        openai = models["gpt-5.6-luna"]["expected_usd"] + models["gpt-4o-mini"]["expected_usd"] + mining + audit + judge
        deepinfra = sum(models[k]["expected_usd"] for k in core[2:])
        out[name] = dict(design=d, per_model=models, mining_gpt4omini=mining, audit_luna=audit, faithfulness_judge_gpt4omini=judge,
                         OPENAI_expected=round(openai, 2), OPENAI_worst_2x=round(2 * openai, 2),
                         DEEPINFRA_core2_expected=round(deepinfra, 2), DEEPINFRA_core2_worst_2x=round(2 * deepinfra, 2),
                         TOTAL_expected=round(openai + deepinfra, 2), TOTAL_worst_2x=round(2 * (openai + deepinfra), 2))
    d = design(200, 12, 60, 1.0)
    tokens = (d["short_calls"] * IN_TOK + d["long_calls_E5"] * LONG_IN) * OPEN_TOKEN_FACTOR
    hours_70b = tokens / 900 / 3600 + 0.5  # ASSUMED prefill 900 tokens/s (70B 4-bit, one A100 80GB), +0.5 h startup/download
    out["runpod_alternative"] = dict(
        assumption="prefill about 900 tokens/s for a 70B 4-bit model on one A100 80GB (UNVERIFIED; measure on a short pod first)",
        total_input_tokens_per_open_model=round(tokens), hours_one_70B_model=round(hours_70b, 1),
        cost_one_70B_model_A100_community_usd=round(hours_70b * 1.19, 2), cost_one_70B_model_A100_secure_usd=round(hours_70b * 1.79, 2),
        note="Qwen3-235B-A22B at FP8 needs roughly 2 x H100 80GB (about $5.38/h community, $7.98/h secure at the listed H100 SXM prices); one 70B model alone uses more than half of a $10 budget")
    return out


def main():
    res = dict(power=power_block(), cost=cost_block())
    (ROOT / "confirm_design_numbers.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["power"], indent=1))
    for k, v in res["cost"].items():
        if k.startswith(("full", "lean")):
            print(k, "short_calls", v["design"]["short_calls"], "long_calls", v["design"]["long_calls_E5"])
            for m, c in v["per_model"].items():
                print("   ", m, c)
            print("   mining", v["mining_gpt4omini"], "audit", v["audit_luna"], "judge", v["faithfulness_judge_gpt4omini"])
            print("   OPENAI", v["OPENAI_expected"], v["OPENAI_worst_2x"], "| DEEPINFRA(core2)", v["DEEPINFRA_core2_expected"], v["DEEPINFRA_core2_worst_2x"], "| TOTAL", v["TOTAL_expected"], v["TOTAL_worst_2x"])
    print(json.dumps(res["cost"]["runpod_alternative"], indent=1))


if __name__ == "__main__":
    main()
