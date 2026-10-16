"""GPU-hour and cost plan for the confirmatory study on RunPod (no OpenAI), plus the Claude Sonnet 5.5 subscription arm.
No model calls, no spend. Output: data/eval/chimera/confirm_runpod_plan.json.

Facts used (all read 2026-10-16; prices through a summarising fetch tool, tag SUMM, not verbatim):
- RunPod on-demand pods (runpod.io/pricing, page dated 2026-10-08): A100 PCIe 80GB $1.19/h community, $1.79/h secure;
  H100 PCIe 80GB $1.99/h community, $2.89/h secure; L40S 48GB $0.79/h community.
- Measured tokens per short call from the PD v2 Luna run: 477 input, 9.7 output. Open-model tokenisers assumed 10% longer.
- Claude headless call measured 2026-10-16: `claude -p --model sonnet --tools "" --system-prompt ...` from a neutral directory ran
  claude-sonnet-5-5 with 814 cache-creation input tokens, 4 output tokens, 1.9 s, list-price-equivalent $0.0033 (subscription quota,
  not dollars).
ASSUMPTIONS (UNVERIFIED, to be measured in the calibration run): prefill throughput on one A100 80GB at about 40% utilisation:
Llama-3.3-70B AWQ 900 tokens/s, Qwen2.5-72B AWQ 850, OLMo-2-32B BF16 1,900, Mistral-Small-24B BF16 2,600; H100 = 2.5 x A100.
"""
import json
from pathlib import Path

ROOT = Path("data/eval/chimera")
IN_TOK, OUT_TOK, OPEN_FAC = 477, 9.7, 1.10
LONG_IN, LONG_OUT = 3300, 450  # E5 recap or profile: last 12,000 characters of the prefix plus instructions


def design(events, items_per_event, ctrl_per_event, e5_events, e2_events, dev_frac=0.2):
    dev = round(events * dev_frac)
    test = events - dev
    items_dev, items_test = dev * items_per_event, test * items_per_event
    blocks = dict(E1_dev_A_B_B3=items_dev * 3, E1_test_A_B_B3=items_test * 3, E1_B2_on_controls=test * ctrl_per_event,
                  M2_probe_3_arms=events * 3, G2b_synthetic=124, E4_open_name_O_P1_P2=items_test * 3,
                  E2_llm_authored_A_B_B3=e2_events * items_per_event * 3)
    return dict(events=events, dev=dev, test=test, items_per_event=items_per_event, short_calls_by_block=blocks,
                short_calls=sum(blocks.values()), long_calls_E5=e5_events * 2 * 3)


def per_model_tokens(d):
    t_in = (d["short_calls"] * IN_TOK + d["long_calls_E5"] * LONG_IN) * OPEN_FAC
    t_out = (d["short_calls"] * OUT_TOK + d["long_calls_E5"] * LONG_OUT) * OPEN_FAC
    return t_in, t_out


def plan(d, models, gpu_name, price, speedup, mining_tokens):
    rows, hours = {}, 0.0
    t_in, t_out = per_model_tokens(d)
    for name, (tps, load_min) in models.items():
        h = t_in / (tps * speedup) / 3600 + t_out / (250 * speedup) / 3600 + load_min / 60  # decode 250 tok/s aggregate assumed
        rows[name] = round(h, 2)
        hours += h
    mining_h = mining_tokens / (models["Llama-3.3-70B-AWQ"][0] * speedup) / 3600
    calib_h = 0.4
    total_h = hours + mining_h + calib_h
    return dict(gpu=gpu_name, price_per_hour=price, hours_per_model=rows, mining_audit_judge_hours=round(mining_h, 2),
                calibration_hours=calib_h, total_hours=round(total_h, 2), expected_usd=round(total_h * price, 2),
                worst_2x_usd=round(2 * total_h * price, 2))


def main():
    models3 = {"Llama-3.3-70B-AWQ": (900, 8), "Qwen2.5-72B-AWQ": (850, 8), "OLMo-2-32B-BF16": (1900, 12)}
    models4 = dict(models3, **{"Mistral-Small-3.2-24B-BF16": (2600, 9)})
    mining_tokens = 3.0e6 + 0.5e6 + 0.35e6  # candidate extraction, audit, faithfulness judge (tokens, input side)
    out = {}
    for label, args in (("core_150_events_7_items", (150, 7, 2, 60, 40)), ("lean_120_events_7_items", (120, 7, 2, 48, 40)),
                        ("wide_200_events_8_items", (200, 8, 2, 80, 60))):
        d = design(*args)
        t_in, t_out = per_model_tokens(d)
        entry = dict(design=d, per_open_model_input_tokens=round(t_in), per_open_model_output_tokens=round(t_out))
        for mset_name, mset in (("3_open_models", models3), ("4_open_models", models4)):
            entry[mset_name] = {
                "A100_80GB_community": plan(d, mset, "A100 PCIe 80GB community", 1.19, 1.0, mining_tokens),
                "H100_80GB_community_assuming_2.5x": plan(d, mset, "H100 PCIe 80GB community", 1.99, 2.5, mining_tokens)}
        # Claude Sonnet 5.5 via the subscription: E1 primary items only, no E4, no E5
        ct = d["test"] * (d["items_per_event"]) * 3 + d["events"] * 3
        entry["claude_sonnet_5_5_subscription"] = dict(
            calls=ct, tokens_incl_overhead=ct * (814 + IN_TOK), list_price_equivalent_usd=round(ct * 0.0033 + ct * 0.0016, 2),
            seconds_sequential=ct * 2, note="quota not dollars; no temperature or seed control; throttling expected")
        out[label] = entry
    (ROOT / "confirm_runpod_plan.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print(k, "short", v["design"]["short_calls"], "long", v["design"]["long_calls_E5"], "tokens/model in", v["per_open_model_input_tokens"])
        for ms in ("3_open_models", "4_open_models"):
            for g, p in v[ms].items():
                print("  ", ms, g, "hours", p["total_hours"], "expected $", p["expected_usd"], "worst 2x $", p["worst_2x_usd"])
        print("   claude", v["claude_sonnet_5_5_subscription"])


if __name__ == "__main__":
    main()
