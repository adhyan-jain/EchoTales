"""Dose-response across all 38 events: does the per-event leakage gap rise with how well models recognise the book?

Predictor ("recognition"): number of the five LOCAL models that name the revealed identity under the title-assisted probe
M2 (original names), from the PD v4 runs (31 events) and PD v6 runs (7 events). Outcomes, deliberately a different model
family from the predictor: (a) Luna's per-event gap (A minus mean of B and B2) over pre-reveal items, (b) the valid
local-model pool's per-event gap. Spearman correlation with a permutation p-value (20,000 shuffles, seed 20261019) and a
leave-one-dataset-out check. POST HOC, descriptive; no model calls.
Output: data/eval/chimera/pd_dose_response.json.
"""
import json
import math
import random
from pathlib import Path

ROOT = Path("data/eval/chimera")
LOCAL = ["qwen2.5:7b", "llama3.1:8b", "mistral:7b-instruct", "phi4-mini:latest", "gemma2:9b"]
SEED = 20261019


def runs(ver):
    out = {}
    for f in sorted((ROOT / ver).glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            out[r["model"]] = r
    return out


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for q in range(i, j + 1):
            out[order[q]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / den if den else float("nan")


def perm_p(x, y, n=20000):
    obs = spearman(x, y)
    rng = random.Random(SEED)
    ys = list(y)
    hits = 0
    for _ in range(n):
        rng.shuffle(ys)
        if abs(spearman(x, ys)) >= abs(obs) - 1e-12:
            hits += 1
    return obs, (hits + 1) / (n + 1)


def event_gaps(r):
    T = r["truth"]
    per = {}
    for i, t in T.items():
        if t["kind"] != "pre":
            continue
        a = int(r["real"][i]["A"] == t["identity_letter"])
        b = (int(r["real"][i]["B"] == t["identity_letter"]) + int(r["real"][i]["B2"] == t["identity_letter"])) / 2
        per.setdefault(t["event"], []).append(a - b)
    return per


def g2_valid(r, v3run):
    T = r["truth"]
    ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
    a = sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl)
    S = v3run["synth_truth"]
    sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
    b = sum(v3run["synth"][i]["A"] == v3run["synth"][i]["B"] for i in sp) / len(sp)
    return a >= 0.90 and b >= 0.80


def main():
    v4, v6 = runs("pd_v4"), runs("pd_v6")
    ds = {"v2": runs("pd_v2"), "v3": runs("pd_v3"), "v6": v6}
    v3 = ds["v3"]
    recog = {}
    for m in LOCAL:
        if m in v4:
            for e, t in v4[m]["truth"].items():
                recog[e] = recog.get(e, 0) + int(v4[m]["probe"][e]["M2_orig"] == t)
        if m in v6:
            for e, t in v6[m]["m2_truth"].items():
                recog[e] = recog.get(e, 0) + int(v6[m]["m2"][e]["M2_orig"] == t)
    luna, pool = {}, {}
    for name, runs_ in ds.items():
        for m, r in runs_.items():
            g = event_gaps(r)
            if m == "gpt-5.6-luna":
                for e, v in g.items():
                    luna[e] = sum(v) / len(v)
            if m in LOCAL and m in v3 and g2_valid(r, v3[m]):
                for e, v in g.items():
                    pool.setdefault(e, []).extend(v)
    pool = {e: sum(v) / len(v) for e, v in pool.items()}
    events_of = {name: {t["event"] for t in next(iter(runs_.values()))["truth"].values()} for name, runs_ in ds.items()}
    out = dict(note="POST HOC dose-response; recognition = number of 5 local models naming the identity under M2 (title-assisted, original names)")
    for tag, outcome in (("luna_gap_vs_local_recognition", luna), ("valid_local_pool_gap_vs_local_recognition", pool)):
        evs = sorted(e for e in outcome if e in recog)
        x = [recog[e] for e in evs]
        y = [outcome[e] for e in evs]
        rho, p = perm_p(x, y)
        by = {k: round(sum(y[i] for i in range(len(evs)) if x[i] == k) / sum(1 for v in x if v == k), 4) for k in sorted(set(x))}
        loo = {}
        for hold in ("v2", "v3", "v6"):
            keep = [i for i, e in enumerate(evs) if e not in events_of[hold]]
            if len(keep) >= 5:
                loo[f"without_{hold}"] = round(spearman([x[i] for i in keep], [y[i] for i in keep]), 4)
        out[tag] = dict(events=len(evs), spearman=round(rho, 4), perm_p=round(p, 5), mean_gap_by_recognition_count=by,
                        events_per_count={k: sum(1 for v in x if v == k) for k in sorted(set(x))}, leave_one_dataset_out_spearman=loo)
    (ROOT / "pd_dose_response.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        if isinstance(v, dict):
            print(k, v)


if __name__ == "__main__":
    main()
