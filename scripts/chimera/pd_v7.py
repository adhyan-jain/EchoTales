"""PD v7 (PREREG_PD_v7.md): PROSPECTIVE test of the post hoc dose-response finding (report 5.22).

Hypothesis fixed before any model call: the original-versus-renamed leakage gap is larger for FAMOUS books than for OBSCURE
books, where fame is a binary class fixed by an objective rule (the book's title appears in a Project Gutenberg Top-100
downloads list at drafting time) and recorded in the events file before anything was run. Machinery is the frozen PD v6
runner (arms A, B, B2; alias-only closed book; title-assisted probe M2) with paths patched; arm B3 is built but not asked
(cost). Validity gate G2 as in v6 (B-vs-B2 on this set's controls >= 90%; synthetic A-vs-B >= 80% from each model's PD v3 run).
Inference: event is the unit; the stratum contrast is a permutation test over event fame labels plus a stratified event
bootstrap. Commands: freeze | build | run | estimate | analyze (same arguments as pd_v6).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pd_v6 as V6  # noqa: E402

P = V6.P
EVENTS7 = P / "PD_events_v7_additions.json"
MANIFEST7 = P / "MANIFEST_PD_v7.json"
OUT7 = Path("data/eval/chimera/pd_v7")
# patch the v6 runner's module globals (read at call time) and the pd_v3 builders it delegates to
V6.EVENTS6 = EVENTS7
V6.MANIFEST = MANIFEST7
V6.OUT = OUT7
V6.REAL_ARMS = ("A", "B", "B2")
V6.V3.EVENT_FILES = [EVENTS7]
V6.V3.MANIFEST = MANIFEST7
V6.V3.OUT = OUT7
SEED = 20261020


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_freeze(args):
    if MANIFEST7.exists():
        sys.exit("REFUSING: manifest exists; a change is a new version")
    files = [EVENTS7, P / "PD_v7_fame_snapshot.txt", P / "PD_prompts_v1.json", P / "PD_prompts_v2.json", P / "PD_prompts_v4.json"]
    man = dict(frozen_for="PREREG_PD_v7.md", prereg_sha256=sha(P / "PREREG_PD_v7.md"),
               event_files_sha256={EVENTS7.name: sha(EVENTS7)}, inputs_sha256={f.name: sha(f) for f in files},
               script_sha256_at_freeze=sha(Path(__file__)))
    MANIFEST7.write_text(json.dumps(man, indent=1))
    print("frozen", json.dumps(man, indent=1))


def perm_diff(fam: list[float], obs: list[float], n=20000):
    """difference of means famous minus obscure; one-sided permutation p over event fame labels; stratified bootstrap CI."""
    d = sum(fam) / len(fam) - sum(obs) / len(obs)
    allv = fam + obs
    rng = random.Random(SEED)
    hit = 0
    for _ in range(n):
        rng.shuffle(allv)
        if sum(allv[: len(fam)]) / len(fam) - sum(allv[len(fam):]) / len(obs) >= d - 1e-12:
            hit += 1
    bs = sorted(sum(rng.choice(fam) for _ in fam) / len(fam) - sum(rng.choice(obs) for _ in obs) / len(obs) for _ in range(5000))
    return d, (hit + 1) / (n + 1), [bs[125], bs[4875]]


def cmd_analyze(args):
    fame = {e["id"]: e["fame"] for e in json.loads(EVENTS7.read_text())["events"]}
    runs = {}
    for f in sorted(OUT7.glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            runs[r["model"]] = r
    v3 = {}
    for f in sorted(Path("data/eval/chimera/pd_v3").glob("run_*.json")):
        r = json.loads(f.read_text())
        if r.get("status") == "COMPLETE":
            v3[r["model"]] = r
    out = dict(preregistration="PREREG_PD_v7.md", per_model={}, strata={},
               label_provenance="TEXT-DERIVED oracle; model-selected; fame by Gutenberg top-100 rule; no human labels")
    ev_gap, valid_models, m2_by_model = {}, [], {}
    for m, r in runs.items():
        T = r["truth"]
        ctrl = [i for i, t in T.items() if t["kind"] == "ctrl"]
        g2a = sum(r["real"][i]["B"] == r["real"][i]["B2"] for i in ctrl) / len(ctrl)
        S = v3[m]["synth_truth"] if m in v3 else {}
        sp = [i for i, t in S.items() if t["type"] != "pre_alias"]
        g2b = (sum(v3[m]["synth"][i]["A"] == v3[m]["synth"][i]["B"] for i in sp) / len(sp)) if sp else float("nan")
        valid = bool(g2a >= 0.90 and g2b >= 0.80)
        gaps = {}
        for i, t in T.items():
            if t["kind"] == "pre":
                a = int(r["real"][i]["A"] == t["identity_letter"])
                b = (int(r["real"][i]["B"] == t["identity_letter"]) + int(r["real"][i]["B2"] == t["identity_letter"])) / 2
                gaps.setdefault(t["event"], []).append(a - b)
        ev_gap[m] = {e: sum(v) / len(v) for e, v in gaps.items()}
        m2_by_model[m] = {e: int(r["m2"][e]["M2_orig"] == r["m2_truth"][e]) for e in r["m2_truth"]}
        if valid:
            valid_models.append(m)
        out["per_model"][m] = dict(G2a=round(g2a, 4), G2b_from_v3=round(g2b, 4), G2_valid=valid)

    def stratum(models):
        evs = sorted({e for m in models for e in ev_gap[m]})
        per = {e: sum(ev_gap[m][e] for m in models if e in ev_gap[m]) / sum(1 for m in models if e in ev_gap[m]) for e in evs}
        fam = [per[e] for e in evs if fame.get(e) == "famous"]
        obs = [per[e] for e in evs if fame.get(e) == "obscure"]
        if len(fam) < 3 or len(obs) < 3:
            return dict(models=sorted(models), note="fewer than 3 events in a stratum", famous_events=len(fam), obscure_events=len(obs))
        d, p, ci = perm_diff(fam, obs)
        return dict(models=sorted(models), famous_events=len(fam), obscure_events=len(obs), mean_gap_famous=round(sum(fam) / len(fam), 4),
                    mean_gap_obscure=round(sum(obs) / len(obs), 4), difference=round(d, 4),
                    difference_ci95=[round(ci[0], 4), round(ci[1], 4)], one_sided_perm_p=round(p, 5),
                    condition_met=bool(d >= 0.10 and p < 0.05))

    loc = [m for m in valid_models if m != "gpt-5.6-luna"]
    if loc:
        out["strata"]["valid_local_pool"] = stratum(loc)
    if "gpt-5.6-luna" in runs:
        out["strata"]["luna"] = stratum(["gpt-5.6-luna"])
    out["strata"]["all_models"] = stratum(list(runs))
    if loc:
        rec = {e: sum(m2_by_model[m].get(e, 0) for m in loc) / len(loc) for e in sorted(fame) if all(e in m2_by_model[m] for m in loc)}
        fam = [v for e, v in rec.items() if fame[e] == "famous"]
        obs = [v for e, v in rec.items() if fame[e] == "obscure"]
        if len(fam) >= 3 and len(obs) >= 3:
            d, p, _ci = perm_diff(fam, obs)
            out["strata"]["recognition_M2"] = dict(models=sorted(loc), mean_famous=round(sum(fam) / len(fam), 4),
                                                   mean_obscure=round(sum(obs) / len(obs), 4), difference=round(d, 4),
                                                   one_sided_perm_p=round(p, 5), condition_met=bool(p < 0.05))
    h1 = out["strata"].get("valid_local_pool", {}).get("condition_met", False)
    h2 = out["strata"].get("luna", {}).get("condition_met", False)
    h3 = out["strata"].get("recognition_M2", {}).get("condition_met", False)
    n_fam = sum(1 for v in fame.values() if v == "famous")
    n_obs = sum(1 for v in fame.values() if v == "obscure")
    if len(loc) < 3 or n_fam < 4 or n_obs < 4:
        verdict = "INCONCLUSIVE (fewer than 3 valid local models or fewer than 4 events in a stratum)"
    elif h1 and h3:
        verdict = "SUPPORTED"
    elif h1 or h2:
        verdict = "PARTIALLY SUPPORTED"
    else:
        verdict = "NOT SUPPORTED"
    out["conditions"] = dict(H1_valid_local_famous_minus_obscure_ge10_p05=h1, H2_luna_same=h2, H3_recognition_higher_for_famous=h3)
    out["verdict"] = verdict
    (OUT7 / "analysis.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["per_model"]))
    for k, v in out["strata"].items():
        print(k, json.dumps(v))
    print("conditions", out["conditions"], "VERDICT:", verdict)


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
    dict(freeze=cmd_freeze, build=V6.cmd_build, run=V6.cmd_run, estimate=V6.cmd_estimate, analyze=cmd_analyze)[a.cmd](a)


if __name__ == "__main__":
    main()
